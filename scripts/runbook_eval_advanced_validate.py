#!/usr/bin/env python3
from __future__ import annotations

from runbook_bootstrap import PROJECT_ROOT, bootstrap
bootstrap()
ROOT = PROJECT_ROOT

import os
import sys
import tempfile
from pathlib import Path



def ok(label: str) -> None:
    print(f"[OK] {label}")


def assert_true(expr, label: str, payload=None) -> None:
    if not expr:
        raise AssertionError(f"{label}: {payload!r}")
    ok(label)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="runbook_eval_advanced_") as tmp:
        root = Path(tmp)
        os.environ["RUNBOOK_STORE_DIR"] = str(root / "store")
        os.environ["RUNBOOK_MEMORY_DIR"] = str(root / "memory")
        os.environ["RUNBOOK_RAG_DIR"] = str(root / "rag")
        os.environ["RUNBOOK_SKILL_PUBLISH_ENABLED"] = "false"
        os.environ["RUNBOOK_MODEL_ENABLED"] = "false"

        from runbook_hermes.eval import list_eval_cases, run_eval, save_postmortem_score, list_postmortem_scores

        cases = list_eval_cases()
        assert_true(cases.get("case_count", 0) >= 8, "advanced eval cases present", cases.get("case_count"))
        assert_true(cases.get("capabilities", {}).get("model_assisted_scoring"), "model assist capability advertised", cases.get("capabilities"))

        result = run_eval(persist=False, model_assist=True)
        metrics = result.get("metrics") or {}
        for key in (
            "evidence_recall_accuracy",
            "rag_citation_accuracy",
            "false_rollback_rate",
            "mttr_target_rate",
            "human_final_score",
            "model_judge_rate",
        ):
            assert_true(key in metrics, f"metric present: {key}", metrics)
        assert_true(metrics.get("pass_rate") == 1.0, "advanced benchmark pass rate", metrics)
        assert_true(metrics.get("evidence_recall_accuracy") == 1.0, "evidence recall accuracy", metrics)
        assert_true(metrics.get("rag_citation_accuracy") == 1.0, "RAG citation accuracy", metrics)
        assert_true(metrics.get("false_rollback_rate") == 0.0, "false rollback rate", metrics)
        first = (result.get("results") or [])[0]
        assert_true((first.get("model_judge") or {}).get("status") in {"disabled", "not_requested"}, "model judge uses existing disabled interface", first.get("model_judge"))

        saved = save_postmortem_score(case_id="payment_503_spike", final_score=0.81, reviewer="validator", notes="test review")
        assert_true(saved.get("status") == "ok", "postmortem score saved", saved)
        listed = list_postmortem_scores()
        assert_true(listed.get("count", 0) >= 1, "postmortem score listed", listed)

    print("[OK] RunbookAIOps advanced eval validation completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
