from __future__ import annotations

from pathlib import Path
from runbook_hermes import tools

TOOLSET = "runbook-observability"


def _schema(name, description, properties, required=None):
    return {"name": name, "description": description, "parameters": {"type": "object", "properties": properties, "required": required or []}}


def register(ctx):
    common_service = {"type": "string", "description": "Service name", "default": "payment-service"}
    ctx.register_tool("prom_query", TOOLSET, _schema("prom_query", "Run a Prometheus query through the configured metrics backend.", {"service": common_service, "query": {"type": "string"}, "window": {"type": "string", "default": "15m"}}, ["service"]), tools.prom_query, description="Run Prometheus query", emoji="📈")
    ctx.register_tool("prom_top_anomalies", TOOLSET, _schema("prom_top_anomalies", "Return top metric anomalies for a service, including HTTP 503, 504 and 429 rates.", {"service": common_service, "window": {"type": "string", "default": "15m"}}, ["service"]), tools.prom_top_anomalies, description="Metric anomalies", emoji="📈")
    ctx.register_tool("loki_query", TOOLSET, _schema("loki_query", "Search service logs through Loki or the configured log backend.", {"service": common_service, "query": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"}, "limit": {"type": "integer", "default": 20}}, ["service"]), tools.loki_query, description="Log search", emoji="📜")
    ctx.register_tool("trace_search", TOOLSET, _schema("trace_search", "Search Jaeger traces for service errors or downstream latency.", {"service": common_service, "start": {"type": "string"}, "end": {"type": "string"}, "error_only": {"type": "boolean", "default": True}}, ["service"]), tools.trace_search, description="Trace search", emoji="🔎")
    ctx.register_tool("recent_deploys", TOOLSET, _schema("recent_deploys", "Return recent deploys for a service.", {"service": common_service, "since": {"type": "string", "default": "2h"}}, ["service"]), tools.recent_deploys, description="Recent deploys", emoji="🚀")
    ctx.register_tool("rollback_canary", TOOLSET, _schema("rollback_canary", "Rollback a canary deployment. Destructive when dry_run=false; approval is required.", {"service": common_service, "target_revision": {"type": "string"}, "dry_run": {"type": "boolean", "default": True}, "approval_id": {"type": "string"}, "checkpoint_id": {"type": "string"}}, ["service", "target_revision"]), tools.rollback_canary, description="Rollback canary", emoji="🛡️")
    ctx.register_tool("verify_recovery", TOOLSET, _schema("verify_recovery", "Verify whether HTTP 503 recovery signals improved after a controlled demo rollback.", {"service": common_service, "window": {"type": "string", "default": "2m"}}, ["service"]), tools.verify_recovery, description="Verify recovery", emoji="✅")
    ctx.register_tool("incident_rca_guard", TOOLSET, _schema("incident_rca_guard", "Validate or generate an RCA hypothesis from evidence.", {"service": common_service, "evidence": {"type": "array", "items": {"type": "object"}}}, ["service", "evidence"]), tools.incident_rca_guard, description="RCA guard", emoji="🧭")
    ctx.register_tool("action_policy_guard", TOOLSET, _schema("action_policy_guard", "Generate policy-checked actions from a root-cause hypothesis.", {"service": common_service, "hypothesis": {"type": "object"}}, ["service", "hypothesis"]), tools.action_policy_guard, description="Action policy", emoji="⚖️")
    ctx.register_tool("runbook_approval_decision", TOOLSET, _schema("runbook_approval_decision", "Approve or reject a pending RunbookHermes destructive action.", {"approval_id": {"type": "string"}, "decision": {"type": "string", "enum": ["approved", "rejected"]}, "approver": {"type": "string"}, "comment": {"type": "string"}}, ["approval_id", "decision"]), tools.runbook_approval_decision, description="Approval decision", emoji="✅")
    ctx.register_tool("execute_controlled_action", TOOLSET, _schema("execute_controlled_action", "Execute or route a non-rollback controlled action through the configured executor shell. Disabled by default unless ACTION_EXECUTION_BACKEND is configured.", {"service": common_service, "incident_id": {"type": "string"}, "action_type": {"type": "string"}, "title": {"type": "string"}, "risk_level": {"type": "string"}, "approval_id": {"type": "string"}, "action_args": {"type": "object"}}, ["service", "action_type"]), tools.execute_controlled_action, description="Execute controlled action", emoji="🧰")
    skill = Path(__file__).resolve().parents[2] / "skills" / "runbooks" / "payment-503-spike" / "SKILL.md"
    if skill.exists():
        ctx.register_skill("payment-503-spike", skill, "Payment service HTTP 503 spike after release triage runbook")
