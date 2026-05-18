from __future__ import annotations

import secrets
from typing import Any, Dict, Mapping, Tuple
from runbook_hermes.commands import from_feishu_event
from runbook_hermes.config import load_settings
from runbook_hermes.memory_router import extract_text_from_payload
from runbook_hermes.webhook_security import prepare_feishu_payload


def _payload_token(payload: Dict[str, Any]) -> str:
    header = payload.get("header") if isinstance(payload.get("header"), dict) else {}
    event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
    return (
        str(payload.get("token") or "")
        or str(payload.get("verification_token") or "")
        or str(header.get("token") or "")
        or str(event.get("token") or "")
    )


def verify_token(payload: Dict[str, Any]) -> bool:
    expected = load_settings().feishu_verification_token
    if not expected:
        return True
    token = _payload_token(payload)
    return bool(token and secrets.compare_digest(token, expected))


def normalize_event(payload: Dict[str, Any]):
    if not verify_token(payload):
        raise ValueError("Feishu verification token mismatch")
    # Real Feishu message events often put text inside event.message.content.
    # Preserve demo/mock shape while enriching summary so the memory router and
    # incident command share the same text.
    event = dict(payload.get("event") or payload)
    text = extract_text_from_payload(payload)
    if text and not event.get("summary"):
        event["summary"] = text
    normalized = dict(payload)
    normalized["event"] = event
    return from_feishu_event(normalized)


def normalize_card_callback(payload: Dict[str, Any]):
    if not verify_token(payload):
        raise ValueError("Feishu verification token mismatch")
    action = payload.get("action") or payload.get("event") or payload
    return from_feishu_event({"event": {"event_type": "approve_or_reject_action", "approval_id": action.get("approval_id"), "decision": action.get("decision"), "second_confirmation": action.get("second_confirmation") or action.get("confirmation") or action.get("confirmation_token"), "service": action.get("service", "payment-service"), "user_id": action.get("user_id"), "user_name": action.get("user_name")}})


def parse_http_body(raw_body: bytes, headers: Mapping[str, str] | None = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Verify/decrypt a Feishu/Lark HTTP webhook body and return payload plus metadata."""
    payload = prepare_feishu_payload(headers or {}, raw_body or b"{}")
    return payload, {"provider": "feishu", "verified": True, "encrypted": bool(payload.get("encrypt") or payload.get("Encrypt"))}
