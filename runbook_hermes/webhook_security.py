from __future__ import annotations

import base64
import hashlib
import json
import secrets
import struct
import time
import xml.etree.ElementTree as ET
from collections import OrderedDict
from typing import Any, Mapping

from .config import load_settings

_REPLAY_CACHE: OrderedDict[str, float] = OrderedDict()


class WebhookSecurityError(ValueError):
    """Raised when provider-native webhook authentication fails."""


def _header(headers: Mapping[str, Any], name: str) -> str:
    lname = name.lower()
    for key, value in headers.items():
        if str(key).lower() == lname:
            return str(value or "")
    return ""


def _json_loads(raw: bytes) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise WebhookSecurityError(f"invalid JSON payload: {exc}") from exc
    if not isinstance(data, dict):
        raise WebhookSecurityError("webhook JSON payload must be an object")
    return data


def _validate_timestamp(timestamp: str, *, replay_key: str, window_seconds: int) -> None:
    if not timestamp:
        raise WebhookSecurityError("missing webhook timestamp")
    try:
        ts = int(float(timestamp))
    except ValueError as exc:
        raise WebhookSecurityError("invalid webhook timestamp") from exc
    window = max(60, int(window_seconds or 600))
    now = int(time.time())
    if abs(now - ts) > window:
        raise WebhookSecurityError("webhook timestamp outside replay window")
    cutoff = now - window
    for key, seen_at in list(_REPLAY_CACHE.items()):
        if seen_at < cutoff:
            _REPLAY_CACHE.pop(key, None)
    if replay_key in _REPLAY_CACHE:
        raise WebhookSecurityError("duplicate webhook signature/timestamp/nonce")
    _REPLAY_CACHE[replay_key] = now
    while len(_REPLAY_CACHE) > 2048:
        _REPLAY_CACHE.popitem(last=False)


def _constant_time_equal(left: str, right: str) -> bool:
    return bool(left and right and secrets.compare_digest(str(left), str(right)))


def _pkcs7_unpad(data: bytes, block_size: int = 32) -> bytes:
    if not data:
        raise WebhookSecurityError("empty encrypted webhook body")
    pad = data[-1]
    if pad < 1 or pad > block_size or pad > len(data):
        raise WebhookSecurityError("invalid webhook padding")
    if data[-pad:] != bytes([pad]) * pad:
        raise WebhookSecurityError("invalid webhook padding bytes")
    return data[:-pad]


def _aes_cbc_decrypt(ciphertext: bytes, key: bytes, iv: bytes, *, block_size: int = 32) -> bytes:
    try:
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except Exception as exc:  # pragma: no cover - dependency packaging issue
        raise WebhookSecurityError("cryptography package is required for encrypted webhooks") from exc
    if len(iv) != 16:
        raise WebhookSecurityError("invalid AES IV length")
    if len(key) not in {16, 24, 32}:
        raise WebhookSecurityError("invalid AES key length")
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend()).decryptor()
    plain = decryptor.update(ciphertext) + decryptor.finalize()
    return _pkcs7_unpad(plain, block_size=block_size)


# ---------------- Feishu / Lark ----------------

def _feishu_signature(headers: Mapping[str, Any], raw_body: bytes, encrypt_key: str) -> tuple[str, str, str, tuple[str, str]]:
    timestamp = _header(headers, "X-Lark-Request-Timestamp")
    nonce = _header(headers, "X-Lark-Request-Nonce")
    signature = _header(headers, "X-Lark-Signature")
    if not (timestamp and nonce and signature):
        raise WebhookSecurityError("missing Feishu/Lark signature headers")
    digest = hashlib.sha256(timestamp.encode() + nonce.encode() + encrypt_key.encode() + raw_body).digest()
    expected_hex = digest.hex()
    expected_b64 = base64.b64encode(digest).decode("utf-8")
    return timestamp, nonce, signature, (expected_hex, expected_b64)


