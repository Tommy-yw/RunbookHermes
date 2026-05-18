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
from .multimodal import collect_multimodal_evidence
from .resources import resource_path
from .service_profiles import compact_service_profile, load_service_profile
from .store import Store, get_store
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


SCENARIO_DIR = resource_path("data", "runbook_mock", "scenarios")


def _store() -> Store:
    return get_store(load_settings())


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


def collect_evidence(service: str, summary: str = "", alert_name: str = "", incident_id: str = "", visual_refs: List[Dict[str, Any]] | None = None) -> List[Dict[str, Any]]:
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
    visual_evidence = collect_multimodal_evidence(
        service=service,
        summary=summary,
        incident_id=incident_id,
        visual_refs=visual_refs or [],
    )
    evidence.extend(visual_evidence)
    for idx, ev in enumerate(evidence, start=1):
        ev.setdefault("evidence_id", f"ev_{scenario}_{idx}")
        ev.setdefault("scenario", scenario)
    return evidence


def _memory_feature_enabled() -> bool:
    return bool(getattr(load_settings(), "runbook_memory_enabled", True))


def _recall_memory_context(service: str, summary: str, alert_name: str | None, severity: str, environment: str) -> Dict[str, Any]:
    if not _memory_feature_enabled():
        return {"status": "disabled"}
    try:
        from .memory import get_memory_manager

        settings = load_settings()
        query = " ".join(str(x or "") for x in [service, summary, alert_name, severity, environment]).strip()
        return get_memory_manager().recall_context(query=query or service, service=service, limit=settings.runbook_memory_context_limit)
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def _rag_feature_enabled() -> bool:
    return bool(getattr(load_settings(), "runbook_rag_enabled", True))


def _recall_rag_context(service: str, summary: str, alert_name: str | None, severity: str, environment: str) -> Dict[str, Any]:
    if not _rag_feature_enabled():
        return {"status": "disabled"}
    try:
        from .rag import get_rag_index

        settings = load_settings()
        query = " ".join(str(x or "") for x in [service, summary, alert_name, severity, environment]).strip()
        return get_rag_index().context(query=query or service, service=service, limit=settings.runbook_rag_context_limit)
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def _learning_summary(result: Dict[str, Any]) -> Dict[str, Any]:
    learned = result.get("learned") or []
    learned_items: List[Dict[str, Any]] = []
    for item in learned:
        if not isinstance(item, dict):
            continue
        mem = item.get("memory") or {}
        learned_items.append({"status": item.get("status"), "memory_id": mem.get("memory_id"), "kind": mem.get("kind"), "title": mem.get("title")})
    return {"status": result.get("status"), "incident_id": result.get("incident_id"), "learned_count": len(learned_items), "learned": learned_items}


def _learn_memory_from_incident(incident: Dict[str, Any], source: str) -> Dict[str, Any]:
    if not _memory_feature_enabled():
        return {"status": "disabled"}
    try:
        from .memory import get_memory_manager

        return get_memory_manager().learn_from_incident(incident, source=source)
    except Exception as exc:
        return {"status": "error", "error": str(exc), "incident_id": incident.get("incident_id")}


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
        "service": incident.get("service", ""),
        "body": body,
        "created_at": time.time(),
    }
    _store().put("skills", skill_id, item)
    record_event(incident["incident_id"], "skill.generated", item)
    return item



