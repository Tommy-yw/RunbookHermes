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
    return _json(decide_approval(args.get("approval_id", ""), args.get("decision", "rejected"), args.get("approver", "operator"), args.get("comment", ""), args.get("second_confirmation", args.get("confirmation_token", ""))))


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
    execution_context = {
        "confirm_execution": args.get("confirm_execution"),
        "confirmation_token": args.get("confirmation_token") or args.get("confirm_token"),
        "audit_id": args.get("audit_id"),
    }
    return _json(execute_non_rollback_action(action, incident, args.get("approval_id"), execution_context=execution_context))


def _memory_enabled() -> bool:
    from .config import load_settings

    return bool(getattr(load_settings(), "runbook_memory_enabled", True))


def runbook_memory_recall(args: Dict[str, Any], **kwargs) -> str:
    """Recall fenced RunbookHermes memory for an incident, service or governance query."""
    if not _memory_enabled():
        return _json({"status": "disabled", "reason": "RUNBOOK_MEMORY_ENABLED=false"})
    from .memory import get_memory_manager

    query = args.get("query") or args.get("summary") or args.get("alert_name") or "incident"
    service = args.get("service", "")
    limit = _as_int(args.get("limit", 6), 6)
    return _json(get_memory_manager().recall_context(str(query), service=str(service or ""), limit=limit))


def runbook_memory_write(args: Dict[str, Any], **kwargs) -> str:
    """Write stable memory after safety scanning.

    For notebook writes pass notebook=MEMORY.md/USER.md/SERVICE_PROFILE.md/etc.
    For indexed memory writes pass kind/title/body/service/tags.
    """
    if not _memory_enabled():
        return _json({"status": "disabled", "reason": "RUNBOOK_MEMORY_ENABLED=false"})
    from .memory import get_memory_manager

    manager = get_memory_manager()
    notebook = args.get("notebook")
    if notebook:
        return _json(
            manager.append_notebook(
                str(notebook),
                str(args.get("title", "Runbook memory note")),
                str(args.get("body", args.get("content", ""))),
                source=str(args.get("source", "tool")),
            )
        )
    tags = args.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    return _json(
        manager.upsert_memory(
            kind=str(args.get("kind", "manual_note")),
            service=str(args.get("service", "")),
            title=str(args.get("title", "Runbook memory note")),
            body=str(args.get("body", args.get("content", ""))),
            tags=tags,
            source=str(args.get("source", "tool")),
            incident_id=str(args.get("incident_id", "")),
            memory_id=args.get("memory_id"),
            trust_score=float(args.get("trust_score", 0.55)),
        )
    )


def runbook_memory_feedback(args: Dict[str, Any], **kwargs) -> str:
    """Record operator feedback on a recalled memory hit so trust can evolve."""
    if not _memory_enabled():
        return _json({"status": "disabled", "reason": "RUNBOOK_MEMORY_ENABLED=false"})
    from .memory import get_memory_manager

    weight = args.get("weight")
    return _json(
        get_memory_manager().record_feedback(
            str(args.get("memory_id", "")),
            str(args.get("label", "helpful")),
            comment=str(args.get("comment", "")),
            weight=float(weight) if weight is not None else None,
        )
    )


def runbook_memory_status(args: Dict[str, Any] | None = None, **kwargs) -> str:
    """Return RunbookHermes memory architecture status and capacity warnings."""
    if not _memory_enabled():
        return _json({"status": "disabled", "reason": "RUNBOOK_MEMORY_ENABLED=false"})
    from .memory import get_memory_manager

    return _json(get_memory_manager().status())


def runbook_evolution_digest(args: Dict[str, Any] | None = None, **kwargs) -> str:
    """Summarize what RunbookHermes has learned and what should be promoted into runbooks."""
    if not _memory_enabled():
        return _json({"status": "disabled", "reason": "RUNBOOK_MEMORY_ENABLED=false"})
    from .memory import get_memory_manager

    args = args or {}
    return _json(get_memory_manager().evolution_digest(limit=_as_int(args.get("limit", 8), 8)))


