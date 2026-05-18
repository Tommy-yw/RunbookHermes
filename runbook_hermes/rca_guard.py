from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Set, Tuple

from .config import load_settings
from .memory_kinds import RCA_PRIOR_KINDS, normalize_memory_kind
from .service_profiles import dependency_names, load_service_profile


DEFAULT_RCA_RULES: List[Dict[str, Any]] = [
    {
        "rule_id": "deploy_db_pool_regression",
        "category": "deploy_db_regression",
        "title": "Recent deployment likely introduced a database connection pool regression that returns HTTP 503",
        "required_signals": ["deploy_recent", "http_503", "db_pool"],
        "supporting_signals": ["mysql", "p95_latency", "trace_error"],
        "base_confidence": 0.80,
    },
    {
        "rule_id": "coupon_timeout",
        "category": "coupon_timeout",
        "title": "coupon-service timeout is likely causing payment-service HTTP 504 responses",
        "required_signals": ["dependency_coupon", "http_504", "timeout"],
        "supporting_signals": ["trace_error", "p95_latency"],
        "base_confidence": 0.74,
    },
    {
        "rule_id": "order_rate_limit",
        "category": "order_rate_limit",
        "title": "order-service rate limiting is likely causing HTTP 429 responses",
        "required_signals": ["dependency_order", "http_429", "rate_limit"],
        "supporting_signals": ["traffic_spike", "promo"],
        "base_confidence": 0.72,
    },
]

SIGNAL_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    ("http_503", re.compile(r"\b503\b|http[_ -]?503|status[=:\s]+503", re.I)),
    ("http_504", re.compile(r"\b504\b|http[_ -]?504|gateway timeout|status[=:\s]+504", re.I)),
    ("http_429", re.compile(r"\b429\b|http[_ -]?429|too many requests", re.I)),
    ("db_pool", re.compile(r"connection pool|db[_ -]?pool|pool exhausted|max connections", re.I)),
    ("mysql", re.compile(r"mysql|rds|innodb", re.I)),
    ("redis", re.compile(r"redis|cache", re.I)),
    ("hot_key", re.compile(r"hot[_ -]?key|hot key", re.I)),
    ("timeout", re.compile(r"timeout|timed out|deadline exceeded|context deadline", re.I)),
    ("rate_limit", re.compile(r"rate[_ -]?limit|rate limit|throttle|quota", re.I)),
    ("traffic_spike", re.compile(r"traffic spike|qps|rps|requests per second|surge", re.I)),
    ("promo", re.compile(r"promo|campaign|flash sale|promotion", re.I)),
    ("p95_latency", re.compile(r"p95|latency|duration|slowest", re.I)),
    ("trace_error", re.compile(r"trace|span|error_count|error span|downstream", re.I)),
    ("deploy_recent", re.compile(r"deploy|deployment|release|revision|version|canary|recent", re.I)),
    ("dependency_coupon", re.compile(r"coupon-service|coupon", re.I)),
    ("dependency_order", re.compile(r"order-service|order", re.I)),
]


def _evidence_text(item: Dict[str, Any]) -> str:
    try:
        return json.dumps(item, ensure_ascii=False, sort_keys=True).lower()
    except Exception:
        return str(item).lower()


def _signals_for_item(item: Dict[str, Any], profile: Dict[str, Any]) -> Set[str]:
    text = _evidence_text(item)
    signals = {name for name, pattern in SIGNAL_PATTERNS if pattern.search(text)}
    source = str(item.get("source", "")).lower()
    if source in {"prometheus", "metric", "metrics"} and any(s in signals for s in ("http_503", "http_504", "http_429", "p95_latency")):
        signals.add("metric_anomaly")
    if source in {"loki", "log", "logs"}:
        signals.add("log_match")
    if source in {"trace", "jaeger", "tempo"}:
        signals.add("trace_evidence")
        if item.get("error_count") or "error" in text:
            signals.add("trace_error")
    if source in {"deploy", "argocd", "kubernetes"}:
        signals.add("deploy_recent")
    for dep in dependency_names(profile):
        dep_norm = dep.lower()
        if dep_norm and dep_norm in text:
            signals.add("dependency")
            if "coupon" in dep_norm:
                signals.add("dependency_coupon")
            if "order" in dep_norm:
                signals.add("dependency_order")
    return signals


