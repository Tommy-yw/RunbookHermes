from __future__ import annotations

from typing import Any, Dict, Mapping, Tuple
from runbook_hermes.commands import IncidentCommand
from runbook_hermes.webhook_security import prepare_wecom_payload


def normalize_event(payload: Dict[str, Any]) -> IncidentCommand:
    text = payload.get("Content") or payload.get("content") or payload.get("summary") or "payment-service HTTP 503 spike after release"
    event_type = payload.get("event_type") or payload.get("Event") or payload.get("MsgType") or "create_incident"
    if str(event_type).lower() in {"approval", "approve_or_reject_action", "card_callback"}:
        event_type = "approve_or_reject_action"
    return IncidentCommand(
        command_id=payload.get("MsgId") or payload.get("command_id") or "wecom_inline",
        source="wecom",
        event_type=event_type,
        service=payload.get("service", "payment-service"),
        severity=payload.get("severity", "p1"),
        environment=payload.get("environment", "prod"),
        alert_name=payload.get("alert_name", "payment_503_spike"),
        summary=text,
        user_id=payload.get("FromUserName") or payload.get("user_id"),
        user_name=payload.get("user_name"),
        approval_id=payload.get("approval_id"),
        decision=payload.get("decision"),
        second_confirmation=payload.get("second_confirmation") or payload.get("confirmation") or payload.get("confirmation_token"),
        raw_payload_ref="wecom://inline",
    )


def normalize_card_callback(payload: Dict[str, Any]) -> IncidentCommand:
    action = payload.get("action") or payload
    return IncidentCommand(
        command_id=payload.get("command_id", "wecom_card_inline"),
        source="wecom",
        event_type="approve_or_reject_action",
        service=action.get("service", "payment-service"),
        severity=action.get("severity", "p1"),
        environment=action.get("environment", "prod"),
        summary=action.get("summary", ""),
        approval_id=action.get("approval_id"),
        decision=action.get("decision"),
        second_confirmation=action.get("second_confirmation") or action.get("confirmation") or action.get("confirmation_token"),
        user_id=action.get("user_id"),
        user_name=action.get("user_name"),
        raw_payload_ref="wecom://card-callback-inline",
    )


def parse_http_body(raw_body: bytes, query: Mapping[str, str] | None = None, content_type: str = "") -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Verify/decrypt a WeCom HTTP webhook body and return payload plus metadata."""
    headers = {"Content-Type": content_type} if content_type else {}
    payload = prepare_wecom_payload(query or {}, headers, raw_body or b"{}")
    return payload, {"provider": "wecom", "verified": True}