def _publish_skill_to_hermes(skill: Dict[str, Any], incident: Dict[str, Any]) -> Dict[str, Any]:
    settings = load_settings()
    if not getattr(settings, "runbook_skill_publish_enabled", True):
        return {"status": "disabled", "reason": "RUNBOOK_SKILL_PUBLISH_ENABLED=false"}
    try:
        from .skill_publisher import get_skill_publisher

        published = get_skill_publisher().publish_generated_skill(skill, incident=incident)
        if published.get("status") == "published" and incident.get("incident_id"):
            record_event(incident["incident_id"], "skill.published_to_hermes", published)
        return published
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


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
    visual_refs: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    incident_id = _short_id("inc")
    now = time.time()
    alert_name = alert_name or _scenario_key(summary)
    service_profile = load_service_profile(service)
    incident = {
        "incident_id": incident_id,
        "service": service,
        "severity": severity,
        "environment": environment,
        "summary": summary or f"{service} HTTP 503 spike after release",
        "alert_name": alert_name,
        "source": source,
        "status": "collecting",
        "service_profile": compact_service_profile(service_profile),
        "created_at": now,
        "updated_at": now,
    }
    _store().put("incidents", incident_id, incident)
    record_event(incident_id, "incident.created", incident)

    memory_context = _recall_memory_context(service, incident["summary"], alert_name, severity, environment)
    if memory_context.get("status") != "disabled":
        incident["memory_context"] = {
            "status": memory_context.get("status"),
            "query": memory_context.get("query"),
            "hits": memory_context.get("hits", []),
            "snr": memory_context.get("snr"),
            "rendered": memory_context.get("rendered", ""),
        }
        _store().put("incidents", incident_id, incident)
        record_event(
            incident_id,
            "memory.recalled",
            {
                "status": memory_context.get("status"),
                "count": len(memory_context.get("hits", [])),
                "hits": [
                    {"memory_id": h.get("memory_id"), "kind": h.get("kind"), "title": h.get("title"), "score": h.get("score")}
                    for h in memory_context.get("hits", [])[:6]
                ],
                "snr": memory_context.get("snr"),
            },
        )

    rag_context = _recall_rag_context(service, incident["summary"], alert_name, severity, environment)
    if rag_context.get("status") != "disabled":
        incident["rag_context"] = {
            "status": rag_context.get("status"),
            "query": rag_context.get("query"),
            "hits": rag_context.get("hits", []),
            "rendered": rag_context.get("rendered", ""),
        }
        _store().put("incidents", incident_id, incident)
        record_event(
            incident_id,
            "rag.recalled",
            {
                "status": rag_context.get("status"),
                "count": len(rag_context.get("hits", [])),
                "hits": [
                    {"doc_id": h.get("doc_id"), "chunk_id": h.get("chunk_id"), "title": h.get("title"), "citation": h.get("citation"), "score": h.get("score")}
                    for h in rag_context.get("hits", [])[:6]
                ],
            },
        )

    evidence = collect_evidence(service, summary=summary, alert_name=alert_name, incident_id=incident_id, visual_refs=visual_refs)
    for ev in evidence:
        ev = dict(ev)
        ev.setdefault("evidence_id", _short_id("ev"))
        ev["incident_id"] = incident_id
        _store().put("evidence", ev["evidence_id"], ev)
    record_event(incident_id, "evidence.collected", {"count": len(evidence), "items": evidence})

    rca = _loads(incident_rca_guard({"service": service, "summary": incident["summary"], "evidence": evidence, "memory_context": memory_context, "rag_context": rag_context, "service_profile": service_profile}))
    hypothesis = rca.get("hypothesis", {})
    hypothesis.setdefault("hypothesis_id", _short_id("hyp"))
    hypothesis["incident_id"] = incident_id
    _store().put("hypotheses", hypothesis["hypothesis_id"], hypothesis)
    record_event(incident_id, "hypothesis.generated", hypothesis)

    policy = _loads(action_policy_guard({"service": service, "hypothesis": hypothesis, "evidence": evidence, "memory_context": memory_context, "rag_context": rag_context, "service_profile": service_profile}))
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
    skill_incident = {**incident, "hypothesis": hypothesis, "action": action}
    skill = _build_skill(skill_incident)
    published_skill = _publish_skill_to_hermes(skill, skill_incident)
    incident["skill_id"] = skill["skill_id"]
    incident["published_skill"] = published_skill
    memory_learning = _learn_memory_from_incident(
        {**incident, "evidence": evidence, "hypothesis": hypothesis, "action": action},
        source="incident_created",
    )
    if memory_learning.get("status") != "disabled":
        incident["memory_learning"] = _learning_summary(memory_learning)
        record_event(incident_id, "memory.learned", incident["memory_learning"])
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
    if not path.suffix:
        path = path.with_suffix(".json")
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


