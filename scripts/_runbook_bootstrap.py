from __future__ import annotations

from runbook_bootstrap import PROJECT_ROOT, bootstrap  # noqa: F401


def ensure_project_root():
    """Compatibility wrapper for older validation scripts."""
    return bootstrap()