def _verify_feishu_signature(headers: Mapping[str, Any], raw_body: bytes, encrypt_key: str, window_seconds: int) -> None:
    timestamp, nonce, signature, expected = _feishu_signature(headers, raw_body, encrypt_key)
    if not any(secrets.compare_digest(value, signature) for value in expected):
        raise WebhookSecurityError("invalid Feishu/Lark signature")
    _validate_timestamp(timestamp, replay_key=f"feishu:{timestamp}:{nonce}:{signature}", window_seconds=window_seconds)


def _feishu_payload_token(payload: Mapping[str, Any]) -> str:
    header = payload.get("header") if isinstance(payload.get("header"), dict) else {}
    event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
    return str(
        payload.get("token")
        or payload.get("verification_token")
        or header.get("token")
        or header.get("verification_token")
        or event.get("token")
        or ""
    )


def _verify_feishu_token(payload: Mapping[str, Any], expected_token: str) -> None:
    if expected_token and not _constant_time_equal(_feishu_payload_token(payload), expected_token):
        raise WebhookSecurityError("Feishu/Lark verification token mismatch")


def _decrypt_feishu_payload(encrypt_value: str, encrypt_key: str) -> dict[str, Any]:
    key = hashlib.sha256(encrypt_key.encode("utf-8")).digest()
    iv = key[:16]
    try:
        cipher = base64.b64decode(encrypt_value)
    except Exception as exc:
        raise WebhookSecurityError("invalid Feishu/Lark encrypted payload") from exc
    plain = _aes_cbc_decrypt(cipher, key, iv, block_size=32)
    return _json_loads(plain)


def prepare_feishu_payload(headers: Mapping[str, Any], raw_body: bytes) -> dict[str, Any]:
    settings = load_settings()
    payload = _json_loads(raw_body)
    signature_ok = False
    if settings.feishu_encrypt_key:
        _verify_feishu_signature(headers, raw_body, settings.feishu_encrypt_key, settings.runbook_gateway_replay_window_seconds)
        signature_ok = True
        encrypted = payload.get("encrypt") or payload.get("Encrypt")
        if encrypted:
            payload = _decrypt_feishu_payload(str(encrypted), settings.feishu_encrypt_key)

    if settings.feishu_verification_token:
        _verify_feishu_token(payload, settings.feishu_verification_token)
    elif settings.runbook_gateway_allow_unsigned_callbacks:
        return payload
    elif settings.runbook_gateway_strict_security and not signature_ok:
        raise WebhookSecurityError("FEISHU_VERIFICATION_TOKEN or FEISHU_ENCRYPT_KEY is required in strict gateway mode")
    return payload


# ---------------- WeCom / Enterprise WeChat ----------------

def _xml_to_dict(raw: bytes) -> dict[str, Any]:
    if not raw.strip():
        return {}
    try:
        root = ET.fromstring(raw.decode("utf-8", "replace"))
    except ET.ParseError as exc:
        raise WebhookSecurityError(f"invalid WeCom XML payload: {exc}") from exc
    return {child.tag: child.text or "" for child in root}


def _wecom_signature(token: str, timestamp: str, nonce: str, encrypt: str) -> str:
    raw = "".join(sorted([token, timestamp, nonce, encrypt]))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _wecom_aes_key(encoding_aes_key: str) -> bytes:
    key = (encoding_aes_key or "").strip()
    if len(key) != 43:
        raise WebhookSecurityError("invalid WECOM_ENCODING_AES_KEY length")
    try:
        decoded = base64.b64decode(key + "=")
    except Exception as exc:
        raise WebhookSecurityError("invalid WECOM_ENCODING_AES_KEY") from exc
    if len(decoded) != 32:
        raise WebhookSecurityError("invalid decoded WECOM_ENCODING_AES_KEY length")
    return decoded


def _decrypt_wecom_message(encrypt_value: str, encoding_aes_key: str, expected_receive_id: str = "") -> str:
    aes_key = _wecom_aes_key(encoding_aes_key)
    try:
        encrypted = base64.b64decode(encrypt_value)
    except Exception as exc:
        raise WebhookSecurityError("invalid WeCom encrypted payload") from exc
    plain = _aes_cbc_decrypt(encrypted, aes_key, aes_key[:16], block_size=32)
    if len(plain) < 20:
        raise WebhookSecurityError("invalid WeCom plaintext length")
    msg_len = struct.unpack("!I", plain[16:20])[0]
    msg = plain[20:20 + msg_len]
    receive_id = plain[20 + msg_len:].decode("utf-8", "ignore")
    if expected_receive_id and receive_id and receive_id != expected_receive_id:
        raise WebhookSecurityError("WeCom receive_id/corp_id mismatch")
    return msg.decode("utf-8", "replace")


