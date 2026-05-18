from __future__ import annotations

from typing import Any, Dict
from .config import load_settings
from .store import get_store

ALLOWED_EVENTS = {
    "incident.created", "evidence.collected", "hypothesis.generated", "action.planned",
    "approval.requested", "approval.resolved", "checkpoint.created", "checkpoint.restored",
    "skill.generated", "skill.published_to_hermes", "action.executed", "recovery.verified",
    "memory.recalled", "memory.learned", "memory.feedback", "memory.router.created_incident",
    "rag.recalled", "rag.ingested",
    "multimodal.evidence_attached", "multimodal.analyzed",
    "gateway.alertmanager.received", "gateway.feishu.received", "gateway.feishu.card_callback",
    "gateway.wecom.received", "gateway.wecom.card_callback",
    "event.unknown",
}


def record_event(incident_id: str, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if event_type not in ALLOWED_EVENTS:
        payload = {"original_event_type": event_type, "payload": payload}
        event_type = "event.unknown"
    return get_store(load_settings()).append_event(incident_id, event_type, payload)
