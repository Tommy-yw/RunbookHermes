from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterable

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_MARKERS = ("data/runbook_mock", "skills/runbooks")


def _candidate_roots() -> list[Path]:
    roots: list[Path] = []
    env_root = os.getenv("RUNBOOK_RESOURCE_ROOT", "").strip()
    if env_root:
        roots.append(Path(env_root))
    roots.extend(
        [
            Path.cwd(),
            _PACKAGE_ROOT,
            Path(sys.prefix) / "share" / "hermes-agent",
            Path(getattr(sys, "base_prefix", sys.prefix)) / "share" / "hermes-agent",
        ]
    )
    seen: set[str] = set()
    out: list[Path] = []
    for root in roots:
        try:
            resolved = root.expanduser().resolve(strict=False)
        except Exception:
            resolved = root.expanduser()
        key = str(resolved)
        if key not in seen:
            seen.add(key)
            out.append(resolved)
    return out


def resource_root(markers: Iterable[str] = _DEFAULT_MARKERS) -> Path:
    """Return the root containing bundled RunbookHermes resources.

    Source checkouts, Docker images and installed wheels can place top-level
    data/profiles/skills/web resources in different locations. RUNBOOK_RESOURCE_ROOT
    is an explicit override; otherwise we discover the first root that contains
    the expected bundled resources.
    """

    marker_paths = [Path(marker) for marker in markers]
    for root in _candidate_roots():
        if all((root / marker).exists() for marker in marker_paths):
            return root
    return _PACKAGE_ROOT


def resource_path(*parts: str | os.PathLike[str]) -> Path:
    path = Path(*map(str, parts)) if parts else Path()
    if path.is_absolute():
        return path
    return resource_root() / path