def _query_value(query: Mapping[str, Any], name: str) -> str:
    for key, value in query.items():
        if str(key) == name:
            return str(value or "")
    return ""


def _verify_wecom_signature(token: str, timestamp: str, nonce: str, encrypted: str, signature: str, window_seconds: int, replay_prefix: str) -> None:
    if not (token and timestamp and nonce and signature and encrypted):
        raise WebhookSecurityError("missing WeCom signature parameters")
    expected = _wecom_signature(token, timestamp, nonce, encrypted)
    if not secrets.compare_digest(expected, signature):
        raise WebhookSecurityError("invalid WeCom signature")
    _validate_timestamp(timestamp, replay_key=f"{replay_prefix}:{timestamp}:{nonce}:{signature}", window_seconds=window_seconds)


def prepare_wecom_payload(query: Mapping[str, Any], headers: Mapping[str, Any], raw_body: bytes) -> dict[str, Any]:
    settings = load_settings()
    token = settings.wecom_token
    encoding_aes_key = settings.wecom_encoding_aes_key
    msg_signature = _query_value(query, "msg_signature") or _query_value(query, "signature")
    timestamp = _query_value(query, "timestamp")
    nonce = _query_value(query, "nonce")
    echostr = _query_value(query, "echostr")

    if echostr:
        if token and encoding_aes_key:
            _verify_wecom_signature(token, timestamp, nonce, echostr, msg_signature, settings.runbook_gateway_replay_window_seconds, "wecom-url")
            return {"type": "url_verification", "echostr": _decrypt_wecom_message(echostr, encoding_aes_key, settings.wecom_corp_id)}
        if settings.runbook_gateway_allow_unsigned_callbacks:
            return {"type": "url_verification", "echostr": echostr}
        if settings.runbook_gateway_strict_security:
            raise WebhookSecurityError("WECOM_TOKEN and WECOM_ENCODING_AES_KEY are required for URL verification in strict mode")
        return {"type": "url_verification", "echostr": echostr}

    content_type = _header(headers, "Content-Type")
    if "json" in content_type.lower() or raw_body.strip().startswith(b"{"):
        payload = _json_loads(raw_body)
    else:
        payload = _xml_to_dict(raw_body)

    msg_signature = msg_signature or str(payload.get("MsgSignature") or payload.get("msg_signature") or "")
    timestamp = timestamp or str(payload.get("TimeStamp") or payload.get("timestamp") or "")
    nonce = nonce or str(payload.get("Nonce") or payload.get("nonce") or "")
    encrypt_value = payload.get("Encrypt") or payload.get("encrypt")
    if token and encrypt_value:
        _verify_wecom_signature(token, timestamp, nonce, str(encrypt_value), msg_signature, settings.runbook_gateway_replay_window_seconds, "wecom")
        if not encoding_aes_key:
            raise WebhookSecurityError("WECOM_ENCODING_AES_KEY is required for encrypted WeCom payload")
        decrypted = _decrypt_wecom_message(str(encrypt_value), encoding_aes_key, settings.wecom_corp_id)
        if decrypted.strip().startswith("<"):
            return _xml_to_dict(decrypted.encode("utf-8"))
        return _json_loads(decrypted.encode("utf-8"))

    if settings.runbook_gateway_allow_unsigned_callbacks:
        return dict(payload)
    if token and settings.runbook_gateway_strict_security:
        raise WebhookSecurityError("missing encrypted WeCom payload in strict mode")
    if not token and settings.runbook_gateway_strict_security:
        raise WebhookSecurityError("WECOM_TOKEN and WECOM_ENCODING_AES_KEY are required in strict gateway mode")

    return dict(payload)