def runbook_memory_reindex_skills(args: Dict[str, Any] | None = None, **kwargs) -> str:
    """Index SKILL.md files and generated runbook skills into local memory."""
    if not _memory_enabled():
        return _json({"status": "disabled", "reason": "RUNBOOK_MEMORY_ENABLED=false"})
    from .memory import get_memory_manager

    return _json(get_memory_manager().reindex_skills())


def runbook_memory_route(args: Dict[str, Any], **kwargs) -> str:
    """Route a chat/Feishu message to Hermes native memory or RunbookHermes domain memory."""
    from .memory_router import RunbookMemoryRouter

    router = RunbookMemoryRouter()
    decision = router.route_message(str(args.get("message", "")), source=str(args.get("source", "chat")), metadata=args.get("metadata") or {})
    result = {"status": "ok", "route": decision.to_dict()}
    if _as_bool(args.get("apply", False), False):
        result["result"] = router.apply(decision)
    return _json(result)


def runbook_publish_skill(args: Dict[str, Any], **kwargs) -> str:
    """Publish generated runbook content into Hermes official Skills directory."""
    from .skill_publisher import get_skill_publisher

    skill = {
        "skill_id": args.get("skill_id", ""),
        "incident_id": args.get("incident_id", ""),
        "service": args.get("service", ""),
        "title": args.get("title", "RunbookHermes skill"),
        "body": args.get("body", ""),
    }
    return _json(get_skill_publisher().publish_generated_skill(skill, incident={"incident_id": args.get("incident_id", ""), "service": args.get("service", "")}))


def runbook_skill_publish_status(args: Dict[str, Any] | None = None, **kwargs) -> str:
    """Return Hermes official Skills publisher status."""
    from .skill_publisher import get_skill_publisher

    return _json(get_skill_publisher().status())

def _rag_enabled() -> bool:
    from .config import load_settings

    return bool(getattr(load_settings(), "runbook_rag_enabled", True))


def runbook_rag_status(args: Dict[str, Any] | None = None, **kwargs) -> str:
    """Return RunbookHermes citation RAG index status."""
    if not _rag_enabled():
        return _json({"status": "disabled", "reason": "RUNBOOK_RAG_ENABLED=false"})
    from .rag import get_rag_index

    return _json(get_rag_index().status())


def runbook_rag_ingest_text(args: Dict[str, Any], **kwargs) -> str:
    """Ingest a text/markdown runbook document into the local citation RAG index."""
    if not _rag_enabled():
        return _json({"status": "disabled", "reason": "RUNBOOK_RAG_ENABLED=false"})
    from .rag import get_rag_index

    tags = args.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    return _json(
        get_rag_index().ingest_text(
            title=str(args.get("title", "Runbook document")),
            body=str(args.get("body", args.get("content", ""))),
            source=str(args.get("source", "tool")),
            service=str(args.get("service", "")),
            tags=tags,
            metadata=args.get("metadata") if isinstance(args.get("metadata"), dict) else {},
        )
    )


def runbook_rag_search(args: Dict[str, Any], **kwargs) -> str:
    """Search the local citation RAG index and return source/chunk citations."""
    if not _rag_enabled():
        return _json({"status": "disabled", "reason": "RUNBOOK_RAG_ENABLED=false"})
    from .rag import get_rag_index

    return _json(
        get_rag_index().search(
            query=str(args.get("query", "")),
            service=str(args.get("service", "")),
            limit=_as_int(args.get("limit", 5), 5),
            include_text=_as_bool(args.get("include_text", False), False),
        )
    )


def runbook_rag_context(args: Dict[str, Any], **kwargs) -> str:
    """Build a fenced RAG context block for RCA or action planning."""
    if not _rag_enabled():
        return _json({"status": "disabled", "reason": "RUNBOOK_RAG_ENABLED=false"})
    from .rag import get_rag_index

    return _json(get_rag_index().context(str(args.get("query", "")), service=str(args.get("service", "")), limit=_as_int(args.get("limit", 5), 5)))


