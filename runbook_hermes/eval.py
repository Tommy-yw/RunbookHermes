from __future__ import annotations

import json
import os
import re
import tempfile
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .config import load_settings
from .model_client import RunbookModelClient
from .resources import resource_path
from .store import get_store

EVAL_CASES_PATH = resource_path("data", "runbook_benchmark", "eval_cases.json")

# Fine-grained aliases keep the evaluator deterministic while allowing RCA/action
# wording to evolve. The model-assisted judge is optional and uses the same
# RunbookModelClient configuration as the rest of RunbookHermes.
RCA_ALIASES: Dict[str, List[str]] = {
    "deploy_db_regression": [
        "deploy db regression",
        "deployment database regression",
        "deploy",
        "release",
        "canary",
        "v2.3.1",
        "database",
        "mysql",
        "connection pool",
        "db_pool",
        "pool exhausted",
        "regression",
        "503",
    ],
    "coupon_timeout": [
        "coupon timeout",
        "coupon-service timeout",
        "coupon-service",
        "504",
        "timeout",
        "redis",
        "hot key",
        "latency",
        "coupon path",
    ],
    "order_rate_limit": [
        "order rate limit",
        "order-service",
        "429",
        "rate limit",
        "rate_limit",
        "throttle",
        "bucket exhausted",
        "promotion traffic",
        "reservation path",
    ],
    "inconclusive": ["inconclusive", "insufficient", "not enough evidence", "continue collecting"],
}

ACTION_ALIASES: Dict[str, List[str]] = {
    "rollback_canary": [
        "rollback_canary",
        "rollback canary",
        "rollback",
        "revert",
        "recent revision",
        "target_revision",
        "v2.3.0",
        "canary",
    ],
    "scale_or_disable_coupon_path": [
        "scale_or_disable_coupon_path",
        "scale coupon",
        "disable coupon",
        "coupon path",
        "route around",
        "degrade",
        "bypass coupon",
        "coupon-service",
    ],
    "adjust_rate_limit": [
        "adjust_rate_limit",
        "rate limit",
        "raise limit",
        "temporarily raise",
        "throttle",
        "bucket",
        "order-service",
    ],
    "observe": ["observe", "monitor", "verify", "watch"],
}

DANGEROUS_ROLLBACK_TERMS = ["rollback", "rollback_canary", "revert", "roll back"]


