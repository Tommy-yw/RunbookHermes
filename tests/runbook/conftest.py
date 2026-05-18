from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def isolated_runbook_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    store = tmp_path / "store"
    monkeypatch.setenv("RUNBOOK_STORE_DIR", str(store))
    monkeypatch.setenv("RUNBOOK_RAG_DIR", str(store / "rag"))
    monkeypatch.setenv("RUNBOOK_TRAINING_DIR", str(store / "training"))
    monkeypatch.setenv("RUNBOOK_API_AUTH_ENABLED", "true")
    monkeypatch.setenv("RUNBOOK_API_TOKEN", "test-token")
    monkeypatch.setenv("RUNBOOK_API_READ_ONLY_TOKEN", "read-token")
    monkeypatch.setenv("RUNBOOK_MODEL_ENABLED", "false")
    monkeypatch.setenv("RUNBOOK_CONTROLLED_EXECUTION_ENABLED", "false")
    monkeypatch.setenv("RUNBOOK_EVAL_PERSIST_DEFAULT", "false")
    monkeypatch.delenv("RUNBOOK_TRAINING_EXTERNAL_LAUNCH_ENABLED", raising=False)
    monkeypatch.delenv("RUNBOOK_TRAINING_EXTERNAL_LAUNCH_TOKEN", raising=False)
    return store
