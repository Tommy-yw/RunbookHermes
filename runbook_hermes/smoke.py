from __future__ import annotations

import json

from .tools import action_policy_guard, incident_rca_guard, loki_query, prom_top_anomalies, recent_deploys, rollback_canary, runbook_approval_decision, trace_search


def _loads(s: str):
    return json.loads(s)


def run_smoke() -> dict:
    service = "payment-service"
    evidence = []
    for call in [
        prom_top_anomalies({"service": service}),
        loki_query({"service": service, "query": "error", "limit": 20}),
        trace_search({"service": service, "error_only": True}),
        recent_deploys({"service": service}),
    ]:
        payload = _loads(call)
        evidence.extend(payload.get("evidence", []))
    rca = _loads(incident_rca_guard({"service": service, "evidence": evidence}))
    policy = _loads(action_policy_guard({"service": service, "hypothesis": rca["hypothesis"]}))
    gate = _loads(rollback_canary({"service": service, "target_revision": "v2.3.0", "dry_run": False}))
    approved = _loads(runbook_approval_decision({"approval_id": gate.get("approval_id"), "decision": "approved", "approver": "smoke"}))
    executed = _loads(rollback_canary({"service": service, "target_revision": "v2.3.0", "dry_run": False, "approval_id": gate.get("approval_id")}))
    return {"ok": True, "evidence_count": len(evidence), "hypothesis": rca["hypothesis"], "policy": policy, "approval_gate": gate, "approval": approved, "execution": executed}
