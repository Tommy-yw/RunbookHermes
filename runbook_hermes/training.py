from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .config import load_settings
from .store import Store, get_store
from .resources import resource_path, resource_root

ROOT = resource_root()
BENCHMARK_CASES_PATH = resource_path("data", "runbook_benchmark", "eval_cases.json")

TOOL_SIGNATURES = {
    "incident_rca_guard": {
        "description": "Validate or generate an RCA hypothesis from evidence.",
        "parameters": {"service": "string", "evidence": "array<object>"},
    },
    "action_policy_guard": {
        "description": "Generate policy-checked actions from a root-cause hypothesis.",
        "parameters": {"service": "string", "hypothesis": "object"},
    },
    "runbook_approval_decision": {
        "description": "Approve or reject a pending destructive action.",
        "parameters": {"approval_id": "string", "decision": "approved|rejected"},
    },
    "runbook_memory_write": {
        "description": "Write safe durable incident learning into RunbookHermes memory.",
        "parameters": {"kind": "string", "service": "string", "title": "string", "body": "string"},
    },
}


@dataclass
class TrainingPaths:
    run_id: str
    run_dir: Path
    prompts_jsonl: Path
    trajectories_jsonl: Path
    compressed_jsonl: Path
    sft_jsonl: Path
    preference_jsonl: Path
    rewards_jsonl: Path
    manifest_json: Path
    alicloud_dir: Path

    def to_dict(self) -> Dict[str, str]:
        return {key: str(value) for key, value in asdict(self).items()}


@dataclass
class TrajectoryScore:
    reward: float
    rca: float
    action: float
    evidence: float
    safety: float
    learning: float
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _settings_store() -> Store:
    return get_store(load_settings())


