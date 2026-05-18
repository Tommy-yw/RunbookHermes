#!/usr/bin/env python3
from __future__ import annotations

from runbook_bootstrap import PROJECT_ROOT, bootstrap
bootstrap()
ROOT = PROJECT_ROOT

import argparse
import json
import sys
from pathlib import Path


from runbook_hermes.eval import list_eval_cases, run_eval


def main() -> int:
    parser = argparse.ArgumentParser(description="Run RunbookHermes deterministic benchmark/eval cases.")
    parser.add_argument("--case", action="append", dest="cases", default=[], help="Case id or scenario id to run. Can be repeated.")
    parser.add_argument("--persist", action="store_true", help="Persist incidents and eval run into RUNBOOK_STORE_DIR instead of a temporary store.")
    parser.add_argument("--model-assist", action="store_true", help="Request optional model-assisted scoring through the same RUNBOOK_MODEL_* interface.")
    parser.add_argument("--list", action="store_true", help="List benchmark cases and exit.")
    args = parser.parse_args()
    if args.list:
        print(json.dumps(list_eval_cases(), ensure_ascii=False, indent=2))
        return 0
    result = run_eval(case_ids=args.cases, persist=args.persist, model_assist=args.model_assist)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("metrics", {}).get("pass_rate", 0) >= 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
