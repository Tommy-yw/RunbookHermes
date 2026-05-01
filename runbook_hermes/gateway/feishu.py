from __future__ import annotations

from typing import Any, Dict
from runbook_hermes.commands import from_feishu_event
from runbook_hermes.config import load_settings


def verify_token(payload: Dict[str, Any]) -> bool:
    expected = load_settings().feishu_verification_token
    if not expected:
        return True
    return payload.get("token") == expected or payload.get("verification_token") == expected


def normalize_event(payload: Dict[str, Any]):
    if not verify_token(payload):
        raise ValueError("Feishu verification token mismatch")
    return from_feishu_event(payload)


def normalize_card_callback(payload: Dict[str, Any]):
    if not verify_token(payload):
        raise ValueError("Feishu verification token mismatch")
    action = payload.get("action") or payload.get("event") or payload
    return from_feishu_event({"event": {"event_type": "approve_or_reject_action", "approval_id": action.get("approval_id"), "decision": action.get("decision"), "service": action.get("service", "payment-service"), "user_id": action.get("user_id"), "user_name": action.get("user_name")}})
