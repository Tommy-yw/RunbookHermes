from __future__ import annotations

from typing import Any, Dict
from runbook_hermes.commands import IncidentCommand


def normalize_event(payload: Dict[str, Any]) -> IncidentCommand:
    text = payload.get("Content") or payload.get("content") or payload.get("summary") or "payment-service HTTP 503 spike after release"
    return IncidentCommand(
        command_id=payload.get("MsgId") or payload.get("command_id") or "wecom_inline",
        source="wecom",
        event_type=payload.get("event_type", "create_incident"),
        service=payload.get("service", "payment-service"),
        severity=payload.get("severity", "p1"),
        environment=payload.get("environment", "prod"),
        alert_name=payload.get("alert_name", "payment_503_spike"),
        summary=text,
        user_id=payload.get("FromUserName") or payload.get("user_id"),
        user_name=payload.get("user_name"),
        approval_id=payload.get("approval_id"),
        decision=payload.get("decision"),
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
        user_id=action.get("user_id"),
        user_name=action.get("user_name"),
        raw_payload_ref="wecom://card-callback-inline",
    )