def build_evidence_graph(evidence: List[Dict[str, Any]], service: str, service_profile: Dict[str, Any] | None = None) -> Dict[str, Any]:
    profile = service_profile or load_service_profile(service)
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    signal_to_evidence: Dict[str, List[str]] = {}
    nodes.append({"id": f"svc:{service}", "type": "service", "label": service})
    for dep in dependency_names(profile):
        dep_id = f"svc:{dep}"
        nodes.append({"id": dep_id, "type": "dependency", "label": dep})
        edges.append({"from": f"svc:{service}", "to": dep_id, "type": "depends_on"})
    for idx, item in enumerate(evidence, start=1):
        ev_id = str(item.get("evidence_id") or f"ev_{idx}")
        nodes.append({"id": ev_id, "type": "evidence", "source": item.get("source"), "label": item.get("summary", ev_id)[:180]})
        edges.append({"from": f"svc:{service}", "to": ev_id, "type": "has_evidence"})
        for signal in sorted(_signals_for_item(item, profile)):
            signal_to_evidence.setdefault(signal, []).append(ev_id)
            signal_id = f"sig:{signal}"
            if not any(n.get("id") == signal_id for n in nodes):
                nodes.append({"id": signal_id, "type": "signal", "label": signal})
            edges.append({"from": ev_id, "to": signal_id, "type": "supports_signal"})
    return {
        "service": service,
        "profile_owner": profile.get("owner"),
        "signals": sorted(signal_to_evidence.keys()),
        "signal_to_evidence": {k: sorted(set(v)) for k, v in signal_to_evidence.items()},
        "nodes": nodes,
        "edges": edges,
    }


