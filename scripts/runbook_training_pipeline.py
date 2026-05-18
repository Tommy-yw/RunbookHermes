#!/usr/bin/env python3
from __future__ import annotations

from runbook_bootstrap import PROJECT_ROOT, bootstrap
bootstrap()
ROOT = PROJECT_ROOT

import sys
from pathlib import Path


import argparse
import json
import sys

from runbook_hermes.training import build_dataset, compress_dataset, export_dataset, run_auto_pipeline, training_status


def main() -> int:
    parser = argparse.ArgumentParser(description="RunbookAIOps training/RL/AutoPipeline helper")
    parser.add_argument("--status", action="store_true", help="print training status")
    parser.add_argument("--build", action="store_true", help="build training datasets")
    parser.add_argument("--compress", action="store_true", help="compress latest or specified run")
    parser.add_argument("--export", action="store_true", help="export handoff templates")
    parser.add_argument("--pipeline", action="store_true", help="run build + compress + export")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--max-incidents", type=int, default=None)
    parser.add_argument("--min-reward", type=float, default=None)
    parser.add_argument("--base-model", default="")
    parser.add_argument("--output-model-name", default="")
    parser.add_argument("--no-incidents", action="store_true")
    parser.add_argument("--no-benchmark-cases", action="store_true")
    parser.add_argument("--use-hermes-compressor", action="store_true")
    parser.add_argument("--execute", action="store_true", help="allow external launch if env gates are enabled")
    args = parser.parse_args()

    if args.status or not any([args.build, args.compress, args.export, args.pipeline]):
        result = training_status()
    elif args.build:
        result = build_dataset(
            include_incidents=not args.no_incidents,
            include_benchmark_cases=not args.no_benchmark_cases,
            max_incidents=args.max_incidents,
            min_reward=args.min_reward,
        )
    elif args.compress:
        result = compress_dataset(run_id=args.run_id or None, use_hermes_compressor=args.use_hermes_compressor)
    elif args.export:
        result = export_dataset(run_id=args.run_id or None, base_model=args.base_model or None, output_model_name=args.output_model_name or None)
    else:
        result = run_auto_pipeline(
            include_incidents=not args.no_incidents,
            include_benchmark_cases=not args.no_benchmark_cases,
            max_incidents=args.max_incidents,
            min_reward=args.min_reward,
            base_model=args.base_model or None,
            output_model_name=args.output_model_name or None,
            use_hermes_compressor=args.use_hermes_compressor,
            dry_run=not args.execute,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") in {"ok", "disabled", "dry_run"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
