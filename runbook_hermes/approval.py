from __future__ import annotations

import time
from typing import Any, Dict

from .config import load_settings
from .store import JsonStore


def _store() -> JsonStore:
    return JsonStore(load_settings().store_dir)


def _event_key(service: str, incident_id: str | None = None) -> str:
    """Prefer incident_id for timelines; fall back to service for standalone tool use."""
    return incident_id or service or "unknown"


def create_checkpoint(
    service: str,
    action: str,
    payload: Dict[str, Any],
    incident_id: str | None = None,
) -> Dict[str, Any]:
    incident_id = incident_id or payload.get("incident_id")
    checkpoint_id = f"checkpoint_{int(time.time() * 1000)}"
    item = {
        "checkpoint_id": checkpoint_id,
        "incident_id": incident_id,
        "service": service,
        "action": action,
        "payload": payload,
        "created_at": time.time(),
    }
    _store().put("checkpoints", checkpoint_id, item)
    _store().append_event(_event_key(service, incident_id), "checkpoint.created", item)
    return item


def create_approval(
    service: str,
    action: str,
    payload: Dict[str, Any],
    checkpoint_id: str,
    incident_id: str | None = None,
) -> Dict[str, Any]:
    incident_id = incident_id or payload.get("incident_id")
    approval_id = f"approval_{int(time.time() * 1000)}"
    item = {
        "approval_id": approval_id,
        "incident_id": incident_id,
        "service": service,
        "action": action,
        "payload": payload,
        "checkpoint_id": checkpoint_id,
        "status": "pending",
        "created_at": time.time(),
    }
    _store().put("approvals", approval_id, item)
    _store().append_event(_event_key(service, incident_id), "approval.requested", item)
    return item


def decide_approval(approval_id: str, decision: str, approver: str = "operator", comment: str = "") -> Dict[str, Any]:
    data = _store().read("approvals")
    item = data.get(approval_id)
    if not item:
        return {"status": "not_found", "approval_id": approval_id}
    normalized = decision.lower().strip()
    item["status"] = "approved" if normalized in {"approved", "approve", "yes"} else "rejected"
    item["approver"] = approver
    item["comment"] = comment
    item["decided_at"] = time.time()
    data[approval_id] = item
    _store().write("approvals", data)
    _store().append_event(_event_key(item.get("service", "unknown"), item.get("incident_id")), "approval.resolved", item)
    return item


def get_approval(approval_id: str) -> Dict[str, Any] | None:
    return _store().read("approvals").get(approval_id)