def _rules_for_profile(profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    rules: List[Dict[str, Any]] = []
    seen = set()
    for rule in list(profile.get("rca_rules") or []) + DEFAULT_RCA_RULES:
        if not isinstance(rule, dict):
            continue
        rid = str(rule.get("rule_id") or rule.get("category") or "")
        if rid in seen:
            continue
        seen.add(rid)
        rules.append(rule)
    return rules


def _score_rule(rule: Dict[str, Any], graph: Dict[str, Any]) -> Dict[str, Any]:
    signals = set(graph.get("signals") or [])
    required = [str(s) for s in rule.get("required_signals") or []]
    supporting = [str(s) for s in rule.get("supporting_signals") or []]
    matched_required = [s for s in required if s in signals]
    matched_supporting = [s for s in supporting if s in signals]
    required_score = len(matched_required) / max(1, len(required))
    support_score = len(matched_supporting) / max(1, len(supporting)) if supporting else 0.0
    full_required = len(matched_required) == len(required)
    base = float(rule.get("base_confidence", 0.65))
    confidence = min(0.95, max(0.20, base * required_score + 0.10 * support_score + (0.05 if full_required else 0.0)))
    evidence_ids = sorted({eid for signal in matched_required + matched_supporting for eid in graph.get("signal_to_evidence", {}).get(signal, [])})
    return {
        "rule_id": rule.get("rule_id"),
        "category": rule.get("category", "inconclusive"),
        "title": rule.get("title", "Evidence matched an RCA policy rule"),
        "confidence": round(confidence, 3),
        "required_signals": required,
        "supporting_signals": supporting,
        "matched_required": matched_required,
        "matched_supporting": matched_supporting,
        "full_required_match": full_required,
        "evidence_ids": evidence_ids,
    }


def _best_rule_match(graph: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any] | None:
    matches = [_score_rule(rule, graph) for rule in _rules_for_profile(profile)]
    viable = [m for m in matches if m["matched_required"]]
    if not viable:
        return None
    viable.sort(key=lambda m: (m["full_required_match"], len(m["matched_required"]), m["confidence"], len(m["matched_supporting"])), reverse=True)
    graph["rule_matches"] = matches
    best = viable[0]
    if not best["full_required_match"] and best["confidence"] < 0.55:
        return None
    return best


def build_hypothesis(evidence: List[Dict[str, Any]], service: str = "payment-service", service_profile: Dict[str, Any] | None = None) -> Dict[str, Any]:
    profile = service_profile or load_service_profile(service)
    graph = build_evidence_graph(evidence, service, profile)
    best = _best_rule_match(graph, profile)
    if best:
        matched = best.get("matched_required", []) + best.get("matched_supporting", [])
        rationale = (
            "Evidence graph matched RCA policy rule "
            f"{best.get('rule_id')}: matched signals={', '.join(matched) or 'none'}."
        )
        return {
            "hypothesis_id": f"hyp_{best.get('category', 'rca')}",
            "category": best.get("category", "inconclusive"),
            "title": best.get("title"),
            "confidence": best.get("confidence", 0.5),
            "evidence_ids": best.get("evidence_ids", []),
            "rationale": rationale,
            "evidence_graph": graph,
            "rca_policy_rule": best,
        }
    ids = [e.get("evidence_id") for e in evidence if e.get("evidence_id")]
    return {
        "hypothesis_id": "hyp_inconclusive",
        "category": "inconclusive",
        "title": "Evidence is insufficient for a confident root cause",
        "confidence": 0.35,
        "evidence_ids": ids,
        "rationale": "The evidence graph did not satisfy any service-profile RCA policy rule. Continue collecting logs, traces, deploy history and dependency metrics.",
        "evidence_graph": graph,
        "rca_policy_rule": None,
    }


def _memory_relevance(memory_context: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(memory_context, dict):
        return {"ids": [], "notes": []}
    hits = memory_context.get("hits") or []
    ids: List[str] = []
    notes: List[str] = []
    for hit in hits[:4]:
        if not isinstance(hit, dict):
            continue
        kind = normalize_memory_kind(hit.get("kind", ""))
        if kind not in RCA_PRIOR_KINDS:
            continue
        memory_id = hit.get("memory_id")
        if memory_id:
            ids.append(str(memory_id))
        title = hit.get("title") or hit.get("snippet") or "memory hit"
        trust = hit.get("trust_score", 0.0)
        notes.append(f"{kind}:{title} (trust={float(trust or 0):.2f})")
    return {"ids": ids, "notes": notes}


def _apply_memory_prior(hypothesis: Dict[str, Any], memory_context: Dict[str, Any] | None) -> Dict[str, Any]:
    relevance = _memory_relevance(memory_context)
    if not relevance["ids"]:
        return hypothesis
    boosted = dict(hypothesis)
    boosted["confidence"] = min(0.95, float(boosted.get("confidence", 0.0)) + min(0.06, 0.015 * len(relevance["ids"])))
    boosted["memory_ids"] = relevance["ids"]
    boosted["memory_prior"] = {
        "used_as": "weak_prior",
        "ids": relevance["ids"],
        "notes": relevance["notes"],
        "safety": "recalled memory is background context; evidence graph and evidence_ids remain authoritative",
    }
    boosted["rationale"] = (boosted.get("rationale", "") + " Historical RunbookHermes memory recalled similar service/fault context; it was used only as a weak prior, not as proof.").strip()
    return boosted


def _attach_model_summary(hypothesis: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    settings = load_settings()
    if not getattr(settings, "runbook_model_enabled", False):
        return hypothesis
    try:
        from .model_client import RunbookModelClient

        graph = hypothesis.get("evidence_graph", {})
        compact = {
            "service": args.get("service"),
            "summary": args.get("summary", ""),
            "hypothesis": {k: hypothesis.get(k) for k in ("category", "title", "confidence", "evidence_ids", "rationale")},
            "signals": graph.get("signals"),
            "rule": hypothesis.get("rca_policy_rule"),
        }
        response = RunbookModelClient(settings).chat(
            [
                {"role": "system", "content": "You summarize RCA evidence. Do not invent evidence. Return concise Chinese text."},
                {"role": "user", "content": json.dumps(compact, ensure_ascii=False)},
            ]
        )
        out = dict(hypothesis)
        out["model_summary"] = {"status": response.get("status"), "enabled": response.get("enabled"), "content": response.get("content", "")[:1200]}
        return out
    except Exception as exc:  # pragma: no cover - optional network path
        out = dict(hypothesis)
        out["model_summary"] = {"status": "error", "error": str(exc)}
        return out


def guard_root_cause(args: Dict[str, Any]) -> Dict[str, Any]:
    evidence = args.get("evidence") or []
    service = args.get("service", "payment-service")
    profile = args.get("service_profile") if isinstance(args.get("service_profile"), dict) else load_service_profile(service)
    hyp = build_hypothesis(evidence, service=service, service_profile=profile)
    hyp = _apply_memory_prior(hyp, args.get("memory_context"))
    hyp = _attach_model_summary(hyp, args)
    return {"status": "ok", "service": service, "hypothesis": hyp}
