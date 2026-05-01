from __future__ import annotations

from typing import Any, Dict
from .config import load_settings
from .store import JsonStore

ALLOWED_EVENTS = {
    "incident.created", "evidence.collected", "hypothesis.generated", "action.planned",
    "approval.requested", "approval.resolved", "checkpoint.created", "checkpoint.restored",
    "skill.generated", "action.executed", "recovery.verified",
    "gateway.alertmanager.received", "gateway.feishu.received", "gateway.feishu.card_callback",
    "gateway.wecom.received", "gateway.wecom.card_callback",
}


def record_event(incident_id: str, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if event_type not in ALLOWED_EVENTS:
        payload = {"original_event_type": event_type, "payload": payload}
        event_type = "incident.created"
    return JsonStore(load_settings().store_dir).append_event(incident_id, event_type, payload)
