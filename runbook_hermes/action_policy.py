from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from .memory_kinds import ACTION_GUARDRAIL_KINDS, normalize_memory_kind
from .service_profiles import first_present, load_service_profile


def _memory_guardrails(args: Dict[str, Any]) -> Dict[str, Any]:
    ctx = args.get("memory_context") or {}
    hits = ctx.get("hits") if isinstance(ctx, dict) else []
    guardrails: List[str] = []
    memory_ids: List[str] = []
    for hit in (hits or [])[:6]:
        if not isinstance(hit, dict):
            continue
        kind = normalize_memory_kind(hit.get("kind", ""))
        if kind not in ACTION_GUARDRAIL_KINDS:
            continue
        mid = hit.get("memory_id")
        if mid:
            memory_ids.append(str(mid))
        title = hit.get("title") or hit.get("snippet") or kind
        guardrails.append(f"{kind}: {title}")
    return {"memory_ids": memory_ids, "guardrails": guardrails}


def _attach_memory_policy(result: Dict[str, Any], memory_policy: Dict[str, Any]) -> Dict[str, Any]:
    if not memory_policy.get("memory_ids"):
        return result
    result = dict(result)
    result["memory_policy"] = {
        "used_as": "governance_context",
        "memory_ids": memory_policy["memory_ids"],
        "guardrails": memory_policy["guardrails"],
        "safety": "memory can tighten policy but cannot bypass approvals/checkpoints",
    }
    for action in result.get("actions") or []:
        if isinstance(action, dict):
            action.setdefault("policy_context", {})["memory_ids"] = memory_policy["memory_ids"]
            action.setdefault("policy_context", {})["guardrails"] = memory_policy["guardrails"]
            if action.get("risk_level") != "read_only":
                action["requires_approval"] = True
                action["checkpoint_before_execution"] = True
    return result


def _iter_evidence(args: Dict[str, Any]) -> List[Dict[str, Any]]:
    evidence = args.get("evidence") or []
    if isinstance(evidence, list):
        return [e for e in evidence if isinstance(e, dict)]
    return []


def _revision_from_evidence(evidence: List[Dict[str, Any]]) -> Tuple[str, str]:
    current = ""
    previous = ""
    for item in evidence:
        if str(item.get("source", "")).lower() != "deploy":
            continue
        current = first_present(current, item.get("version"), item.get("current_revision"), item.get("current_version"))
        previous = first_present(previous, item.get("previous_version"), item.get("previous_revision"), item.get("target_revision"))
        if current and previous:
            return current, previous
    return current, previous


def _format_title(template: str, **values: str) -> str:
    try:
        return template.format(**values)
    except Exception:
        return template


def _profile_action_rule(profile: Dict[str, Any], category: str) -> Dict[str, Any]:
    rules = profile.get("action_rules") or {}
    if isinstance(rules, dict) and isinstance(rules.get(category), dict):
        return dict(rules[category])
    return {}


def _profile_context(profile: Dict[str, Any]) -> Dict[str, Any]:
    rollback = profile.get("rollback") or {}
    return {
        "service_profile": {
            "service": profile.get("service"),
            "owner": profile.get("owner"),
            "rollback_backend_hint": rollback.get("preferred_backend"),
            "rollback_workload": rollback.get("kubernetes_workload_name") or rollback.get("argocd_app"),
            "policy_source": "data/runbook_profiles/services.json",
        }
    }


