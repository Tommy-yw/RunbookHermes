from __future__ import annotations

import os
import subprocess
from pathlib import Path


def test_eval_regression_gate_passes(tmp_path):
    root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env.update({
        "RUNBOOK_STORE_DIR": str(tmp_path / "store"),
        "RUNBOOK_RAG_DIR": str(tmp_path / "store" / "rag"),
        "RUNBOOK_TRAINING_DIR": str(tmp_path / "store" / "training"),
        "RUNBOOK_API_AUTH_ENABLED": "false",
        "RUNBOOK_MODEL_ENABLED": "false",
    })
    subprocess.run(
        [
            "python",
            str(root / "scripts" / "runbook_eval_regression_gate.py"),
            "--min-pass-rate", "0.80",
            "--min-score", "0.80",
            "--min-rag-citation", "0.70",
        ],
        cwd=root,
        env=env,
        check=True,
        timeout=120,
    )
