from __future__ import annotations

import sys
from pathlib import Path


def bootstrap() -> Path:
    """Put the project root on sys.path for directly executed runbook scripts."""
    root = Path(__file__).resolve().parents[1]
    root_s = str(root)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)
    return root


PROJECT_ROOT = bootstrap()
