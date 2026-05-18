#!/usr/bin/env python3
from __future__ import annotations

from runbook_bootstrap import PROJECT_ROOT, bootstrap
bootstrap()
ROOT = PROJECT_ROOT

import json
import sys
import os
import shutil
import tempfile
from pathlib import Path



def ok(label: str) -> None:
    print(f"[OK] {label}")


def assert_true(expr, label: str):
    if not expr:
        raise AssertionError(label)
    ok(label)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="runbook_training_validate_") as tmp:
        root = Path(tmp)
        os.environ["RUNBOOK_STORE_DIR"] = str(root / "store")
        os.environ["RUNBOOK_MEMORY_DIR"] = str(root / "memory")
        os.environ["RUNBOOK_RAG_DIR"] = str(root / "rag")
        os.environ["RUNBOOK_TRAINING_DIR"] = str(root / "training")
        os.environ["RUNBOOK_SKILL_PUBLISH_ENABLED"] = "false"
        os.environ["RUNBOOK_API_AUTH_ENABLED"] = "true"
        os.environ["RUNBOOK_API_TOKEN"] = "write-token"
        os.environ["RUNBOOK_API_READ_ONLY_TOKEN"] = "read-token"

        from runbook_hermes import incident_service as svc
        from runbook_hermes.api_auth import _is_public_path
        from runbook_hermes.training import build_dataset, compress_dataset, export_dataset, run_auto_pipeline, training_status
        from runbook_hermes.tools import runbook_training_pipeline

        incident = svc.create_incident("payment-service HTTP 503 spike after release", "payment-service", "p1", "prod", "training-validate")
        assert_true(bool(incident.get("incident_id")), "incident created for training harvest")
        status = training_status()
        assert_true(status.get("official_hermes_rl", {}).get("batch_runner_exists"), "Hermes batch_runner detected")
        assert_true(status.get("official_hermes_rl", {}).get("trajectory_compressor_exists"), "Hermes trajectory_compressor detected")
        assert_true(_is_public_path("/web/index.html") and not _is_public_path("/webhook"), "API auth public prefix is exact")

        built = build_dataset(include_incidents=True, include_benchmark_cases=True)
        assert_true(built.get("status") == "ok" and built.get("record_count", 0) >= 4, "training dataset built")
        paths = built.get("paths") or {}
        for key in ("trajectories_jsonl", "prompts_jsonl", "sft_jsonl", "preference_jsonl", "rewards_jsonl"):
            assert_true(Path(paths[key]).exists(), f"dataset file exists: {key}")
        sample = json.loads(Path(paths["trajectories_jsonl"]).read_text(encoding="utf-8").splitlines()[0])
        assert_true(sample.get("conversations") and sample.get("reward", {}).get("reward", 0) >= 0.65, "trajectory contains reward")

        compressed = compress_dataset(run_id=built.get("run_id"))
        assert_true(compressed.get("status") == "ok" and Path(compressed.get("path", "")).exists(), "training dataset compressed")
        exported = export_dataset(run_id=built.get("run_id"))
        handoff = exported.get("alicloud_handoff") or {}
        assert_true(Path(handoff.get("pai_spec", "")).exists(), "PAI handoff generated")
        assert_true(Path(handoff.get("dashscope_template", "")).exists(), "DashScope handoff generated")

        piped = run_auto_pipeline(include_incidents=True, include_benchmark_cases=True, dry_run=True)
        assert_true(piped.get("status") == "ok" and piped.get("dry_run") is True, "AutoPipeline dry run completed")
        tool_result = json.loads(runbook_training_pipeline({"dry_run": True}))
        assert_true(tool_result.get("status") == "ok", "Hermes tool training pipeline works")

    print("[OK] RunbookAIOps training/RL/AutoPipeline validation completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