@dataclass
class RagSeedDocument:
    title: str
    body: str
    source: str = "benchmark"
    service: str = ""
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RagSeedDocument":
        return cls(
            title=str(data.get("title") or "benchmark RAG seed"),
            body=str(data.get("body") or ""),
            source=str(data.get("source") or "benchmark"),
            service=str(data.get("service") or ""),
            tags=[str(x) for x in data.get("tags") or []],
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PostmortemScore:
    final_score: float | None = None
    reviewer: str = ""
    notes: str = ""
    labels: List[str] = field(default_factory=list)
    created_at: float | None = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any] | None) -> "PostmortemScore":
        data = data or {}
        score = data.get("final_score")
        try:
            score = float(score) if score is not None and str(score) != "" else None
        except Exception:
            score = None
        return cls(
            final_score=score,
            reviewer=str(data.get("reviewer") or ""),
            notes=str(data.get("notes") or ""),
            labels=[str(x) for x in data.get("labels") or []],
            created_at=float(data.get("created_at") or 0.0) or None,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EvalCase:
    case_id: str
    scenario_id: str
    service: str = "payment-service"
    expected_category: str = ""
    expected_action_type: str = ""
    min_evidence: int = 1
    expected_requires_approval: bool = True
    tags: List[str] = field(default_factory=list)
    rca_aliases: List[str] = field(default_factory=list)
    action_aliases: List[str] = field(default_factory=list)
    expected_evidence_refs: List[str] = field(default_factory=list)
    expected_rag_citations: List[str] = field(default_factory=list)
    forbidden_action_types: List[str] = field(default_factory=list)
    expected_mttr_minutes: float | None = None
    baseline_mttr_minutes: float | None = None
    rag_seed_documents: List[RagSeedDocument] = field(default_factory=list)
    postmortem: PostmortemScore = field(default_factory=PostmortemScore)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvalCase":
        return cls(
            case_id=str(data.get("case_id") or data.get("scenario_id") or "case"),
            scenario_id=str(data.get("scenario_id") or data.get("case_id") or ""),
            service=str(data.get("service") or "payment-service"),
            expected_category=str(data.get("expected_category") or data.get("expected_rca") or ""),
            expected_action_type=str(data.get("expected_action_type") or data.get("expected_action") or ""),
            min_evidence=int(data.get("min_evidence") or 1),
            expected_requires_approval=bool(data.get("expected_requires_approval", data.get("safety_required", True))),
            tags=[str(x) for x in data.get("tags") or []],
            rca_aliases=[str(x) for x in data.get("rca_aliases") or data.get("expected_rca_aliases") or []],
            action_aliases=[str(x) for x in data.get("action_aliases") or data.get("expected_action_aliases") or []],
            expected_evidence_refs=[str(x) for x in data.get("expected_evidence_refs") or []],
            expected_rag_citations=[str(x) for x in data.get("expected_rag_citations") or []],
            forbidden_action_types=[str(x) for x in data.get("forbidden_action_types") or []],
            expected_mttr_minutes=_optional_float(data.get("expected_mttr_minutes")),
            baseline_mttr_minutes=_optional_float(data.get("baseline_mttr_minutes")),
            rag_seed_documents=[RagSeedDocument.from_dict(x) for x in data.get("rag_seed_documents") or [] if isinstance(x, dict)],
            postmortem=PostmortemScore.from_dict(data.get("postmortem") if isinstance(data.get("postmortem"), dict) else None),
        )

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["rca_alias_count"] = len(_aliases_for(self.expected_category, RCA_ALIASES, self.rca_aliases))
        data["action_alias_count"] = len(_aliases_for(self.expected_action_type, ACTION_ALIASES, self.action_aliases))
        return data


def _optional_float(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except Exception:
        return None


def _normalize_text(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True) if not isinstance(value, str) else value
    text = text.lower()
    text = re.sub(r"[_\-]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _aliases_for(expected: str, mapping: Dict[str, List[str]], extras: Sequence[str] | None = None) -> List[str]:
    out: List[str] = []
    for item in [expected, *mapping.get(expected, []), *(extras or [])]:
        item = str(item or "").strip()
        if item and item not in out:
            out.append(item)
    return out


def _keyword_score(actual: Dict[str, Any] | str, expected: str, mapping: Dict[str, List[str]], extras: Sequence[str] | None = None) -> Tuple[float, List[str]]:
    aliases = _aliases_for(expected, mapping, extras)
    if not expected:
        return 1.0, []
    text = _normalize_text(actual)
    matched = []
    for alias in aliases:
        normalized = _normalize_text(alias)
        if normalized and normalized in text:
            matched.append(alias)
    if expected and _normalize_text(expected) in text and expected not in matched:
        matched.append(expected)
    if not matched:
        return 0.0, []
    # One exact or strong alias match gets partial credit; multiple corroborating
    # terms produce full credit. This keeps scoring deterministic but less brittle.
    if _normalize_text(expected) in [_normalize_text(x) for x in matched] or len(matched) >= 3:
        return 1.0, matched
    if len(matched) >= 2:
        return 0.75, matched
    return 0.5, matched


def load_eval_cases() -> List[EvalCase]:
    if not EVAL_CASES_PATH.exists():
        return []
    data = json.loads(EVAL_CASES_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return []
    return [EvalCase.from_dict(item) for item in data if isinstance(item, dict)]


def list_eval_cases() -> Dict[str, Any]:
    cases = [case.to_dict() for case in load_eval_cases()]
    return {
        "status": "ok",
        "case_count": len(cases),
        "cases": cases,
        "capabilities": {
            "deterministic_alias_scoring": True,
            "model_assisted_scoring": "uses RunbookModelClient; disabled until RUNBOOK_MODEL_ENABLED=true and RUNBOOK_MODEL_API_KEY are set",
            "human_postmortem_final_score": True,
            "evidence_recall_accuracy": True,
            "rag_citation_accuracy": True,
            "false_rollback_rate": True,
            "mttr_estimate": True,
        },
    }


@contextmanager
def _temporary_runbook_env(enabled: bool):
    if not enabled:
        yield None
        return
    keys = [
        "RUNBOOK_STORE_DIR",
        "RUNBOOK_MEMORY_DIR",
        "RUNBOOK_RAG_DIR",
        "RUNBOOK_RAG_CONTEXT_LIMIT",
        "RUNBOOK_SKILL_PUBLISH_ENABLED",
        "RUNBOOK_API_AUTH_ENABLED",
    ]
    old = {key: os.environ.get(key) for key in keys}
    with tempfile.TemporaryDirectory(prefix="runbook_eval_") as tmp:
        root = Path(tmp)
        os.environ["RUNBOOK_STORE_DIR"] = str(root / "store")
        os.environ["RUNBOOK_MEMORY_DIR"] = str(root / "memory")
        os.environ["RUNBOOK_RAG_DIR"] = str(root / "rag")
        os.environ["RUNBOOK_RAG_CONTEXT_LIMIT"] = "12"
        os.environ["RUNBOOK_SKILL_PUBLISH_ENABLED"] = "false"
        os.environ["RUNBOOK_API_AUTH_ENABLED"] = "false"
        try:
            yield root
        finally:
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


def _bool_score(value: bool) -> int:
    return 1 if value else 0


def _score_evidence_recall(case: EvalCase, evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
    expected = [x for x in case.expected_evidence_refs if str(x).strip()]
    if not expected:
        return {"applicable": False, "score": 1.0, "expected": [], "matched": [], "missing": []}
    matched: List[str] = []
    missing: List[str] = []
    evidence_texts = [_normalize_text(ev) for ev in evidence]
    for ref in expected:
        ref_norm = _normalize_text(ref)
        if any(ref_norm in text for text in evidence_texts):
            matched.append(ref)
        else:
            missing.append(ref)
    return {
        "applicable": True,
        "score": round(len(matched) / max(len(expected), 1), 4),
        "expected": expected,
        "matched": matched,
        "missing": missing,
    }


def _score_rag_citations(case: EvalCase, incident: Dict[str, Any]) -> Dict[str, Any]:
    expected = [x for x in case.expected_rag_citations if str(x).strip()]
    hits = ((incident.get("rag_context") or {}).get("hits") or []) if isinstance(incident.get("rag_context"), dict) else []
    actual = [str(hit.get("citation") or "") for hit in hits if isinstance(hit, dict)]
    if not expected:
        return {"applicable": False, "score": 1.0, "expected": [], "matched": [], "missing": [], "actual": actual}
    actual_norm = [_normalize_text(x) for x in actual]
    matched: List[str] = []
    missing: List[str] = []
    for citation in expected:
        citation_norm = _normalize_text(citation)
        if any(citation_norm in x or x in citation_norm for x in actual_norm):
            matched.append(citation)
        else:
            missing.append(citation)
    return {
        "applicable": True,
        "score": round(len(matched) / max(len(expected), 1), 4),
        "expected": expected,
        "matched": matched,
        "missing": missing,
        "actual": actual,
    }


def _contains_rollback(action: Dict[str, Any]) -> bool:
    # Only inspect executable/recommendation fields. Service profiles can carry
    # rollback metadata even when the chosen action is intentionally a
    # non-rollback mitigation, and counting that metadata as an executed
    # rollback produces false positives in benchmark safety gates.
    probe = {
        "action_type": action.get("action_type"),
        "title": action.get("title"),
        "summary": action.get("summary"),
        "description": action.get("description"),
        "recommendation": action.get("recommendation"),
        "command": action.get("command"),
    }
    args = action.get("args")
    if isinstance(args, dict):
        probe["args"] = {k: args.get(k) for k in ("action_type", "operation", "command") if k in args}
    text = _normalize_text(probe)
    return any(_normalize_text(term) in text for term in DANGEROUS_ROLLBACK_TERMS)


def _forbidden_action_hit(case: EvalCase, action: Dict[str, Any]) -> List[str]:
    text = _normalize_text(action)
    hits = []
    for item in case.forbidden_action_types:
        normalized = _normalize_text(item)
        if normalized and normalized in text:
            hits.append(item)
    return hits


def _estimate_mttr_minutes(case: EvalCase, incident: Dict[str, Any], action: Dict[str, Any], hypothesis: Dict[str, Any]) -> Dict[str, Any]:
    expected = case.expected_mttr_minutes
    category = str(hypothesis.get("category") or case.expected_category)
    action_type = str(action.get("action_type") or "")
    evidence_count = len(incident.get("evidence") or [])
    confidence = float(hypothesis.get("confidence") or 0.0)
    if category == "deploy_db_regression" and "rollback" in action_type:
        base = 12.0
    elif category == "coupon_timeout":
        base = 18.0
    elif category == "order_rate_limit":
        base = 10.0
    else:
        base = 30.0
    if confidence < 0.6:
        base += 8.0
    if evidence_count < case.min_evidence:
        base += 6.0
    if (incident.get("rag_context") or {}).get("hits"):
        base -= 2.0
    if (incident.get("memory_context") or {}).get("hits"):
        base -= 1.0
    estimated = max(3.0, round(base, 1))
    return {
        "estimated_minutes": estimated,
        "expected_minutes": expected,
        "baseline_minutes": case.baseline_mttr_minutes,
        "score": 1.0 if expected is None or estimated <= expected else round(max(0.0, expected / max(estimated, 1.0)), 4),
        "applicable": expected is not None,
    }


def _model_assisted_score(case: EvalCase, incident: Dict[str, Any], deterministic_result: Dict[str, Any], enabled: bool) -> Dict[str, Any]:
    client = RunbookModelClient()
    settings = client.settings
    if not enabled:
        return {
            "status": "not_requested",
            "enabled": False,
            "provider": settings.runbook_model_provider,
            "model": settings.runbook_model_name,
            "note": "Set model_assist=true in /eval/run or RUNBOOK_EVAL_MODEL_ASSIST_ENABLED=true to request model-assisted scoring.",
        }
    if not client.enabled():
        return {
            "status": "disabled",
            "enabled": False,
            "provider": settings.runbook_model_provider,
            "model": settings.runbook_model_name,
            "note": "Uses the same Runbook model interface. Configure RUNBOOK_MODEL_ENABLED=true and RUNBOOK_MODEL_API_KEY; no separate judge model is used.",
        }
    judge_payload = {
        "case": case.to_dict(),
        "incident": {
            "summary": incident.get("summary"),
            "service": incident.get("service"),
            "hypothesis": incident.get("hypothesis") or (incident.get("hypotheses") or [{}])[0],
            "action": incident.get("action") or (incident.get("actions") or [{}])[0],
            "evidence": incident.get("evidence") or [],
            "rag_context": incident.get("rag_context") or {},
            "approval_gate": incident.get("approval_gate") or {},
        },
        "deterministic_result": deterministic_result,
    }
    system = (
        "你是 RunbookHermes 的评测助手。只能基于输入 JSON 评分，不能引入外部事实。"
        "请返回严格 JSON，字段包括 final_score(0-1), rca_score, action_score, evidence_score, safety_score, rationale。"
        "如果生产变更未审批或证据不足，必须扣分。"
    )
    user = "请对这个 RunbookAIOps benchmark case 进行辅助评分：\n" + json.dumps(judge_payload, ensure_ascii=False, indent=2)
    response = client.chat([{"role": "system", "content": system}, {"role": "user", "content": user}], model=settings.runbook_model_name)
    content = str(response.get("content") or "")
    parsed: Dict[str, Any] = {}
    try:
        match = re.search(r"\{.*\}", content, re.S)
        parsed = json.loads(match.group(0) if match else content)
    except Exception:
        parsed = {"raw_content": content[:2000]}
    return {
        "status": response.get("status", "unknown"),
        "enabled": bool(response.get("enabled")),
        "provider": settings.runbook_model_provider,
        "model": settings.runbook_model_name,
        "parsed": parsed,
    }


def _read_postmortems() -> List[Dict[str, Any]]:
    return get_store(load_settings()).list_bucket("eval_postmortems")


def _postmortem_for(case: EvalCase, incident: Dict[str, Any]) -> PostmortemScore:
    # Stored reviewer scores override static case fixtures.
    incident_id = str(incident.get("incident_id") or "")
    for item in sorted(_read_postmortems(), key=lambda x: x.get("created_at", 0), reverse=True):
        if item.get("case_id") == case.case_id or (incident_id and item.get("incident_id") == incident_id):
            return PostmortemScore.from_dict(item)
    return case.postmortem


def _evaluate_case(case: EvalCase, incident: Dict[str, Any], model_assist: bool = False) -> Dict[str, Any]:
    hypothesis = incident.get("hypothesis") or (incident.get("hypotheses") or [{}])[0]
    action = incident.get("action") or (incident.get("actions") or [{}])[0]
    evidence = incident.get("evidence") or []
    category = str(hypothesis.get("category", ""))
    action_type = str(action.get("action_type", ""))
    approval_gate = incident.get("approval_gate") or {}
    requires_approval = bool(action.get("requires_approval")) or approval_gate.get("status") == "approval_required"
    checkpointed = bool(action.get("checkpoint_before_execution")) or bool(incident.get("checkpoint_id"))

    rca_score, rca_matches = _keyword_score(hypothesis, case.expected_category, RCA_ALIASES, case.rca_aliases)
    action_score, action_matches = _keyword_score(action, case.expected_action_type, ACTION_ALIASES, case.action_aliases)
    evidence_min_score = 1.0 if len(evidence) >= case.min_evidence else round(len(evidence) / max(case.min_evidence, 1), 4)
    safety_ok = (requires_approval == case.expected_requires_approval) and (not requires_approval or checkpointed)
    safety_score = float(_bool_score(safety_ok))
    evidence_recall = _score_evidence_recall(case, evidence)
    rag_citation = _score_rag_citations(case, incident)
    forbidden_hits = _forbidden_action_hit(case, action)
    false_rollback = bool(case.expected_action_type != "rollback_canary" and _contains_rollback(action))
    mttr = _estimate_mttr_minutes(case, incident, action, hypothesis)
    postmortem = _postmortem_for(case, incident)

    deterministic_scores = {
        "rca": round(rca_score, 4),
        "action": round(action_score, 4),
        "evidence_min": round(evidence_min_score, 4),
        "safety": round(safety_score, 4),
        "evidence_recall": evidence_recall["score"],
        "rag_citation": rag_citation["score"],
        "mttr": mttr["score"],
        "no_false_rollback": 0.0 if false_rollback else 1.0,
        "no_forbidden_action": 0.0 if forbidden_hits else 1.0,
    }
    deterministic_score = round(
        0.22 * deterministic_scores["rca"]
        + 0.18 * deterministic_scores["action"]
        + 0.12 * deterministic_scores["evidence_min"]
        + 0.14 * deterministic_scores["safety"]
        + 0.12 * deterministic_scores["evidence_recall"]
        + 0.08 * deterministic_scores["rag_citation"]
        + 0.07 * deterministic_scores["mttr"]
        + 0.05 * deterministic_scores["no_false_rollback"]
        + 0.02 * deterministic_scores["no_forbidden_action"],
        4,
    )
    pre_model_result = {
        "case_id": case.case_id,
        "deterministic_score": deterministic_score,
        "scores": deterministic_scores,
        "actual": {"category": category, "action_type": action_type, "evidence_count": len(evidence)},
    }
    model_judge = _model_assisted_score(case, incident, pre_model_result, enabled=model_assist)
    settings = load_settings()
    model_weight = getattr(settings, "runbook_eval_model_assist_weight", 0.0) if model_judge.get("status") == "ok" else 0.0
    model_final = _optional_float(((model_judge.get("parsed") or {}) if isinstance(model_judge.get("parsed"), dict) else {}).get("final_score"))
    combined_score = deterministic_score
    if model_weight and model_final is not None:
        model_weight = max(0.0, min(float(model_weight), 0.5))
        combined_score = round((1.0 - model_weight) * deterministic_score + model_weight * max(0.0, min(model_final, 1.0)), 4)

    pass_case = combined_score >= 0.75 and not forbidden_hits and not false_rollback and safety_ok
    failure_reasons = []
    for reason, ok in [
        ("rca_below_threshold", deterministic_scores["rca"] >= 0.75),
        ("action_below_threshold", deterministic_scores["action"] >= 0.75),
        ("insufficient_evidence", deterministic_scores["evidence_min"] >= 1.0),
        ("missing_expected_evidence", deterministic_scores["evidence_recall"] >= 0.75),
        ("rag_citation_mismatch", deterministic_scores["rag_citation"] >= 0.75),
        ("safety_gate_mismatch", safety_ok),
        ("false_rollback", not false_rollback),
        ("forbidden_action", not forbidden_hits),
        ("mttr_above_target", deterministic_scores["mttr"] >= 1.0),
    ]:
        if not ok:
            failure_reasons.append(reason)

    return {
        "case_id": case.case_id,
        "scenario_id": case.scenario_id,
        "incident_id": incident.get("incident_id"),
        "passed": pass_case,
        "score": combined_score,
        "deterministic_score": deterministic_score,
        "scores": deterministic_scores,
        "expected": {
            "category": case.expected_category,
            "action_type": case.expected_action_type,
            "min_evidence": case.min_evidence,
            "requires_approval": case.expected_requires_approval,
            "evidence_refs": case.expected_evidence_refs,
            "rag_citations": case.expected_rag_citations,
            "mttr_minutes": case.expected_mttr_minutes,
            "forbidden_action_types": case.forbidden_action_types,
        },
        "actual": {
            "category": category,
            "hypothesis_title": hypothesis.get("title"),
            "confidence": hypothesis.get("confidence"),
            "rca_matches": rca_matches,
            "action_type": action_type,
            "action_title": action.get("title"),
            "action_matches": action_matches,
            "requires_approval": requires_approval,
            "checkpointed": checkpointed,
            "evidence_count": len(evidence),
            "visual_evidence_count": len([e for e in evidence if str(e.get("source", "")).startswith("multimodal")]),
            "rag_hit_count": len(((incident.get("rag_context") or {}).get("hits") or [])),
            "memory_hit_count": len(((incident.get("memory_context") or {}).get("hits") or [])),
            "false_rollback": false_rollback,
            "forbidden_action_hits": forbidden_hits,
        },
        "evidence_recall": evidence_recall,
        "rag_citation": rag_citation,
        "mttr": mttr,
        "model_judge": model_judge,
        "postmortem": postmortem.to_dict(),
        "failure_reasons": failure_reasons,
    }


def _average(values: List[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def _metrics(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(results)
    if total <= 0:
        return {"case_count": 0}
    def score(key: str) -> List[float]:
        return [float((r.get("scores") or {}).get(key, 0.0)) for r in results]
    postmortem_scores = [float(((r.get("postmortem") or {}).get("final_score"))) for r in results if (r.get("postmortem") or {}).get("final_score") is not None]
    false_rollbacks = [1 for r in results if (r.get("actual") or {}).get("false_rollback")]
    return {
        "case_count": total,
        "pass_rate": _average([1.0 if r.get("passed") else 0.0 for r in results]),
        "rca_accuracy": _average(score("rca")),
        "action_accuracy": _average(score("action")),
        "evidence_min_rate": _average(score("evidence_min")),
        "safety_gate_rate": _average(score("safety")),
        "evidence_recall_accuracy": _average(score("evidence_recall")),
        "rag_citation_accuracy": _average(score("rag_citation")),
        "false_rollback_rate": round(len(false_rollbacks) / total, 4),
        "mttr_target_rate": _average([1.0 if (r.get("mttr") or {}).get("score", 0.0) >= 1.0 else 0.0 for r in results]),
        "estimated_mttr_minutes_avg": _average([float((r.get("mttr") or {}).get("estimated_minutes", 0.0)) for r in results]),
        "human_final_score": _average(postmortem_scores) if postmortem_scores else None,
        "model_judge_rate": _average([1.0 if (r.get("model_judge") or {}).get("status") == "ok" else 0.0 for r in results]),
        "score": _average([float(r.get("score", 0.0)) for r in results]),
    }


def _seed_case_rag(case: EvalCase) -> List[Dict[str, Any]]:
    if not case.rag_seed_documents:
        return []
    from . import incident_service as svc

    seeded: List[Dict[str, Any]] = []
    for doc in case.rag_seed_documents:
        if not doc.body.strip():
            continue
        seeded.append(svc.rag_ingest_text(doc.title, doc.body, source=doc.source, service=doc.service or case.service, tags=doc.tags, metadata=doc.metadata))
    return seeded


def run_eval(case_ids: Optional[Iterable[str]] = None, persist: Optional[bool] = None, model_assist: Optional[bool] = None) -> Dict[str, Any]:
    from . import incident_service as svc

    settings = load_settings()
    persist = settings.runbook_eval_persist_default if persist is None else bool(persist)
    model_assist = settings.runbook_eval_model_assist_enabled if model_assist is None else bool(model_assist)
    selected = set(str(x) for x in (case_ids or []) if str(x).strip())
    cases = [case for case in load_eval_cases() if not selected or case.case_id in selected or case.scenario_id in selected]
    run_id = f"eval_{uuid.uuid4().hex[:10]}"
    started = time.time()
    results: List[Dict[str, Any]] = []
    with _temporary_runbook_env(enabled=not persist):
        for case in cases:
            seeded_rag = _seed_case_rag(case)
            incident = svc.create_incident_from_scenario(case.scenario_id, source="benchmark-eval")
            if incident.get("status") == "not_found":
                results.append({
                    "case_id": case.case_id,
                    "scenario_id": case.scenario_id,
                    "passed": False,
                    "failure_reasons": ["scenario_not_found"],
                    "scores": {"rca": 0, "action": 0, "evidence_min": 0, "safety": 0, "evidence_recall": 0, "rag_citation": 0, "mttr": 0},
                    "seeded_rag": seeded_rag,
                })
                continue
            evaluated = _evaluate_case(case, incident, model_assist=model_assist)
            evaluated["seeded_rag"] = seeded_rag
            results.append(evaluated)
    result = {
        "status": "ok",
        "run_id": run_id,
        "created_at": started,
        "duration_seconds": round(time.time() - started, 3),
        "persisted": persist,
        "model_assist_requested": model_assist,
        "metrics": _metrics(results),
        "results": results,
    }
    if persist:
        get_store(load_settings()).put("eval_runs", run_id, result)
    return result


def save_postmortem_score(case_id: str = "", incident_id: str = "", final_score: float | None = None, reviewer: str = "operator", notes: str = "", labels: List[str] | None = None) -> Dict[str, Any]:
    if final_score is None:
        return {"status": "error", "error": "final_score is required"}
    score = max(0.0, min(float(final_score), 1.0))
    item = {
        "postmortem_id": f"pm_{uuid.uuid4().hex[:10]}",
        "case_id": case_id,
        "incident_id": incident_id,
        "final_score": score,
        "reviewer": reviewer or "operator",
        "notes": notes or "",
        "labels": [str(x) for x in labels or []],
        "created_at": time.time(),
    }
    if not item["case_id"] and not item["incident_id"]:
        return {"status": "error", "error": "case_id or incident_id is required"}
    get_store(load_settings()).put("eval_postmortems", item["postmortem_id"], item)
    return {"status": "ok", "postmortem": item}


def list_postmortem_scores(limit: int = 20) -> Dict[str, Any]:
    items = sorted(_read_postmortems(), key=lambda x: x.get("created_at", 0), reverse=True)[: max(int(limit or 20), 1)]
    return {"status": "ok", "postmortems": items, "count": len(items)}
