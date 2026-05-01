from __future__ import annotations

import json
from typing import Any, Dict

from .approval import create_approval, create_checkpoint, decide_approval, get_approval
from .backends import get_deploy_backend, get_observability_backend
from .execution import execute_non_rollback_action
from .rca_guard import guard_root_cause
from .action_policy import plan_action


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False)


def _as_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return default


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def prom_query(args: Dict[str, Any], **kwargs) -> str:
    service = args.get("service", "payment-service")
    result = get_observability_backend().prom_query(service, args.get("query", ""), args.get("window", "15m"))
    return _json(result)


def prom_top_anomalies(args: Dict[str, Any], **kwargs) -> str:
    service = args.get("service", "payment-service")
    return _json({"status": "ok", "evidence": get_observability_backend().prom_top_anomalies(service, args.get("window", "15m"))})


def loki_query(args: Dict[str, Any], **kwargs) -> str:
    service = args.get("service", "payment-service")
    limit = _as_int(args.get("limit", 20), 20)
    return _json({"status": "ok", "evidence": get_observability_backend().loki_query(service, args.get("query", ""), args.get("start", ""), args.get("end", ""), limit)})


def trace_search(args: Dict[str, Any], **kwargs) -> str:
    service = args.get("service", "payment-service")
    return _json({"status": "ok", "evidence": get_observability_backend().trace_search(service, args.get("start", ""), args.get("end", ""), _as_bool(args.get("error_only", True), True))})


def recent_deploys(args: Dict[str, Any], **kwargs) -> str:
    service = args.get("service", "payment-service")
    return _json({"status": "ok", "evidence": get_observability_backend().recent_deploys(service, args.get("since", "2h"))})


def rollback_canary(args: Dict[str, Any], **kwargs) -> str:
    service = args.get("service", "payment-service")
    target_revision = args.get("target_revision", "v2.3.0")
    dry_run = _as_bool(args.get("dry_run", True), True)
    approval_id = args.get("approval_id", "")
    incident_id = args.get("incident_id") or args.get("incidentId") or ""
    payload = {"incident_id": incident_id, "service": service, "target_revision": target_revision, "dry_run": dry_run}
    if not dry_run:
        approval = get_approval(approval_id) if approval_id else None
        if not approval or approval.get("status") != "approved":
            checkpoint = create_checkpoint(service, "rollback_canary", payload, incident_id=incident_id or None)
            approval = create_approval(service, "rollback_canary", payload, checkpoint["checkpoint_id"], incident_id=incident_id or None)
            return _json({"status": "approval_required", "service": service, "incident_id": incident_id, "approval_id": approval["approval_id"], "checkpoint_id": checkpoint["checkpoint_id"], "message": "rollback_canary is destructive. Approval is required before execution."})
    checkpoint_id = args.get("checkpoint_id") or (get_approval(approval_id) or {}).get("checkpoint_id", "")
    return _json(get_deploy_backend().rollback_canary(service, target_revision, dry_run=dry_run, checkpoint_id=checkpoint_id))


def verify_recovery(args: Dict[str, Any], **kwargs) -> str:
    service = args.get("service", "payment-service")
    return _json(get_deploy_backend().verify_recovery(service, window=args.get("window", "2m")))


def incident_rca_guard(args: Dict[str, Any], **kwargs) -> str:
    return _json(guard_root_cause(args))


def action_policy_guard(args: Dict[str, Any], **kwargs) -> str:
    return _json(plan_action(args))


def runbook_approval_decision(args: Dict[str, Any], **kwargs) -> str:
    return _json(decide_approval(args.get("approval_id", ""), args.get("decision", "rejected"), args.get("approver", "operator"), args.get("comment", "")))


def execute_controlled_action(args: Dict[str, Any], **kwargs) -> str:
    """Execute a non-rollback controlled action through an explicit executor backend.

    This tool is intentionally conservative. Without ACTION_EXECUTION_BACKEND
    it returns executor_not_configured and does not mutate anything.
    """
    action = {
        "action_type": args.get("action_type", "controlled_action"),
        "title": args.get("title", "Controlled action"),
        "risk_level": args.get("risk_level", "write_safe"),
        "args": args.get("action_args", {}),
    }
    incident = {
        "incident_id": args.get("incident_id"),
        "service": args.get("service", "payment-service"),
    }
    return _json(execute_non_rollback_action(action, incident, args.get("approval_id")))
