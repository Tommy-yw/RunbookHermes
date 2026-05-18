#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run RunbookHermes benchmark eval and enforce regression thresholds.")
    parser.add_argument("--min-pass-rate", type=float, default=0.85)
    parser.add_argument("--min-score", type=float, default=0.85)
    parser.add_argument("--min-rag-citation", type=float, default=0.75)
    parser.add_argument("--min-evidence-recall", type=float, default=0.75)
    parser.add_argument("--max-false-rollback", "--max-false-rollback-rate", dest="max_false_rollback", type=float, default=0.0)
    parser.add_argument("--persist", action="store_true")
    parser.add_argument("--case-id", action="append", default=[])
    args = parser.parse_args()

    temp_store = None
    if not args.persist and not os.environ.get("RUNBOOK_STORE_DIR"):
        temp_store = tempfile.TemporaryDirectory(prefix="runbook_eval_gate_")
        os.environ["RUNBOOK_STORE_DIR"] = temp_store.name
        os.environ["RUNBOOK_RAG_DIR"] = str(Path(temp_store.name) / "rag")
        os.environ["RUNBOOK_TRAINING_DIR"] = str(Path(temp_store.name) / "training")
    os.environ.setdefault("RUNBOOK_API_AUTH_ENABLED", "false")
    os.environ.setdefault("RUNBOOK_MODEL_ENABLED", "false")
    os.environ.setdefault("RUNBOOK_EVAL_PERSIST_DEFAULT", "false")

    from runbook_hermes.eval import run_eval

    result = run_eval(case_ids=args.case_id, persist=args.persist, model_assist=False)
    metrics = result.get("metrics") or {}
    checks = {
        "pass_rate": (float(metrics.get("pass_rate") or 0.0), args.min_pass_rate, ">="),
        "score": (float(metrics.get("score") or 0.0), args.min_score, ">="),
        "rag_citation_accuracy": (float(metrics.get("rag_citation_accuracy") or 0.0), args.min_rag_citation, ">="),
        "evidence_recall_accuracy": (float(metrics.get("evidence_recall_accuracy") or 0.0), args.min_evidence_recall, ">="),
        "false_rollback_rate": (float(metrics.get("false_rollback_rate") or 0.0), args.max_false_rollback, "<="),
    }
    failures = []
    for name, (actual, threshold, op) in checks.items():
        ok = actual >= threshold if op == ">=" else actual <= threshold
        if not ok:
            failures.append({"metric": name, "actual": actual, "threshold": threshold, "operator": op})
    payload = {"status": "ok" if not failures else "failed", "metrics": metrics, "failures": failures, "run_id": result.get("run_id")}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if temp_store is not None:
        temp_store.cleanup()
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
