from __future__ import annotations

import os
import subprocess
from pathlib import Path


def test_docker_static_smoke_script():
    root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["RUNBOOK_DOCKER_SMOKE_MODE"] = "static"
    subprocess.run([str(root / "scripts" / "runbook_docker_smoke.sh")], cwd=root, env=env, check=True)
