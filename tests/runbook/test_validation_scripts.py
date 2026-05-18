from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


CORE_VALIDATION_COMMANDS = [
    ["scripts/runbook_validate.py"],
    ["scripts/runbook_gateway_smoke.py", "--all"],
    ["scripts/runbook_web_api_smoke.py"],
    ["scripts/runbook_stage2_4_validate.py"],
    ["scripts/runbook_stage5_7_validate.py"],
]

INTEGRATION_VALIDATION_COMMANDS = [
    ["scripts/runbook_fix_patch_validate.py"],
    ["scripts/runbook_hardening_validate.py"],
    ["scripts/runbook_phase3_4_validate.py"],
    ["scripts/runbook_stage8_validate.py"],
    ["scripts/runbook_memory_validate.py"],
    ["scripts/runbook_training_validate.py"],
    ["scripts/runbook_eval_advanced_validate.py"],
    ["scripts/runbook_hermes_bridge_validate.py"],
]


@pytest.mark.parametrize("command", CORE_VALIDATION_COMMANDS, ids=lambda c: Path(c[0]).stem)
def test_validation_scripts_under_pytest(command: list[str], isolated_runbook_env: Path) -> None:
    env = os.environ.copy()
    env["RUNBOOK_STORE_DIR"] = str(isolated_runbook_env / Path(command[0]).stem)
    env["RUNBOOK_RAG_DIR"] = str(isolated_runbook_env / Path(command[0]).stem / "rag")
    env["RUNBOOK_TRAINING_DIR"] = str(isolated_runbook_env / Path(command[0]).stem / "training")
    env["RUNBOOK_API_AUTH_ENABLED"] = "false"
    env["RUNBOOK_MODEL_ENABLED"] = "false"
    env["RUNBOOK_EVAL_MODEL_ASSIST_ENABLED"] = "false"
    env["ACTION_EXECUTION_SECOND_CONFIRMATION_REQUIRED"] = "false"
    proc = subprocess.run([sys.executable, *command], text=True, capture_output=True, cwd=Path(__file__).resolve().parents[2], env=env, timeout=240)
    assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.mark.integration
@pytest.mark.parametrize("command", INTEGRATION_VALIDATION_COMMANDS, ids=lambda c: Path(c[0]).stem)
def test_integration_validation_scripts(command: list[str], isolated_runbook_env: Path) -> None:
    env = os.environ.copy()
    env["RUNBOOK_STORE_DIR"] = str(isolated_runbook_env / Path(command[0]).stem)
    env["RUNBOOK_RAG_DIR"] = str(isolated_runbook_env / Path(command[0]).stem / "rag")
    env["RUNBOOK_TRAINING_DIR"] = str(isolated_runbook_env / Path(command[0]).stem / "training")
    env["RUNBOOK_API_AUTH_ENABLED"] = "false"
    env["RUNBOOK_MODEL_ENABLED"] = "false"
    env["RUNBOOK_EVAL_MODEL_ASSIST_ENABLED"] = "false"
    env["ACTION_EXECUTION_SECOND_CONFIRMATION_REQUIRED"] = "false"
    proc = subprocess.run([sys.executable, *command], text=True, capture_output=True, cwd=Path(__file__).resolve().parents[2], env=env, timeout=300)
    assert proc.returncode == 0, proc.stdout + proc.stderr
