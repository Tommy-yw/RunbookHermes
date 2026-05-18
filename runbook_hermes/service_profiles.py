from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .config import load_settings
from .resources import resource_path

_DEFAULT_PROFILE: Dict[str, Any] = {
    "service": "unknown",
    "owner": "unknown",
    "dependencies": [],
    "slo": {},
    "rollback": {"requires_approval": True, "requires_checkpoint": True},
    "rca_rules": [],
    "action_rules": {},
}


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def service_profiles_path() -> Path:
    settings = load_settings()
    configured = getattr(settings, "runbook_service_profiles_path", None)
    if configured:
        return Path(configured)
    return resource_path("data", "runbook_profiles", "services.json")


def load_all_service_profiles() -> Dict[str, Dict[str, Any]]:
    data = _read_json(service_profiles_path())
    services = data.get("services") if isinstance(data, dict) else {}
    if not isinstance(services, dict):
        return {}
    return {str(name): dict(profile) for name, profile in services.items() if isinstance(profile, dict)}


def load_service_profile(service: str) -> Dict[str, Any]:
    service = service or "unknown"
    profiles = load_all_service_profiles()
    profile = profiles.get(service) or profiles.get(service.replace("_", "-")) or {}
    merged = {**_DEFAULT_PROFILE, **profile}
    merged["service"] = profile.get("service") or service
    merged.setdefault("dependencies", [])
    merged.setdefault("rollback", {})
    merged.setdefault("rca_rules", [])
    merged.setdefault("action_rules", {})
    return merged


def compact_service_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "service": profile.get("service"),
        "owner": profile.get("owner"),
        "dependencies": list(profile.get("dependencies") or []),
        "slo": profile.get("slo") or {},
        "rollback": profile.get("rollback") or {},
        "rca_rule_ids": [r.get("rule_id") for r in profile.get("rca_rules") or [] if isinstance(r, dict)],
        "action_categories": sorted((profile.get("action_rules") or {}).keys()),
    }


def dependency_names(profile: Dict[str, Any]) -> List[str]:
    deps = profile.get("dependencies") or []
    if isinstance(deps, str):
        return [deps]
    return [str(dep) for dep in deps if str(dep).strip()]


def first_present(*values: Any) -> str:
    for value in values:
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""