def _training_root() -> Path:
    settings = load_settings()
    root = Path(settings.runbook_training_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _now() -> float:
    return time.time()


def _short_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _json_line(obj: Dict[str, Any]) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n"


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    items: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                items.append(parsed)
    return items


def _write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(_json_line(row))
            count += 1
    return count


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _paths(run_id: str) -> TrainingPaths:
    run_dir = _training_root() / "runs" / run_id
    dataset_dir = run_dir / "datasets"
    return TrainingPaths(
        run_id=run_id,
        run_dir=run_dir,
        prompts_jsonl=dataset_dir / "dataset.jsonl",
        trajectories_jsonl=dataset_dir / "trajectories.jsonl",
        compressed_jsonl=dataset_dir / "compressed.jsonl",
        sft_jsonl=dataset_dir / "sft.jsonl",
        preference_jsonl=dataset_dir / "preference.jsonl",
        rewards_jsonl=dataset_dir / "rewards.jsonl",
        manifest_json=run_dir / "manifest.json",
        alicloud_dir=run_dir / "alicloud",
    )


def _latest_run_id() -> str:
    runs = list_training_runs(limit=1).get("runs") or []
    if runs:
        return str(runs[0].get("run_id") or "")
    return ""


def _get_paths_for_run(run_id: str | None = None) -> TrainingPaths:
    rid = str(run_id or _latest_run_id()).strip()
    if not rid:
        raise ValueError("no training run found; build a dataset first")
    return _paths(rid)


def _safe_text(value: Any, limit: int = 8000) -> str:
    text = str(value or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _safe_tool_payload(data: Any, limit: int = 12000) -> Any:
    text = json.dumps(data, ensure_ascii=False, sort_keys=True)
    if len(text) <= limit:
        return data
    return {"preview": text[: limit - 1] + "...", "truncated": True, "original_chars": len(text)}


def _tool_call(name: str, arguments: Dict[str, Any]) -> str:
    return "<tool_call>\n" + json.dumps({"name": name, "arguments": arguments}, ensure_ascii=False, sort_keys=True) + "\n</tool_call>"


def _tool_response(name: str, content: Any, call_id: str) -> str:
    payload = {"tool_call_id": call_id, "name": name, "content": _safe_tool_payload(content)}
    return "<tool_response>\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n</tool_response>"


def _system_message() -> str:
    return (
        "You are a RunbookAIOps function-calling model. Diagnose incidents, collect evidence, "
        "propose guarded actions, request approval for destructive changes, and write reusable memory. "
        "Return function calls inside <tool_call> tags and tool results are supplied inside <tool_response> tags.\n"
        "<tools>\n" + json.dumps(TOOL_SIGNATURES, ensure_ascii=False, indent=2, sort_keys=True) + "\n</tools>"
    )


def _incident_prompt(incident: Dict[str, Any]) -> str:
    parts = [
        f"Handle incident {incident.get('incident_id', 'incident')}.",
        f"service={incident.get('service', '')}",
        f"severity={incident.get('severity', '')}",
        f"environment={incident.get('environment', '')}",
        f"summary={incident.get('summary', '')}",
    ]
    memory_hits = len(((incident.get("memory_context") or {}).get("hits") or []))
    rag_hits = len(((incident.get("rag_context") or {}).get("hits") or []))
    if memory_hits or rag_hits:
        parts.append(f"Use recalled memory hits={memory_hits} and RAG citations={rag_hits} only as background.")
    parts.append("Produce RCA, guarded remediation, approval decision points, and learning notes.")
    return " ".join(_safe_text(x, 1000) for x in parts if x)


def _final_answer(incident: Dict[str, Any], score: TrajectoryScore) -> str:
    hypothesis = incident.get("hypothesis") or (incident.get("hypotheses") or [{}])[0]
    action = incident.get("action") or (incident.get("actions") or [{}])[0]
    approval = incident.get("approval_gate") or {}
    learned = incident.get("memory_learning") or {}
    return "\n".join(
        [
            "<think>",
            "The root cause, action and safety gates have been checked. Now present the concise runbook outcome.",
            "</think>",
            f"RCA: {hypothesis.get('category', 'unknown')} - {hypothesis.get('title', '')}",
            f"Action: {action.get('action_type', 'unknown')} - {action.get('title', '')}",
            f"Approval: {approval.get('status', 'not_required')}; checkpoint={incident.get('checkpoint_id', '')}",
            f"Learning: {learned.get('learned_count', 0)} memory items; reward={score.reward:.3f}",
        ]
    )


def score_incident(incident: Dict[str, Any]) -> TrajectoryScore:
    hypothesis = incident.get("hypothesis") or (incident.get("hypotheses") or [{}])[0]
    action = incident.get("action") or (incident.get("actions") or [{}])[0]
    evidence = incident.get("evidence") or []
    learned = (incident.get("memory_learning") or {}).get("learned") or []
    approval_gate = incident.get("approval_gate") or {}

    reasons: List[str] = []
    rca = 1.0 if (hypothesis.get("category") or hypothesis.get("title")) else 0.0
    if not rca:
        reasons.append("missing_rca")
    action_score = 1.0 if (action.get("action_type") or action.get("title")) else 0.0
    if not action_score:
        reasons.append("missing_action")
    evidence_score = min(1.0, len(evidence) / 4.0)
    if evidence_score < 1.0:
        reasons.append("low_evidence")
    risky = bool(action.get("requires_approval")) or str(action.get("risk_level", "")).lower() in {"destructive", "high", "write_high"}
    checkpointed = bool(incident.get("checkpoint_id")) or bool(action.get("checkpoint_before_execution"))
    safety = 1.0 if (not risky or (approval_gate.get("status") == "approval_required" and checkpointed)) else 0.0
    if not safety:
        reasons.append("missing_approval_or_checkpoint")
    learning = min(1.0, len(learned) / 2.0)
    if learning < 1.0:
        reasons.append("low_learning")
    reward = round(0.35 * rca + 0.25 * action_score + 0.20 * evidence_score + 0.15 * safety + 0.05 * learning, 4)
    return TrajectoryScore(reward=reward, rca=rca, action=action_score, evidence=round(evidence_score, 4), safety=safety, learning=round(learning, 4), reasons=reasons)


def incident_to_trajectory_record(incident: Dict[str, Any], *, source: str = "incident_store", prompt_index: int = 0) -> Dict[str, Any]:
    incident_id = str(incident.get("incident_id") or f"synthetic_{prompt_index}")
    service = str(incident.get("service") or "payment-service")
    evidence = incident.get("evidence") or []
    hypothesis = incident.get("hypothesis") or (incident.get("hypotheses") or [{}])[0]
    action = incident.get("action") or (incident.get("actions") or [{}])[0]
    score = score_incident(incident)

    rca_args = {"service": service, "evidence": evidence[:12]}
    action_args = {"service": service, "hypothesis": hypothesis}
    memory_args = {
        "kind": "incident_summary",
        "service": service,
        "title": f"{service} incident training memory: {hypothesis.get('category', 'unknown')}",
        "body": f"summary={incident.get('summary', '')}; action={action.get('action_type', '')}; evidence={len(evidence)}",
        "incident_id": incident_id,
    }
    conversations = [
        {"from": "system", "value": _system_message()},
        {"from": "human", "value": _incident_prompt(incident)},
        {
            "from": "gpt",
            "value": "<think>Gather the evidence and ask the RCA guard for a structured hypothesis.</think>\n" + _tool_call("incident_rca_guard", rca_args),
        },
        {"from": "tool", "value": _tool_response("incident_rca_guard", hypothesis, f"call_rca_{incident_id}")},
        {
            "from": "gpt",
            "value": "<think>Use the hypothesis to plan an action, preserving approval and checkpoint safety gates.</think>\n" + _tool_call("action_policy_guard", action_args),
        },
        {"from": "tool", "value": _tool_response("action_policy_guard", action, f"call_action_{incident_id}")},
        {
            "from": "gpt",
            "value": "<think>The incident produced reusable operational learning. Store a safe summary.</think>\n" + _tool_call("runbook_memory_write", memory_args),
        },
        {
            "from": "tool",
            "value": _tool_response(
                "runbook_memory_write",
                incident.get("memory_learning") or {"status": "not_recorded", "incident_id": incident_id},
                f"call_memory_{incident_id}",
            ),
        },
        {"from": "gpt", "value": _final_answer(incident, score)},
    ]
    tool_stats = {
        "incident_rca_guard": {"count": 1, "success": 1 if hypothesis else 0, "failure": 0 if hypothesis else 1},
        "action_policy_guard": {"count": 1, "success": 1 if action else 0, "failure": 0 if action else 1},
        "runbook_memory_write": {"count": 1, "success": 1 if incident.get("memory_learning") else 0, "failure": 0 if incident.get("memory_learning") else 1},
    }
    return {
        "prompt_index": prompt_index,
        "conversations": conversations,
        "metadata": {
            "source": source,
            "incident_id": incident_id,
            "service": service,
            "summary": incident.get("summary", ""),
            "created_at": incident.get("created_at") or _now(),
            "model": "runbook-aiops-deterministic-exporter",
            "reward": score.reward,
        },
        "completed": bool(score.rca and score.action and score.safety),
        "partial": False,
        "api_calls": 0,
        "toolsets_used": ["runbook-observability", "runbook-memory", "runbook-training"],
        "tool_stats": tool_stats,
        "tool_error_counts": {name: stats["failure"] for name, stats in tool_stats.items()},
        "reward": score.to_dict(),
    }


def _case_summary(case: Dict[str, Any]) -> str:
    scenario = str(case.get("scenario_id") or case.get("case_id") or "incident")
    if "coupon" in scenario:
        return "payment-service HTTP 504 spike because coupon-service downstream timeout increased"
    if "order" in scenario:
        return "payment-service receives HTTP 429 responses from order-service under reservation load"
    return "payment-service HTTP 503 spike after v2.3.1 canary deployment"


def _synthetic_incident_from_case(case: Dict[str, Any], index: int) -> Dict[str, Any]:
    service = str(case.get("service") or "payment-service")
    scenario = str(case.get("scenario_id") or case.get("case_id") or f"case_{index}")
    category = str(case.get("expected_category") or "unknown")
    action_type = str(case.get("expected_action_type") or "investigate")
    min_evidence = int(case.get("min_evidence") or 3)
    evidence = [
        {
            "evidence_id": f"ev_{scenario}_{i}",
            "source": "benchmark_synthetic",
            "service": service,
            "summary": f"Benchmark evidence {i} for {scenario}",
            "confidence": 0.75 + min(i, 3) * 0.03,
            "scenario": scenario,
        }
        for i in range(1, max(min_evidence, 1) + 1)
    ]
    return {
        "incident_id": f"bench_{scenario}",
        "service": service,
        "severity": "p1",
        "environment": "prod",
        "summary": _case_summary(case),
        "alert_name": scenario,
        "source": "benchmark_case",
        "created_at": _now(),
        "evidence": evidence,
        "hypothesis": {
            "hypothesis_id": f"hyp_{scenario}",
            "category": category,
            "title": f"Expected benchmark RCA: {category}",
            "confidence": 0.9,
            "evidence_ids": [item["evidence_id"] for item in evidence],
        },
        "action": {
            "action_id": f"act_{scenario}",
            "action_type": action_type,
            "title": f"Expected guarded action: {action_type}",
            "requires_approval": bool(case.get("expected_requires_approval", True)),
            "checkpoint_before_execution": True,
            "risk_level": "destructive" if action_type == "rollback_canary" else "write_safe",
        },
        "approval_gate": {"status": "approval_required", "checkpoint_id": f"checkpoint_{scenario}"},
        "checkpoint_id": f"checkpoint_{scenario}",
        "memory_learning": {
            "status": "ok",
            "learned_count": 2,
            "learned": [
                {"memory": {"kind": "incident_summary", "title": f"{scenario} summary"}},
                {"memory": {"kind": "fault_pattern", "title": f"{scenario} pattern"}},
            ],
        },
    }


def _load_benchmark_cases() -> List[Dict[str, Any]]:
    if not BENCHMARK_CASES_PATH.exists():
        return []
    try:
        data = json.loads(BENCHMARK_CASES_PATH.read_text(encoding="utf-8"))
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []
    except Exception:
        return []


def _stored_incidents(limit: int) -> List[Dict[str, Any]]:
    items = _settings_store().list_bucket("incidents")
    items = [item for item in items if isinstance(item, dict)]
    items.sort(key=lambda item: float(item.get("created_at") or 0), reverse=True)
    hydrated: List[Dict[str, Any]] = []
    try:
        from . import incident_service as svc
    except Exception:
        svc = None  # type: ignore
    for item in items[: max(0, limit)]:
        incident_id = str(item.get("incident_id") or "")
        if svc is not None and incident_id:
            try:
                full = svc.get_incident(incident_id)
                if full:
                    hydrated.append(full)
                    continue
            except Exception:
                pass
        hydrated.append(item)
    return hydrated


def _prompt_rows(records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for record in records:
        meta = record.get("metadata") or {}
        human = ""
        for msg in record.get("conversations") or []:
            if msg.get("from") == "human":
                human = str(msg.get("value") or "")
                break
        rows.append(
            {
                "prompt": human or f"Handle RunbookAIOps incident {meta.get('incident_id', '')}",
                "metadata": meta,
                "source": meta.get("source", "runbook_aiops"),
                "docker_image": os.getenv("RUNBOOK_TRAINING_DEFAULT_DOCKER_IMAGE", ""),
            }
        )
    return rows


def _sft_rows(records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for record in records:
        conversations = record.get("conversations") or []
        messages = []
        for item in conversations:
            role = item.get("from")
            value = item.get("value", "")
            if role == "system":
                messages.append({"role": "system", "content": value})
            elif role == "human":
                messages.append({"role": "user", "content": value})
            elif role == "gpt":
                messages.append({"role": "assistant", "content": value})
            elif role == "tool":
                messages.append({"role": "tool", "content": value})
        rows.append({"messages": messages, "metadata": record.get("metadata") or {}, "reward": (record.get("reward") or {}).get("reward", 0.0)})
    return rows


def _preference_rows(records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for record in records:
        conversations = record.get("conversations") or []
        prompt = ""
        chosen = ""
        for item in conversations:
            if item.get("from") == "human" and not prompt:
                prompt = str(item.get("value") or "")
            if item.get("from") == "gpt":
                chosen = str(item.get("value") or chosen)
        reward = float((record.get("reward") or {}).get("reward") or 0.0)
        rejected = (
            "RCA: unknown\nAction: investigate manually\nApproval: not_checked\n"
            "This response is intentionally weak and is used only as a preference baseline."
        )
        rows.append({"prompt": prompt, "chosen": chosen, "rejected": rejected, "score_chosen": reward, "score_rejected": 0.05, "metadata": record.get("metadata") or {}})
    return rows


def _compress_value(value: str, max_chars: int) -> Tuple[str, bool]:
    if len(value) <= max_chars:
        return value, False
    head = value[: max_chars // 2]
    tail = value[-max_chars // 2 :]
    summary = f"\n[RUNBOOK_TRAJECTORY_SUMMARY: middle content compressed; original_chars={len(value)}]\n"
    return head.rstrip() + summary + tail.lstrip(), True


def compress_records(records: Sequence[Dict[str, Any]], max_message_chars: int) -> Tuple[List[Dict[str, Any]], int]:
    compressed: List[Dict[str, Any]] = []
    changed = 0
    for record in records:
        clone = json.loads(json.dumps(record, ensure_ascii=False))
        for message in clone.get("conversations") or []:
            value = str(message.get("value") or "")
            new_value, did = _compress_value(value, max_message_chars)
            if did:
                message["value"] = new_value
                changed += 1
        compressed.append(clone)
    return compressed, changed


def _alicloud_handoff(paths: TrainingPaths, *, base_model: str, output_model_name: str) -> Dict[str, Any]:
    paths.alicloud_dir.mkdir(parents=True, exist_ok=True)
    oss_uri = os.getenv("RUNBOOK_ALICLOUD_OSS_URI", "oss://<bucket>/runbook-aiops/training/")
    pai_workspace = os.getenv("RUNBOOK_ALICLOUD_PAI_WORKSPACE", "<workspace-id>")
    pai_spec = {
        "kind": "pai-dlc-training-job",
        "workspace_id": pai_workspace,
        "display_name": output_model_name,
        "base_model": base_model,
        "input_dataset": str(paths.compressed_jsonl),
        "input_dataset_oss_uri": oss_uri.rstrip("/") + f"/{paths.run_id}/compressed.jsonl",
        "output_model_oss_uri": oss_uri.rstrip("/") + f"/{paths.run_id}/model/",
        "image": os.getenv("RUNBOOK_ALICLOUD_TRAINING_IMAGE", "<pai-dlc-qwen-or-ms-swift-image>"),
        "command": "swift sft --model ${BASE_MODEL} --dataset ${INPUT_DATASET} --output_dir ${OUTPUT_DIR}",
        "env": {
            "BASE_MODEL": base_model,
            "INPUT_DATASET": "${PAI_INPUT_DATASET}",
            "OUTPUT_DIR": "${PAI_OUTPUT_MODEL_DIR}",
        },
        "dry_run": True,
        "notes": [
            "Upload compressed.jsonl/sft.jsonl to OSS before submitting a DLC job.",
            "Set RUNBOOK_ALICLOUD_AUTOPIPELINE_EXECUTE=true only after reviewing the generated job spec.",
        ],
    }
    dashscope_payload = {
        "base_model": base_model,
        "training_file": str(paths.sft_jsonl),
        "validation_file": "",
        "suffix": output_model_name,
        "metadata": {"run_id": paths.run_id, "source": "RunbookAIOps"},
        "dry_run": True,
        "note": "Template only. Submit through the current Alibaba Model Studio/DashScope fine-tuning flow used by your account/region.",
    }
    commands = {
        "upload_to_oss": f"ossutil cp -r {paths.run_dir} {oss_uri.rstrip('/')}/{paths.run_id}/",
        "pai_submit_placeholder": "aliyun pai CreateTrainingJob --body file://alicloud/pai_dlc_job_spec.json",
        "hermes_rl_cli": f"python rl_cli.py 'Train a RunbookAIOps model using {paths.compressed_jsonl}'",
        "hermes_compressor": f"python trajectory_compressor.py --input={paths.trajectories_jsonl} --output={paths.compressed_jsonl}",
    }
    _write_json(paths.alicloud_dir / "pai_dlc_job_spec.json", pai_spec)
    _write_json(paths.alicloud_dir / "dashscope_finetune_template.json", dashscope_payload)
    _write_json(paths.alicloud_dir / "handoff_commands.json", commands)
    return {"status": "ok", "dir": str(paths.alicloud_dir), "pai_spec": str(paths.alicloud_dir / "pai_dlc_job_spec.json"), "dashscope_template": str(paths.alicloud_dir / "dashscope_finetune_template.json"), "commands": commands}


def training_status() -> Dict[str, Any]:
    settings = load_settings()
    root = _training_root()
    latest = _latest_run_id()
    tinker_dir = ROOT / "tinker-atropos"
    tinker_initialized = bool(
        tinker_dir.is_dir()
        and any(tinker_dir.iterdir())
        and ((tinker_dir / "pyproject.toml").exists() or (tinker_dir / "README.md").exists())
    )
    official = {
        "batch_runner": str(ROOT / "batch_runner.py"),
        "batch_runner_exists": (ROOT / "batch_runner.py").exists(),
        "trajectory_compressor": str(ROOT / "trajectory_compressor.py"),
        "trajectory_compressor_exists": (ROOT / "trajectory_compressor.py").exists(),
        "rl_cli": str(ROOT / "rl_cli.py"),
        "rl_cli_exists": (ROOT / "rl_cli.py").exists(),
        "tinker_atropos": str(tinker_dir),
        "tinker_atropos_exists": tinker_initialized,
        "tinker_atropos_status": "available" if tinker_initialized else "submodule_not_initialized",
    }
    return {
        "status": "ok" if settings.runbook_training_enabled else "disabled",
        "enabled": bool(settings.runbook_training_enabled),
        "training_dir": str(root),
        "latest_run_id": latest,
        "stored_incidents": len(_settings_store().list_bucket("incidents")),
        "benchmark_cases": len(_load_benchmark_cases()),
        "min_reward": settings.runbook_training_min_reward,
        "alicloud_enabled": settings.runbook_alicloud_autopipeline_enabled,
        "alicloud_execute_enabled": settings.runbook_alicloud_autopipeline_execute,
        "external_launch_enabled": bool(getattr(settings, "runbook_training_external_launch_enabled", False)),
        "external_launch_token_configured": bool(getattr(settings, "runbook_training_external_launch_token", "")),
        "pipeline_isolation": "pipeline_run_is_always_dataset_export_only; use /training/external-launch for real external launch",
        "official_hermes_rl": official,
    }


def build_dataset(
    *,
    include_incidents: bool = True,
    include_benchmark_cases: bool = True,
    max_incidents: Optional[int] = None,
    min_reward: Optional[float] = None,
    run_id: str | None = None,
) -> Dict[str, Any]:
    settings = load_settings()
    if not settings.runbook_training_enabled:
        return {"status": "disabled", "reason": "RUNBOOK_TRAINING_ENABLED=false"}
    run_id = run_id or _short_id("train")
    paths = _paths(run_id)
    max_incidents = int(max_incidents if max_incidents is not None else settings.runbook_training_max_incidents)
    min_reward = float(min_reward if min_reward is not None else settings.runbook_training_min_reward)

    records: List[Dict[str, Any]] = []
    sources: Dict[str, int] = {"incident_store": 0, "benchmark_case": 0}
    if include_incidents:
        for incident in _stored_incidents(max_incidents):
            record = incident_to_trajectory_record(incident, source="incident_store", prompt_index=len(records))
            if float((record.get("reward") or {}).get("reward") or 0.0) >= min_reward:
                records.append(record)
                sources["incident_store"] += 1
    if include_benchmark_cases:
        for case in _load_benchmark_cases():
            incident = _synthetic_incident_from_case(case, len(records))
            record = incident_to_trajectory_record(incident, source="benchmark_case", prompt_index=len(records))
            if float((record.get("reward") or {}).get("reward") or 0.0) >= min_reward:
                records.append(record)
                sources["benchmark_case"] += 1

    if not records:
        return {"status": "empty", "reason": "no incidents or benchmark cases met the reward threshold", "min_reward": min_reward}

    prompts = _prompt_rows(records)
    sft = _sft_rows(records)
    prefs = _preference_rows(records)
    rewards = [{"metadata": row.get("metadata") or {}, "reward": row.get("reward") or {}} for row in records]
    _write_jsonl(paths.trajectories_jsonl, records)
    _write_jsonl(paths.prompts_jsonl, prompts)
    _write_jsonl(paths.sft_jsonl, sft)
    _write_jsonl(paths.preference_jsonl, prefs)
    _write_jsonl(paths.rewards_jsonl, rewards)
    manifest = {
        "status": "dataset_built",
        "run_id": run_id,
        "created_at": _now(),
        "record_count": len(records),
        "sources": sources,
        "min_reward": min_reward,
        "paths": paths.to_dict(),
        "formats": ["hermes_trajectories", "batch_runner_dataset", "sft_messages", "preference_pairs", "reward_jsonl"],
    }
    _write_json(paths.manifest_json, manifest)
    _settings_store().put("training_runs", run_id, {**manifest, "status": "dataset_built"})
    return {**manifest, "status": "ok", "phase": "dataset_built"}


def compress_dataset(*, run_id: str | None = None, max_message_chars: Optional[int] = None, use_hermes_compressor: bool = False) -> Dict[str, Any]:
    settings = load_settings()
    paths = _get_paths_for_run(run_id)
    max_message_chars = int(max_message_chars if max_message_chars is not None else settings.runbook_training_compress_max_chars)
    records = _read_jsonl(paths.trajectories_jsonl)
    if not records:
        return {"status": "empty", "reason": f"no trajectories at {paths.trajectories_jsonl}"}
    command = ["python", str(ROOT / "trajectory_compressor.py"), f"--input={paths.trajectories_jsonl}", f"--output={paths.compressed_jsonl}"]
    hermes_result: Dict[str, Any] = {"used": False, "command": " ".join(command)}
    if use_hermes_compressor:
        try:
            proc = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True, timeout=1800)
            hermes_result.update({"used": True, "returncode": proc.returncode, "stdout_tail": proc.stdout[-4000:], "stderr_tail": proc.stderr[-4000:]})
            if proc.returncode == 0 and paths.compressed_jsonl.exists():
                compressed_count = len(_read_jsonl(paths.compressed_jsonl))
                return {"status": "ok", "run_id": paths.run_id, "compressed_count": compressed_count, "path": str(paths.compressed_jsonl), "hermes_compressor": hermes_result}
        except Exception as exc:
            hermes_result.update({"used": True, "error": f"{type(exc).__name__}: {exc}"})
    compressed, changed = compress_records(records, max_message_chars=max_message_chars)
    _write_jsonl(paths.compressed_jsonl, compressed)
    manifest = json.loads(paths.manifest_json.read_text(encoding="utf-8")) if paths.manifest_json.exists() else {"run_id": paths.run_id}
    manifest.update({"status": "compressed", "compressed_at": _now(), "compressed_count": len(compressed), "messages_compressed": changed, "compressed_path": str(paths.compressed_jsonl), "hermes_compressor": hermes_result})
    _write_json(paths.manifest_json, manifest)
    _settings_store().put("training_runs", paths.run_id, manifest)
    return {"status": "ok", "run_id": paths.run_id, "compressed_count": len(compressed), "messages_compressed": changed, "path": str(paths.compressed_jsonl), "hermes_compressor": hermes_result}


def export_dataset(*, run_id: str | None = None, base_model: str | None = None, output_model_name: str | None = None) -> Dict[str, Any]:
    settings = load_settings()
    paths = _get_paths_for_run(run_id)
    if not paths.compressed_jsonl.exists():
        compress_dataset(run_id=paths.run_id)
    base_model = base_model or settings.runbook_training_base_model
    output_model_name = output_model_name or f"runbook-aiops-{paths.run_id}"
    handoff = _alicloud_handoff(paths, base_model=base_model, output_model_name=output_model_name)
    manifest = json.loads(paths.manifest_json.read_text(encoding="utf-8")) if paths.manifest_json.exists() else {"run_id": paths.run_id}
    manifest.update({"status": "exported", "exported_at": _now(), "base_model": base_model, "output_model_name": output_model_name, "alicloud_handoff": handoff})
    _write_json(paths.manifest_json, manifest)
    _settings_store().put("training_runs", paths.run_id, manifest)
    return {"status": "ok", "run_id": paths.run_id, "paths": paths.to_dict(), "base_model": base_model, "output_model_name": output_model_name, "alicloud_handoff": handoff}


def run_auto_pipeline(
    *,
    include_incidents: bool = True,
    include_benchmark_cases: bool = True,
    max_incidents: Optional[int] = None,
    min_reward: Optional[float] = None,
    base_model: str | None = None,
    output_model_name: str | None = None,
    use_hermes_compressor: bool = False,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Build/export a training package without launching external jobs.

    This function is intentionally isolated from real cloud launch. The caller's
    dry_run flag is recorded as requested_dry_run, but the pipeline always
    returns dry_run=True and never executes Alibaba/DashScope/other external
    jobs. Real launch is handled only by external_launch_training().
    """
    started = _now()
    requested_dry_run = bool(dry_run)
    steps: List[Dict[str, Any]] = []
    status = training_status()
    steps.append({"name": "status", "result": status})
    build = build_dataset(include_incidents=include_incidents, include_benchmark_cases=include_benchmark_cases, max_incidents=max_incidents, min_reward=min_reward)
    steps.append({"name": "build_dataset", "result": build})
    if build.get("status") != "ok":
        return {"status": "failed", "failed_step": "build_dataset", "steps": steps, "dry_run": True, "requested_dry_run": requested_dry_run, "external_launch_isolated": True}
    run_id = str(build.get("run_id"))
    compressed = compress_dataset(run_id=run_id, use_hermes_compressor=use_hermes_compressor)
    steps.append({"name": "compress", "result": compressed})
    if compressed.get("status") != "ok":
        return {"status": "failed", "failed_step": "compress", "run_id": run_id, "steps": steps, "dry_run": True, "requested_dry_run": requested_dry_run, "external_launch_isolated": True}
    exported = export_dataset(run_id=run_id, base_model=base_model, output_model_name=output_model_name)
    steps.append({"name": "export", "result": exported})
    launch = {
        "status": "isolated",
        "executed": False,
        "reason": "training pipeline is dataset/export only; call /training/external-launch with explicit gates for real launch",
    }
    steps.append({"name": "external_launch_isolated", "result": launch})
    result = {
        "status": "ok",
        "run_id": run_id,
        "duration_seconds": round(_now() - started, 3),
        "dry_run": True,
        "requested_dry_run": requested_dry_run,
        "external_launch_isolated": True,
        "steps": steps,
        "next_actions": [
            "Review manifest.json, compressed.jsonl and sft.jsonl.",
            "Run benchmark eval against the current model before changing production routing.",
            "Use /training/external-launch only after human approval and strong confirmation token.",
        ],
    }
    _settings_store().put("training_runs", run_id, {**(exported if isinstance(exported, dict) else {}), "status": "pipeline_ready", "pipeline": result})
    return result


def _try_alicloud_launch(pai_spec_path: Path) -> Dict[str, Any]:
    if not pai_spec_path.exists():
        return {"status": "error", "executed": False, "error": f"spec not found: {pai_spec_path}"}
    if shutil.which("aliyun") is None:
        return {"status": "skipped", "executed": False, "reason": "aliyun CLI not installed", "spec": str(pai_spec_path)}
    cmd = ["aliyun", "pai", "CreateTrainingJob", "--body", f"file://{pai_spec_path}"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return {"status": "ok" if proc.returncode == 0 else "error", "executed": True, "returncode": proc.returncode, "stdout_tail": proc.stdout[-4000:], "stderr_tail": proc.stderr[-4000:], "command": " ".join(cmd)}
    except Exception as exc:
        return {"status": "error", "executed": True, "error": f"{type(exc).__name__}: {exc}", "command": " ".join(cmd)}




def external_launch_training(run_id: str = "", confirmation_token: str = "") -> Dict[str, Any]:
    """Explicit, gated external training launch.

    This is the only path that can execute an external cloud job, and it is
    fail-closed unless all feature flags and the confirmation token are set.
    """
    settings = load_settings()
    run_id = str(run_id or _latest_run_id()).strip()
    if not getattr(settings, "runbook_training_external_launch_enabled", False):
        return {"status": "rejected", "executed": False, "reason": "RUNBOOK_TRAINING_EXTERNAL_LAUNCH_ENABLED is not true", "run_id": run_id}
    expected = getattr(settings, "runbook_training_external_launch_token", "")
    if not expected:
        return {"status": "rejected", "executed": False, "reason": "RUNBOOK_TRAINING_EXTERNAL_LAUNCH_TOKEN is not configured", "run_id": run_id}
    if str(confirmation_token or "") != str(expected):
        return {"status": "rejected", "executed": False, "reason": "invalid confirmation token", "run_id": run_id}
    if not (settings.runbook_alicloud_autopipeline_enabled and settings.runbook_alicloud_autopipeline_execute):
        return {"status": "rejected", "executed": False, "reason": "AliCloud AutoPipeline launch gates are disabled", "run_id": run_id}
    try:
        paths = _get_paths_for_run(run_id)
    except Exception as exc:
        return {"status": "rejected", "executed": False, "reason": str(exc), "run_id": run_id}
    if not paths.manifest_json.exists():
        return {"status": "rejected", "executed": False, "reason": "manifest not found", "run_id": run_id}
    if not (paths.alicloud_dir / "pai_dlc_job_spec.json").exists():
        export_dataset(run_id=run_id)
    result = _try_alicloud_launch(paths.alicloud_dir / "pai_dlc_job_spec.json")
    result["run_id"] = run_id
    result["external_launch"] = True
    return result


def list_training_runs(limit: int = 10) -> Dict[str, Any]:
    data = _settings_store().read("training_runs")
    rows = [item for item in data.values() if isinstance(item, dict)]
    rows.sort(key=lambda item: float(item.get("created_at") or item.get("exported_at") or 0), reverse=True)
    return {"status": "ok", "count": len(rows[:limit]), "runs": rows[:limit]}


def list_datasets(limit: int = 20) -> Dict[str, Any]:
    root = _training_root() / "runs"
    rows: List[Dict[str, Any]] = []
    for manifest in sorted(root.glob("*/manifest.json"), reverse=True):
        try:
            item = json.loads(manifest.read_text(encoding="utf-8"))
            item.setdefault("manifest_path", str(manifest))
            rows.append(item)
        except Exception:
            continue
        if len(rows) >= limit:
            break
    return {"status": "ok", "count": len(rows), "datasets": rows}