def _rollback_action(service: str, profile: Dict[str, Any], evidence: List[Dict[str, Any]], rule: Dict[str, Any]) -> Dict[str, Any]:
    rollback = profile.get("rollback") or {}
    current_revision, evidence_previous = _revision_from_evidence(evidence)
    target_revision = first_present(evidence_previous, rollback.get("safe_previous_revision"), rule.get("target_revision"), "previous")
    current_revision = first_present(current_revision, "current")
    title = _format_title(
        rule.get("title_template") or "Rollback {service} canary from {current_revision} to {target_revision}",
        service=service,
        current_revision=current_revision,
        target_revision=target_revision,
    )
    args = {
        "service": service,
        "target_revision": target_revision,
        "current_revision": current_revision,
        "preferred_backend": rollback.get("preferred_backend"),
        "kubernetes_namespace": rollback.get("kubernetes_namespace"),
        "kubernetes_workload_kind": rollback.get("kubernetes_workload_kind"),
        "kubernetes_workload_name": rollback.get("kubernetes_workload_name"),
        "kubernetes_container": rollback.get("kubernetes_container"),
        "image_repository": rollback.get("image_repository"),
        "argocd_app": rollback.get("argocd_app"),
    }
    return {
        "action_id": "act_rollback_canary",
        "action_type": "rollback_canary",
        "title": title,
        "risk_level": rule.get("risk_level", "destructive"),
        "requires_approval": bool(rollback.get("requires_approval", True)),
        "checkpoint_before_execution": bool(rollback.get("requires_checkpoint", True)),
        "dry_run_default": True,
        "args": {k: v for k, v in args.items() if v not in (None, "")},
        "policy_context": _profile_context(profile),
    }


def _write_action(service: str, profile: Dict[str, Any], category: str, rule: Dict[str, Any]) -> Dict[str, Any]:
    target_service = first_present(rule.get("target_service"), service)
    action_type = first_present(rule.get("action_type"), f"manual_{category}")
    title = _format_title(rule.get("title_template") or f"Apply guarded remediation for {category}", service=service, target_service=target_service)
    return {
        "action_id": f"act_{action_type}",
        "action_type": action_type,
        "title": title,
        "risk_level": rule.get("risk_level", "write_safe"),
        "requires_approval": True,
        "checkpoint_before_execution": True,
        "dry_run_default": True,
        "args": {"service": target_service, "category": category},
        "policy_context": _profile_context(profile),
    }


def _observe_action(service: str, category: str) -> Dict[str, Any]:
    metric = "HTTP 503 rate and p95 latency" if category == "deploy_db_regression" else "error rate and latency"
    return {
        "action_id": f"act_observe_{category}",
        "action_type": "observe",
        "title": f"Observe {metric} for 10 minutes after remediation",
        "risk_level": "read_only",
        "requires_approval": False,
        "checkpoint_before_execution": False,
        "dry_run_default": True,
        "args": {"service": service, "window": "10m"},
        "policy_context": {"source": "service_profile_followup"},
    }


def plan_action(args: Dict[str, Any]) -> Dict[str, Any]:
    hypothesis = args.get("hypothesis") or {}
    service = args.get("service", "payment-service")
    category = str(hypothesis.get("category") or "")
    evidence = _iter_evidence(args)
    profile = args.get("service_profile") if isinstance(args.get("service_profile"), dict) else load_service_profile(service)
    memory_policy = _memory_guardrails(args)
    actions: List[Dict[str, Any]] = []

    rule = _profile_action_rule(profile, category)
    if category == "deploy_db_regression":
        actions.append(_rollback_action(service, profile, evidence, rule))
        if rule.get("observe_after", True):
            actions.append(_observe_action(service, category))
    elif rule:
        actions.append(_write_action(service, profile, category, rule))
    elif category == "coupon_timeout":
        actions.append(
            {
                "action_id": "act_scale_coupon",
                "action_type": "scale_or_disable_coupon_path",
                "title": "Route around or scale coupon-service before retrying payment requests",
                "risk_level": "write_safe",
                "requires_approval": True,
                "checkpoint_before_execution": True,
                "dry_run_default": True,
                "args": {"service": "coupon-service"},
                "policy_context": _profile_context(profile),
            }
        )
    elif category == "order_rate_limit":
        actions.append(
            {
                "action_id": "act_relax_order_rate_limit",
                "action_type": "adjust_rate_limit",
                "title": "Review order-service rate-limit policy and temporarily raise the demo limit",
                "risk_level": "write_safe",
                "requires_approval": True,
                "checkpoint_before_execution": True,
                "dry_run_default": True,
                "args": {"service": "order-service"},
                "policy_context": _profile_context(profile),
            }
        )

    result = {
        "status": "ok",
        "service": service,
        "category": category,
        "actions": actions,
        "planner": "service_profile_policy",
        "service_profile": _profile_context(profile)["service_profile"],
    }
    return _attach_memory_policy(result, memory_policy)