def runbook_multimodal_analyze(args: Dict[str, Any], **kwargs) -> str:
    """Analyze Grafana screenshots, Feishu alert cards, log screenshots or dashboards as AIOps evidence."""
    from .multimodal import collect_multimodal_evidence

    refs = args.get("visual_refs") or args.get("images") or []
    if isinstance(refs, dict):
        refs = [refs]
    include_dashboard = args.get("include_dashboard_snapshot")
    return _json(
        {
            "status": "ok",
            "evidence": collect_multimodal_evidence(
                service=str(args.get("service", "payment-service")),
                summary=str(args.get("summary", "")),
                incident_id=str(args.get("incident_id", "")),
                visual_refs=refs,
                include_dashboard_snapshot=bool(include_dashboard) if include_dashboard is not None else None,
            ),
        }
    )


def runbook_topology_parse(args: Dict[str, Any], **kwargs) -> str:
    """Parse textual topology hints or diagram OCR into nodes and edges."""
    from .multimodal import parse_topology

    return _json(parse_topology(str(args.get("text", args.get("body", ""))), service=str(args.get("service", ""))))


def runbook_eval_benchmark(args: Dict[str, Any] | None = None, **kwargs) -> str:
    """Run deterministic RunbookHermes RCA/action/safety benchmark cases."""
    from .eval import run_eval

    args = args or {}
    case_ids = args.get("case_ids") or []
    if isinstance(case_ids, str):
        case_ids = [x.strip() for x in case_ids.split(",") if x.strip()]
    persist = args.get("persist")
    return _json(run_eval(case_ids=case_ids, persist=bool(persist) if persist is not None else None, model_assist=args.get("model_assist")))


def runbook_training_status(args: Dict[str, Any] | None = None, **kwargs) -> str:
    """Return RunbookAIOps training/RL/AutoPipeline status and Hermes RL handoff availability."""
    from .training import training_status

    return _json(training_status())


def runbook_training_build_dataset(args: Dict[str, Any] | None = None, **kwargs) -> str:
    """Build Hermes-compatible trajectories plus SFT/preference/reward datasets from incidents and benchmark cases."""
    from .training import build_dataset

    args = args or {}
    return _json(
        build_dataset(
            include_incidents=_as_bool(args.get("include_incidents", True), True),
            include_benchmark_cases=_as_bool(args.get("include_benchmark_cases", True), True),
            max_incidents=args.get("max_incidents"),
            min_reward=args.get("min_reward"),
        )
    )


def runbook_training_compress(args: Dict[str, Any] | None = None, **kwargs) -> str:
    """Compress RunbookAIOps trajectories and keep official Hermes trajectory_compressor handoff details."""
    from .training import compress_dataset

    args = args or {}
    return _json(
        compress_dataset(
            run_id=str(args.get("run_id") or "") or None,
            max_message_chars=args.get("max_message_chars"),
            use_hermes_compressor=_as_bool(args.get("use_hermes_compressor", False), False),
        )
    )


def runbook_training_export(args: Dict[str, Any] | None = None, **kwargs) -> str:
    """Export training datasets and generate Alibaba Cloud PAI/DashScope dry-run handoff templates."""
    from .training import export_dataset

    args = args or {}
    return _json(
        export_dataset(
            run_id=str(args.get("run_id") or "") or None,
            base_model=str(args.get("base_model") or "") or None,
            output_model_name=str(args.get("output_model_name") or "") or None,
        )
    )


def runbook_training_pipeline(args: Dict[str, Any] | None = None, **kwargs) -> str:
    """Run the local RunbookAIOps dataset -> compression -> export AutoPipeline in dry-run mode by default."""
    from .training import run_auto_pipeline

    args = args or {}
    return _json(
        run_auto_pipeline(
            include_incidents=_as_bool(args.get("include_incidents", True), True),
            include_benchmark_cases=_as_bool(args.get("include_benchmark_cases", True), True),
            max_incidents=args.get("max_incidents"),
            min_reward=args.get("min_reward"),
            base_model=str(args.get("base_model") or "") or None,
            output_model_name=str(args.get("output_model_name") or "") or None,
            use_hermes_compressor=_as_bool(args.get("use_hermes_compressor", False), False),
            dry_run=_as_bool(args.get("dry_run", True), True),
        )
    )