def decide(approval_id: str, decision: str, approver: str = "operator", comment: str = "", execution_context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    execution_context = execution_context or {}
    confirmation = execution_context.get("second_confirmation") or execution_context.get("confirmation_token") or execution_context.get("confirm_token") or ""
    result = _loads(runbook_approval_decision({"approval_id": approval_id, "decision": decision, "approver": approver, "comment": comment, "second_confirmation": confirmation}))
    updated_incident_ids: List[str] = []
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
                executed = execute_non_rollback_action(action, incident, approval_id, execution_context=execution_context)
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
            updated_incident_ids.append(incident_id)
        _store().write("incidents", incidents)
    incident_id_for_learning = find_incident_id_for_approval(approval_id)
    if incident_id_for_learning and incident_id_for_learning not in updated_incident_ids:
        updated_incident_ids.append(incident_id_for_learning)
    for incident_id in updated_incident_ids:
        memory_learning = _learn_memory_from_incident(get_incident(incident_id), source="approval_decision")
        if memory_learning.get("status") != "disabled":
            record_event(incident_id, "memory.learned", _learning_summary(memory_learning))
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


def memory_status() -> Dict[str, Any]:
    if not _memory_feature_enabled():
        return {"status": "disabled"}
    from .memory import get_memory_manager

    return get_memory_manager().status()


def search_memory(query: str, service: str = "", limit: int = 8, include_body: bool = False) -> Dict[str, Any]:
    if not _memory_feature_enabled():
        return {"status": "disabled"}
    from .memory import get_memory_manager

    return get_memory_manager().search(query=query, service=service, limit=limit, include_body=include_body)


def write_memory(
    kind: str,
    title: str,
    body: str,
    service: str = "",
    tags: List[str] | None = None,
    source: str = "api",
    incident_id: str = "",
    notebook: str | None = None,
) -> Dict[str, Any]:
    if not _memory_feature_enabled():
        return {"status": "disabled"}
    from .memory import get_memory_manager

    manager = get_memory_manager()
    if notebook:
        return manager.append_notebook(notebook, title, body, source=source)
    return manager.upsert_memory(kind=kind, service=service, title=title, body=body, tags=tags or [], source=source, incident_id=incident_id)


def memory_feedback(memory_id: str, label: str, comment: str = "", weight: float | None = None) -> Dict[str, Any]:
    if not _memory_feature_enabled():
        return {"status": "disabled"}
    from .memory import get_memory_manager

    return get_memory_manager().record_feedback(memory_id, label, comment=comment, weight=weight)


def memory_notebooks() -> Dict[str, Any]:
    if not _memory_feature_enabled():
        return {"status": "disabled"}
    from .memory import get_memory_manager

    return get_memory_manager().read_notebooks()


def memory_evolution_digest(limit: int = 8) -> Dict[str, Any]:
    if not _memory_feature_enabled():
        return {"status": "disabled"}
    from .memory import get_memory_manager

    return get_memory_manager().evolution_digest(limit=limit)


def memory_reindex_skills() -> Dict[str, Any]:
    if not _memory_feature_enabled():
        return {"status": "disabled"}
    from .memory import get_memory_manager

    return get_memory_manager().reindex_skills()


def incident_memory_context(incident_id: str) -> Dict[str, Any]:
    incident = get_incident(incident_id)
    if not incident:
        return {"status": "not_found", "incident_id": incident_id}
    return incident.get("memory_context") or {"status": "empty", "incident_id": incident_id}



def route_memory_message(message: str, source: str = "chat", metadata: Dict[str, Any] | None = None, apply: bool = True) -> Dict[str, Any]:
    settings = load_settings()
    if not getattr(settings, "runbook_memory_router_enabled", True):
        return {"status": "disabled", "reason": "RUNBOOK_MEMORY_ROUTER_ENABLED=false"}
    from .memory_router import RunbookMemoryRouter

    router = RunbookMemoryRouter()
    decision = router.route_message(message, source=source, metadata=metadata or {})
    result: Dict[str, Any] = {"status": "ok", "route": decision.to_dict()}
    if not apply:
        return result
    if decision.action == "create_incident":
        incident = create_incident(
            decision.message,
            service=decision.service or "payment-service",
            severity=decision.severity if decision.severity != "info" else "p2",
            environment=decision.environment or "prod",
            source=source,
            alert_name=(metadata or {}).get("alert_name") or "feishu_chat_incident",
        )
        result["incident"] = incident
        if incident.get("incident_id"):
            record_event(incident["incident_id"], "memory.router.created_incident", decision.to_dict())
        return result
    result["result"] = router.apply(decision)
    return result


def memory_bridge_status() -> Dict[str, Any]:
    from .hermes_bridge import bridge_status

    return bridge_status()


def skill_publisher_status() -> Dict[str, Any]:
    from .skill_publisher import get_skill_publisher

    return get_skill_publisher().status()


def publish_skill(skill_id: str = "", title: str = "", body: str = "", service: str = "", incident_id: str = "") -> Dict[str, Any]:
    from .skill_publisher import get_skill_publisher

    skill = get_skill(skill_id) if skill_id else {}
    if not skill:
        skill = {"skill_id": skill_id, "incident_id": incident_id, "title": title or "RunbookHermes skill", "body": body, "service": service}
    incident = get_incident(skill.get("incident_id") or incident_id) if (skill.get("incident_id") or incident_id) else {"service": service}
    return get_skill_publisher().publish_generated_skill(skill, incident=incident)


def rag_status() -> Dict[str, Any]:
    if not _rag_feature_enabled():
        return {"status": "disabled"}
    from .rag import get_rag_index

    return get_rag_index().status()


def rag_documents(limit: int = 50) -> Dict[str, Any]:
    if not _rag_feature_enabled():
        return {"status": "disabled"}
    from .rag import get_rag_index

    return get_rag_index().list_documents(limit=limit)


def rag_ingest_text(
    title: str,
    body: str,
    source: str = "api",
    service: str = "",
    tags: List[str] | None = None,
    metadata: Dict[str, Any] | None = None,
    acl_tags: List[str] | None = None,
    permission_scope: str = "public",
    expires_at: float | None = None,
) -> Dict[str, Any]:
    if not _rag_feature_enabled():
        return {"status": "disabled"}
    from .rag import get_rag_index

    return get_rag_index().ingest_text(
        title=title,
        body=body,
        source=source,
        service=service,
        tags=tags or [],
        metadata=metadata or {},
        acl_tags=acl_tags or [],
        permission_scope=permission_scope,
        expires_at=expires_at,
    )


def rag_ingest_path(path: str, service: str = "", tags: List[str] | None = None, recursive: bool = True, acl_tags: List[str] | None = None, permission_scope: str = "public") -> Dict[str, Any]:
    if not _rag_feature_enabled():
        return {"status": "disabled"}
    from .rag import get_rag_index

    p = Path(path)
    if p.is_dir():
        return get_rag_index().ingest_directory(p, service=service, tags=tags or [], recursive=recursive, acl_tags=acl_tags or [], permission_scope=permission_scope)
    return get_rag_index().ingest_path(p, service=service, tags=tags or [], acl_tags=acl_tags or [], permission_scope=permission_scope)


def rag_search(query: str, service: str = "", limit: int = 5, include_text: bool = False, permission_scope: str = "", acl: List[str] | str | None = None) -> Dict[str, Any]:
    if not _rag_feature_enabled():
        return {"status": "disabled"}
    from .rag import get_rag_index

    return get_rag_index().search(query=query, service=service, limit=limit, include_text=include_text, permission_scope=permission_scope, acl=acl)


def rag_context(query: str, service: str = "", limit: int = 5, permission_scope: str = "", acl: List[str] | str | None = None) -> Dict[str, Any]:
    if not _rag_feature_enabled():
        return {"status": "disabled"}
    from .rag import get_rag_index

    return get_rag_index().context(query=query, service=service, limit=limit, permission_scope=permission_scope, acl=acl)


def rag_evaluate(queries: List[Dict[str, Any]], service: str = "", limit: int = 5, permission_scope: str = "", acl: List[str] | str | None = None) -> Dict[str, Any]:
    if not _rag_feature_enabled():
        return {"status": "disabled"}
    from .rag import get_rag_index

    normalized: List[Dict[str, Any]] = []
    for item in queries or []:
        case = dict(item)
        if service and not case.get("service"):
            case["service"] = service
        if permission_scope and not case.get("permission_scope"):
            case["permission_scope"] = permission_scope
        if acl and not case.get("acl"):
            case["acl"] = acl
        normalized.append(case)
    return get_rag_index().evaluate_queries(normalized, limit=limit)


def multimodal_analyze(service: str = "", summary: str = "", visual_refs: List[Dict[str, Any]] | None = None, include_dashboard_snapshot: bool | None = None) -> Dict[str, Any]:
    evidence = collect_multimodal_evidence(service=service or "payment-service", summary=summary, visual_refs=visual_refs or [], include_dashboard_snapshot=include_dashboard_snapshot)
    return {"status": "ok", "service": service or "payment-service", "evidence_count": len(evidence), "evidence": evidence}


def attach_multimodal_evidence(incident_id: str, visual_refs: List[Dict[str, Any]] | None = None, include_dashboard_snapshot: bool | None = None) -> Dict[str, Any]:
    incident = get_incident(incident_id)
    if not incident:
        return {"status": "not_found", "incident_id": incident_id}
    evidence = collect_multimodal_evidence(
        service=incident.get("service", "payment-service"),
        summary=incident.get("summary", ""),
        incident_id=incident_id,
        visual_refs=visual_refs or [],
        include_dashboard_snapshot=include_dashboard_snapshot,
    )
    for idx, ev in enumerate(evidence, start=1):
        ev = dict(ev)
        ev["incident_id"] = incident_id
        ev.setdefault("evidence_id", _short_id("ev_visual"))
        # Avoid overwriting an existing evidence item when generated IDs collide.
        if _store().read("evidence").get(ev["evidence_id"]):
            ev["evidence_id"] = _short_id("ev_visual")
        _store().put("evidence", ev["evidence_id"], ev)
    current_ids = list(incident.get("evidence_ids") or [])
    for ev in evidence:
        if ev.get("evidence_id") and ev.get("evidence_id") not in current_ids:
            current_ids.append(ev.get("evidence_id"))
    incident["evidence_ids"] = current_ids
    incident["updated_at"] = time.time()
    _store().put("incidents", incident_id, incident)
    record_event(incident_id, "multimodal.evidence_attached", {"count": len(evidence), "items": evidence})
    return {"status": "ok", "incident_id": incident_id, "evidence_count": len(evidence), "evidence": evidence}


def eval_cases() -> Dict[str, Any]:
    from .eval import list_eval_cases

    return list_eval_cases()


def run_benchmark_eval(case_ids: List[str] | None = None, persist: bool | None = None, model_assist: bool | None = None) -> Dict[str, Any]:
    from .eval import run_eval

    return run_eval(case_ids=case_ids, persist=persist, model_assist=model_assist)


def latest_eval_runs(limit: int = 10) -> Dict[str, Any]:
    return {"status": "ok", "runs": sorted(_store().list_bucket("eval_runs"), key=lambda x: x.get("created_at", 0), reverse=True)[:limit]}


def save_eval_postmortem(case_id: str = "", incident_id: str = "", final_score: float | None = None, reviewer: str = "operator", notes: str = "", labels: List[str] | None = None) -> Dict[str, Any]:
    from .eval import save_postmortem_score

    return save_postmortem_score(case_id=case_id, incident_id=incident_id, final_score=final_score, reviewer=reviewer, notes=notes, labels=labels or [])


def latest_eval_postmortems(limit: int = 20) -> Dict[str, Any]:
    from .eval import list_postmortem_scores

    return list_postmortem_scores(limit=limit)




def training_status() -> Dict[str, Any]:
    from .training import training_status as _training_status

    return _training_status()


def training_build_dataset(
    include_incidents: bool = True,
    include_benchmark_cases: bool = True,
    max_incidents: int | None = None,
    min_reward: float | None = None,
) -> Dict[str, Any]:
    from .training import build_dataset

    return build_dataset(
        include_incidents=include_incidents,
        include_benchmark_cases=include_benchmark_cases,
        max_incidents=max_incidents,
        min_reward=min_reward,
    )


def training_compress_dataset(run_id: str = "", max_message_chars: int | None = None, use_hermes_compressor: bool = False) -> Dict[str, Any]:
    from .training import compress_dataset

    return compress_dataset(run_id=run_id or None, max_message_chars=max_message_chars, use_hermes_compressor=use_hermes_compressor)


def training_export_dataset(run_id: str = "", base_model: str = "", output_model_name: str = "") -> Dict[str, Any]:
    from .training import export_dataset

    return export_dataset(run_id=run_id or None, base_model=base_model or None, output_model_name=output_model_name or None)


def training_run_pipeline(
    include_incidents: bool = True,
    include_benchmark_cases: bool = True,
    max_incidents: int | None = None,
    min_reward: float | None = None,
    base_model: str = "",
    output_model_name: str = "",
    use_hermes_compressor: bool = False,
    dry_run: bool = True,
) -> Dict[str, Any]:
    from .training import run_auto_pipeline

    return run_auto_pipeline(
        include_incidents=include_incidents,
        include_benchmark_cases=include_benchmark_cases,
        max_incidents=max_incidents,
        min_reward=min_reward,
        base_model=base_model or None,
        output_model_name=output_model_name or None,
        use_hermes_compressor=use_hermes_compressor,
        dry_run=dry_run,
    )




def training_external_launch(run_id: str = "", confirmation_token: str = "") -> Dict[str, Any]:
    from .training import external_launch_training

    return external_launch_training(run_id=run_id, confirmation_token=confirmation_token)


def training_runs(limit: int = 10) -> Dict[str, Any]:
    from .training import list_training_runs

    return list_training_runs(limit=limit)


def training_datasets(limit: int = 20) -> Dict[str, Any]:
    from .training import list_datasets

    return list_datasets(limit=limit)


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
        "memory": memory_evolution_digest(limit=4) if _memory_feature_enabled() else {"status": "disabled"},
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
        "memory": {
            "enabled": settings.runbook_memory_enabled,
            "memory_dir": str(settings.runbook_memory_dir),
            "context_limit": settings.runbook_memory_context_limit,
            "hrr_dim": settings.runbook_memory_hrr_dim,
            "external_provider": settings.runbook_memory_external_provider,
            "external_mode": settings.runbook_memory_external_mode,
            "bridge_enabled": settings.runbook_memory_bridge_enabled,
            "bridge_provider_name": settings.runbook_memory_bridge_provider_name,
            "router_enabled": settings.runbook_memory_router_enabled,
            "feishu_router_enabled": settings.runbook_feishu_memory_router_enabled,
            "skill_publish_enabled": settings.runbook_skill_publish_enabled,
            "skill_publish_category": settings.runbook_skill_publish_category,
        },
        "rag": {
            "enabled": settings.runbook_rag_enabled,
            "rag_dir": str(settings.runbook_rag_dir),
            "context_limit": settings.runbook_rag_context_limit,
            "chunk_chars": settings.runbook_rag_chunk_chars,
            "chunk_overlap": settings.runbook_rag_chunk_overlap,
        },
        "multimodal": {
            "enabled": settings.runbook_multimodal_enabled,
            "collect_dashboards": settings.runbook_multimodal_collect_dashboards,
            "use_hermes_vision": settings.runbook_multimodal_use_hermes_vision,
        },
        "api_auth": {
            "enabled": settings.runbook_api_auth_enabled,
            "header": settings.runbook_api_auth_header,
            "token_configured": bool(settings.runbook_api_token),
            "read_only_token_configured": bool(settings.runbook_api_read_only_token),
        },
        "eval": {
            "persist_default": settings.runbook_eval_persist_default,
            "model_assist_enabled": settings.runbook_eval_model_assist_enabled,
            "model_assist_weight": settings.runbook_eval_model_assist_weight,
            "model_interface": "RunbookModelClient / RUNBOOK_MODEL_* (same interface as RunbookAIOps)",
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
            "action_execution_allowed_operations": list(settings.action_execution_allowed_operations),
            "action_execution_require_second_confirmation": bool(settings.action_execution_require_second_confirmation),
            "action_execution_confirmation_token_configured": bool(settings.action_execution_confirmation_token),
        },
        "gateway": {
            "feishu_app_configured": bool(settings.feishu_app_id and settings.feishu_app_secret),
            "feishu_verification_token_configured": bool(settings.feishu_verification_token),
            "feishu_encrypt_key_configured": bool(settings.feishu_encrypt_key),
            "wecom_app_configured": bool(settings.wecom_corp_id and settings.wecom_secret),
            "wecom_token_configured": bool(settings.wecom_token),
            "wecom_encoding_aes_key_configured": bool(settings.wecom_encoding_aes_key),
            "strict_security": bool(settings.runbook_gateway_strict_security),
            "replay_window_seconds": settings.runbook_gateway_replay_window_seconds,
        },
        "notes": [
            "API auth is enabled by default; configure RUNBOOK_API_TOKEN or explicitly disable auth only for isolated local demos.",
            "Production rollback is disabled unless a specific rollback backend and controlled execution are configured.",
            "Non-rollback write actions require backend allowlist, approved approval_id, audit_id and second confirmation.",
            "RAG path ingestion is sandboxed by RUNBOOK_RAG_ALLOWED_ROOTS.",
            "Feishu/WeCom gateway callbacks verify provider-native tokens/signatures/encryption and replay windows when configured.",
            "Prometheus/Loki/Trace can run against the local payment demo or your own systems by changing backend environment variables.",
        ],
    }
