from __future__ import annotations

import time
from typing import Any, Dict

from .schemas import IncidentCommand


def from_cli(summary: str, service: str = "payment-service", severity: str = "p1", environment: str = "prod") -> IncidentCommand:
    return IncidentCommand(command_id=f"cmd_{int(time.time()*1000)}", source="cli", event_type="create_incident", service=service, severity=severity, environment=environment, summary=summary)


def from_alertmanager(payload: Dict[str, Any]) -> IncidentCommand:
    labels = payload.get("commonLabels") or {}
    annotations = payload.get("commonAnnotations") or {}
    first = (payload.get("alerts") or [{}])[0]
    return IncidentCommand(
        command_id=f"cmd_{int(time.time()*1000)}",
        source="alertmanager",
        event_type="create_incident",
        service=labels.get("service", "payment-service"),
        severity=labels.get("severity", "p1"),
        environment=labels.get("environment", "prod"),
        alert_name=labels.get("alert_name") or labels.get("alertname"),
        summary=annotations.get("summary", ""),
        starts_at=first.get("startsAt"),
        generator_url=first.get("generatorURL"),
        raw_payload_ref="alertmanager://inline",
    )


def from_feishu_event(payload: Dict[str, Any]) -> IncidentCommand:
    event = payload.get("event") or payload
    event_type = event.get("event_type") or event.get("type") or "create_incident"
    return IncidentCommand(
        command_id=f"cmd_{int(time.time()*1000)}",
        source="feishu",
        event_type=event_type,
        service=event.get("service", "payment-service"),
        severity=event.get("severity", "p1"),
        environment=event.get("environment", "prod"),
        alert_name=event.get("alert_name"),
        summary=event.get("summary", ""),
        user_id=event.get("user_id") or event.get("open_id"),
        user_name=event.get("user_name"),
        approval_id=event.get("approval_id"),
        decision=event.get("decision"),
        raw_payload_ref="feishu://inline",
    )
