from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

from .approval import create_approval, create_checkpoint
from .events import record_event
from .config import load_settings
from .execution import execute_non_rollback_action
from .model_client import RunbookModelClient
from .store import JsonStore
from .tools import (
    action_policy_guard,
    incident_rca_guard,
    loki_query,
    prom_top_anomalies,
    recent_deploys,
    rollback_canary,
    runbook_approval_decision,
    trace_search,
)


ROOT = Path(__file__).resolve().parent.parent
SCENARIO_DIR = ROOT / "data" / "runbook_mock" / "scenarios"


def _store() -> JsonStore:
    return JsonStore(load_settings().store_dir)


def _loads(s: str) -> Dict[str, Any]:
    return json.loads(s)


def _short_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _scenario_key(summary: str = "", alert_name: str = "") -> str:
    text = f"{summary} {alert_name}".lower()
    if "coupon" in text or "504" in text:
        return "coupon_504_timeout"
    if "order" in text or "429" in text or "rate limit" in text or "rate-limit" in text:
        return "order_429_rate_limit"
    return "payment_503_spike"


def _filter_evidence(items: List[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
    if key == "coupon_504_timeout":
        keep = ("504", "coupon", "timeout")
    elif key == "order_429_rate_limit":
        keep = ("429", "order", "rate limit", "rate_limit")
    else:
        keep = ("503", "connection pool", "mysql", "v2.3.1", "db_pool", "p95")
    filtered = []
    for item in items:
        text = json.dumps(item, ensure_ascii=False).lower()
        if any(term in text for term in keep):
            filtered.append(item)
    return filtered or items


def collect_evidence(service: str, summary: str = "", alert_name: str = "") -> List[Dict[str, Any]]:
    scenario = _scenario_key(summary, alert_name)
    if scenario == "coupon_504_timeout":
        log_query = "coupon-service timeout HTTP 504"
    elif scenario == "order_429_rate_limit":
        log_query = "order-service HTTP 429 rate_limit_exceeded"
    else:
        log_query = "connection pool exhausted HTTP 503 mysql-payment"

    calls = [
        prom_top_anomalies({"service": service, "window": "15m"}),
        loki_query({"service": service, "query": log_query, "limit": 20}),
        trace_search({"service": service, "error_only": True}),
        recent_deploys({"service": service, "since": "2h"}) if scenario == "payment_503_spike" else json.dumps({"status": "ok", "evidence": []}),
    ]

    evidence: List[Dict[str, Any]] = []
    for raw in calls:
        payload = _loads(raw)
        items = payload.get("evidence")
        if isinstance(items, list):
            evidence.extend(items)
        elif isinstance(items, dict):
            evidence.append(items)

    evidence = _filter_evidence(evidence, scenario)
    for idx, ev in enumerate(evidence, start=1):
        ev.setdefault("evidence_id", f"ev_{scenario}_{idx}")
        ev.setdefault("scenario", scenario)
    return evidence


def _build_skill(incident: Dict[str, Any]) -> Dict[str, Any]:
    skill_id = _short_id("skill")
    hypothesis = incident.get("hypothesis") or {}
    action = incident.get("action") or {}
    body = f"""# Runbook Skill: {incident.get('service', 'service')} incident triage

## When to use
Use this runbook when `{incident.get('service')}` reports `{incident.get('summary')}`.

## Evidence to collect
- Metrics anomalies
- Logs containing timeout, connection pool, HTTP 503, HTTP 504, HTTP 429 or dependency errors
- Trace latency and downstream error evidence
- Recent deployments when a release regression is suspected

## Current hypothesis
{hypothesis.get('title', 'No hypothesis recorded')}

## Evidence IDs
{', '.join(hypothesis.get('evidence_ids', [])) or 'No evidence IDs recorded'}

## Recommended action
{action.get('title', 'No action recorded')}

## Safety
High-risk actions require approval, checkpoint and dry-run before execution. Non-rollback write actions require an explicit executor backend before production mutation.
"""
    item = {
        "skill_id": skill_id,
        "incident_id": incident["incident_id"],
        "title": f"{incident.get('service')} incident runbook",
        "body": body,
        "created_at": time.time(),
    }
    _store().put("skills", skill_id, item)
    record_event(incident["incident_id"], "skill.generated", item)
    return item


def _prepare_action_gate(incident_id: str, incident: Dict[str, Any], action: Dict[str, Any]) -> Dict[str, Any]:
    if not action or not action.get("requires_approval"):
        return {"status": "no_approval_required"}

    action_type = action.get("action_type")
    if action_type == "rollback_canary":
        return _loads(
            rollback_canary(
                {
                    "incident_id": incident_id,
                    "service": incident.get("service", "payment-service"),
                    "target_revision": action.get("args", {}).get("target_revision", action.get("target_revision", "v2.3.0")),
                    "dry_run": False,
                }
            )
        )

    checkpoint = create_checkpoint(
        incident.get("service", "unknown"),
        action_type or "controlled_action",
        {"incident_id": incident_id, "action": action},
        incident_id=incident_id,
    )
    approval = create_approval(
        incident.get("service", "unknown"),
        action_type or "controlled_action",
        {"incident_id": incident_id, "action": action},
        checkpoint["checkpoint_id"],
        incident_id=incident_id,
    )
    record_event(incident_id, "checkpoint.created", checkpoint)
    record_event(incident_id, "approval.requested", approval)
    return {
        "status": "approval_required",
        "checkpoint_id": checkpoint["checkpoint_id"],
        "approval_id": approval["approval_id"],
        "action_type": action_type,
        "message": "Non-rollback controlled action requires approval and an executor backend.",
    }


def create_incident(
    summary: str,
    service: str = "payment-service",
    severity: str = "p1",
    environment: str = "prod",
    source: str = "web",
    alert_name: str | None = None,
) -> Dict[str, Any]:
    incident_id = _short_id("inc")
    now = time.time()
    alert_name = alert_name or _scenario_key(summary)
    incident = {
        "incident_id": incident_id,
        "service": service,
        "severity": severity,
        "environment": environment,
        "summary": summary or f"{service} HTTP 503 spike after release",
        "alert_name": alert_name,
        "source": source,
        "status": "collecting",
        "created_at": now,
        "updated_at": now,
    }
    _store().put("incidents", incident_id, incident)
    record_event(incident_id, "incident.created", incident)

    evidence = collect_evidence(service, summary=summary, alert_name=alert_name)
    for ev in evidence:
        ev = dict(ev)
        ev.setdefault("evidence_id", _short_id("ev"))
        ev["incident_id"] = incident_id
        _store().put("evidence", ev["evidence_id"], ev)
    record_event(incident_id, "evidence.collected", {"count": len(evidence), "items": evidence})

    rca = _loads(incident_rca_guard({"service": service, "evidence": evidence}))
    hypothesis = rca.get("hypothesis", {})
    hypothesis.setdefault("hypothesis_id", _short_id("hyp"))
    hypothesis["incident_id"] = incident_id
    _store().put("hypotheses", hypothesis["hypothesis_id"], hypothesis)
    record_event(incident_id, "hypothesis.generated", hypothesis)

    policy = _loads(action_policy_guard({"service": service, "hypothesis": hypothesis}))
    action_list = policy.get("actions") or []
    action = action_list[0] if action_list else {}
    if action:
        action.setdefault("action_id", _short_id("act"))
        action["incident_id"] = incident_id
        _store().put("actions", action["action_id"], action)
        record_event(incident_id, "action.planned", action)
    else:
        record_event(incident_id, "action.planned", {"status": "no_action", "service": service})

    gate = _prepare_action_gate(incident_id, incident, action)
    approval_id = gate.get("approval_id")
    checkpoint_id = gate.get("checkpoint_id")
    status = "approval_pending" if gate.get("status") == "approval_required" else "completed"

    incident.update(
        {
            "status": status,
            "updated_at": time.time(),
            "evidence_ids": [ev.get("evidence_id") for ev in evidence if ev.get("evidence_id")],
            "hypothesis_id": hypothesis.get("hypothesis_id"),
            "action_id": action.get("action_id"),
            "approval_id": approval_id,
            "checkpoint_id": checkpoint_id,
            "approval_gate": gate,
        }
    )
    _store().put("incidents", incident_id, incident)
    skill = _build_skill({**incident, "hypothesis": hypothesis, "action": action})
    incident["skill_id"] = skill["skill_id"]
    _store().put("incidents", incident_id, incident)
    return get_incident(incident_id)


def create_incident_from_scenario(scenario_id: str, source: str = "web") -> Dict[str, Any]:
    scenario_map = {
        "payment_503_spike": "payment_503_spike.json",
        "coupon_504_timeout": "coupon_504_timeout.json",
        "order_429_rate_limit": "order_429_rate_limit.json",
    }
    filename = scenario_map.get(scenario_id, scenario_id)
    path = SCENARIO_DIR / filename
    if not path.exists():
        return {"status": "not_found", "scenario_id": scenario_id}
    data = json.loads(path.read_text(encoding="utf-8"))
    return create_incident(
        data.get("summary", ""),
        data.get("service", "payment-service"),
        data.get("severity", "p2"),
        data.get("environment", "prod"),
        source=source,
        alert_name=data.get("alert_name") or scenario_id,
    )


def list_scenarios() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for path in sorted(SCENARIO_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        data["scenario_id"] = path.stem
        out.append(data)
    return out


def list_incidents() -> List[Dict[str, Any]]:
    incidents = sorted(_store().list_bucket("incidents"), key=lambda x: x.get("created_at", 0), reverse=True)
    hypotheses = _store().read("hypotheses")
    actions = _store().read("actions")
    for incident in incidents:
        if incident.get("hypothesis_id") and incident["hypothesis_id"] in hypotheses:
            incident["hypothesis"] = hypotheses[incident["hypothesis_id"]]
        if incident.get("action_id") and incident["action_id"] in actions:
            incident["action"] = actions[incident["action_id"]]
    return incidents


def get_incident(incident_id: str) -> Dict[str, Any]:
    incident = _store().read("incidents").get(incident_id)
    if not incident:
        return {}
    evidence = [ev for ev in _store().list_bucket("evidence") if ev.get("incident_id") == incident_id]
    hypotheses = [h for h in _store().list_bucket("hypotheses") if h.get("incident_id") == incident_id]
    actions = [a for a in _store().list_bucket("actions") if a.get("incident_id") == incident_id]
    skills = [s for s in _store().list_bucket("skills") if s.get("incident_id") == incident_id]
    approvals = [
        a
        for a in _store().list_bucket("approvals")
        if a.get("incident_id") == incident_id or a.get("approval_id") == incident.get("approval_id")
    ]
    checkpoints = [
        c
        for c in _store().list_bucket("checkpoints")
        if c.get("incident_id") == incident_id or c.get("checkpoint_id") == incident.get("checkpoint_id")
    ]
    enriched = dict(incident)
    enriched.update(
        {
            "evidence": evidence,
            "hypotheses": hypotheses,
            "actions": actions,
            "skills": skills,
            "approvals": approvals,
            "checkpoints": checkpoints,
        }
    )
    if hypotheses:
        enriched["hypothesis"] = hypotheses[0]
    if actions:
        enriched["action"] = actions[0]
    return enriched


def get_events(incident_id: str) -> List[Dict[str, Any]]:
    return _store().read("events").get(incident_id, [])


def list_approvals() -> List[Dict[str, Any]]:
    return sorted(_store().list_bucket("approvals"), key=lambda x: x.get("created_at", 0), reverse=True)


def decide(approval_id: str, decision: str, approver: str = "operator", comment: str = "") -> Dict[str, Any]:
    result = _loads(runbook_approval_decision({"approval_id": approval_id, "decision": decision, "approver": approver, "comment": comment}))
    if result.get("status") == "approved":
        incidents = _store().read("incidents")
        for incident_id, incident in list(incidents.items()):
            if incident.get("approval_id") != approval_id:
                continue
            action = _store().read("actions").get(incident.get("action_id", ""), {})
            if action.get("action_type") == "rollback_canary":
                executed = _loads(
                    rollback_canary(
                        {
                            "incident_id": incident_id,
                            "service": incident.get("service", "payment-service"),
                            "target_revision": action.get("args", {}).get("target_revision", action.get("target_revision", "v2.3.0")),
                            "dry_run": False,
                            "approval_id": approval_id,
                        }
                    )
                )
            else:
                executed = execute_non_rollback_action(action, incident, approval_id)
            incident["status"] = "completed"
            incident["execution"] = executed
            incident["updated_at"] = time.time()
            incidents[incident_id] = incident
            # decide_approval() already records approval.resolved under the incident_id.
            record_event(incident_id, "action.executed", executed)
            if executed.get("status") in {"controlled_execution_succeeded", "mock_execution_succeeded", "demo_execution_recorded"}:
                from .tools import verify_recovery

                verification = _loads(verify_recovery({"service": incident.get("service", "payment-service"), "window": "2m"}))
                incident["verification"] = verification
                record_event(incident_id, "recovery.verified", verification)
        _store().write("incidents", incidents)
    return result


def list_checkpoints(incident_id: str) -> List[Dict[str, Any]]:
    incident = _store().read("incidents").get(incident_id, {})
    checkpoint_id = incident.get("checkpoint_id")
    return [
        c
        for c in _store().list_bucket("checkpoints")
        if c.get("incident_id") == incident_id or (checkpoint_id and c.get("checkpoint_id") == checkpoint_id)
    ]


def find_incident_id_for_approval(approval_id: str | None) -> str | None:
    if not approval_id:
        return None
    for incident_id, incident in _store().read("incidents").items():
        if incident.get("approval_id") == approval_id:
            return incident_id
    approval = _store().read("approvals").get(approval_id, {})
    return approval.get("incident_id")


def restore_last_checkpoint(incident_id: str) -> Dict[str, Any]:
    checkpoints = list_checkpoints(incident_id)
    if not checkpoints:
        return {"status": "not_found", "incident_id": incident_id}
    latest = sorted(checkpoints, key=lambda x: x.get("created_at", 0), reverse=True)[0]
    result = {"status": "restore_dry_run_succeeded", "incident_id": incident_id, "checkpoint_id": latest["checkpoint_id"], "message": "Restore adapter shell is ready. Real restore backend is not enabled."}
    record_event(incident_id, "checkpoint.restored", result)
    return result


def replay(incident_id: str) -> Dict[str, Any]:
    incident = get_incident(incident_id)
    if not incident:
        return {"status": "not_found", "incident_id": incident_id}
    return {"status": "replayed", "incident_id": incident_id, "summary": incident.get("summary"), "hypothesis": incident.get("hypothesis"), "action": incident.get("action")}


def get_skill(skill_id: str) -> Dict[str, Any]:
    return _store().read("skills").get(skill_id, {})


def list_skills() -> List[Dict[str, Any]]:
    return sorted(_store().list_bucket("skills"), key=lambda x: x.get("created_at", 0), reverse=True)


def daily_digest() -> Dict[str, Any]:
    incidents = list_incidents()
    pending = [a for a in list_approvals() if a.get("status") == "pending"]
    return {"status": "ok", "kind": "daily_health_digest", "incident_count": len(incidents), "pending_approvals": len(pending), "latest": incidents[:5]}


def weekly_digest() -> Dict[str, Any]:
    incidents = list_incidents()
    services: Dict[str, int] = {}
    categories: Dict[str, int] = {}
    for incident in incidents:
        services[incident.get("service", "unknown")] = services.get(incident.get("service", "unknown"), 0) + 1
        hyp = get_incident(incident["incident_id"]).get("hypothesis", {})
        cat = hyp.get("category", "unknown")
        categories[cat] = categories.get(cat, 0) + 1
    return {"status": "ok", "kind": "weekly_top_incidents", "incident_count": len(incidents), "top_services": services, "top_fault_categories": categories, "latest": incidents[:10]}


def model_summary(incident_id: str) -> Dict[str, Any]:
    incident = get_incident(incident_id)
    if not incident:
        return {"status": "not_found", "incident_id": incident_id}
    return RunbookModelClient().summarize_incident(incident)


def dashboard_summary() -> Dict[str, Any]:
    incidents = list_incidents()
    approvals = list_approvals()
    skills = list_skills()
    by_status: Dict[str, int] = {}
    by_service: Dict[str, int] = {}
    by_category: Dict[str, int] = {}
    for incident in incidents:
        by_status[incident.get("status", "unknown")] = by_status.get(incident.get("status", "unknown"), 0) + 1
        by_service[incident.get("service", "unknown")] = by_service.get(incident.get("service", "unknown"), 0) + 1
        hyp = get_incident(incident["incident_id"]).get("hypothesis", {})
        cat = hyp.get("category", "unknown")
        by_category[cat] = by_category.get(cat, 0) + 1
    return {
        "status": "ok",
        "totals": {
            "incidents": len(incidents),
            "pending_approvals": len([a for a in approvals if a.get("status") == "pending"]),
            "skills": len(skills),
            "completed": len([i for i in incidents if i.get("status") == "completed"]),
        },
        "by_status": by_status,
        "by_service": by_service,
        "by_category": by_category,
        "recent_incidents": incidents[:6],
        "recent_skills": skills[:6],
        "pending_approvals": [a for a in approvals if a.get("status") == "pending"][:6],
    }


def runtime_status() -> Dict[str, Any]:
    settings = load_settings()
    return {
        "status": "ok",
        "profile": "runbook-hermes",
        "store_dir": str(settings.store_dir),
        "model": {
            "enabled": settings.runbook_model_enabled,
            "provider": settings.runbook_model_provider,
            "model_name": settings.runbook_model_name,
            "base_url_configured": bool(settings.runbook_model_base_url),
            "api_key_configured": bool(settings.runbook_model_api_key),
        },
        "observability": {
            "obs_backend": settings.obs_backend,
            "deploy_backend": settings.deploy_backend,
            "trace_backend": settings.trace_backend,
            "trace_provider_kind": settings.trace_provider_kind,
            "prometheus_configured": bool(settings.prometheus_base_url),
            "loki_configured": bool(settings.loki_base_url),
            "trace_configured": bool(settings.trace_base_url),
            "demo_deploy_state_file": str(settings.demo_deploy_state_file),
            "demo_version_file": str(settings.demo_version_file),
        },
        "execution": {
            "rollback_backend_kind": settings.rollback_backend_kind,
            "controlled_execution_enabled": settings.controlled_execution_enabled,
            "action_execution_backend": settings.action_execution_backend,
            "action_execution_api_configured": bool(settings.action_execution_api_base_url),
        },
        "gateway": {
            "feishu_app_configured": bool(settings.feishu_app_id and settings.feishu_app_secret),
            "feishu_verification_token_configured": bool(settings.feishu_verification_token),
            "wecom_app_configured": bool(settings.wecom_corp_id and settings.wecom_secret),
        },
        "notes": [
            "Production rollback is disabled unless a specific rollback backend and controlled execution are configured.",
            "Feishu/WeCom adapters expose event and card-callback boundaries; online platform configuration is still required.",
            "Prometheus/Loki/Trace can run against the local payment demo or your own systems by changing backend environment variables.",
        ],
    }
