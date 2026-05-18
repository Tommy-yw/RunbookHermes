from __future__ import annotations

import secrets
from typing import Any, Dict

from fastapi import HTTPException, Request, status

from .config import load_settings

PUBLIC_PATH_PREFIXES = ("/web",)
PUBLIC_EXACT_PATHS = {
    "/",
    "/health",
    "/auth/status",
    "/favicon.ico",
}
FEISHU_WEBHOOK_PATHS = {
    "/gateway/feishu/events",
    "/gateway/feishu/webhook",
    "/gateway/feishu/card-callback",
}
WECOM_WEBHOOK_PATHS = {
    "/gateway/wecom/events",
    "/gateway/wecom/webhook",
    "/gateway/wecom/card-callback",
}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _token_from_request(request: Request, header_name: str) -> str:
    header_value = request.headers.get(header_name) or request.headers.get(header_name.lower())
    if header_value:
        return header_value.strip()
    auth = request.headers.get("authorization", "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def _is_public_path(path: str) -> bool:
    if path in PUBLIC_EXACT_PATHS:
        return True
    for prefix in PUBLIC_PATH_PREFIXES:
        if path == prefix or path.startswith(prefix.rstrip("/") + "/"):
            return True
    return False


def _webhook_public_path(path: str) -> bool:
    settings = load_settings()
    if path in FEISHU_WEBHOOK_PATHS:
        return bool(getattr(settings, "runbook_gateway_allow_unsigned_callbacks", False) or settings.feishu_verification_token or settings.feishu_encrypt_key)
    if path in WECOM_WEBHOOK_PATHS:
        return bool(getattr(settings, "runbook_gateway_allow_unsigned_callbacks", False) or (settings.wecom_token and settings.wecom_encoding_aes_key))
    return False


def _matches(candidate: str, expected: str) -> bool:
    return bool(candidate and expected and secrets.compare_digest(candidate, expected))


def auth_status() -> Dict[str, Any]:
    settings = load_settings()
    return {
        "enabled": bool(settings.runbook_api_auth_enabled),
        "header": settings.runbook_api_auth_header,
        "write_token_configured": bool(settings.runbook_api_token),
        "read_only_token_configured": bool(settings.runbook_api_read_only_token),
        "public_paths": sorted(PUBLIC_EXACT_PATHS),
        "public_prefixes": list(PUBLIC_PATH_PREFIXES),
        "webhook_public_paths": {
            "feishu": sorted(FEISHU_WEBHOOK_PATHS) if (settings.feishu_verification_token or settings.feishu_encrypt_key) else [],
            "wecom": sorted(WECOM_WEBHOOK_PATHS) if (settings.wecom_token and settings.wecom_encoding_aes_key) else [],
        },
        "docs_enabled": False,
    }


async def require_runbook_api_auth(request: Request) -> None:
    """FastAPI dependency for RunbookHermes API token authentication.

    API authentication is enabled by default. Web UI static assets, health and
    auth status remain public. Feishu/WeCom webhook paths bypass the API token
    only when their own verification/encryption settings are configured, and
    the endpoint then performs provider-native signature/token checks.
    """
    path = request.url.path
    if _is_public_path(path) or _webhook_public_path(path):
        return
    settings = load_settings()
    if not settings.runbook_api_auth_enabled:
        return
    if not settings.runbook_api_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RunbookHermes API auth is enabled but RUNBOOK_API_TOKEN is not configured",
        )
    token = _token_from_request(request, settings.runbook_api_auth_header)
    if _matches(token, settings.runbook_api_token):
        return
    if request.method.upper() in SAFE_METHODS and _matches(token, settings.runbook_api_read_only_token):
        return
    if token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid RunbookHermes API token")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="missing RunbookHermes API token",
        headers={"WWW-Authenticate": "Bearer"},
    )
