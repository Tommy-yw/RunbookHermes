from __future__ import annotations

import json
import urllib.request
from typing import Any, Dict

from .config import Settings, load_settings


def execute_non_rollback_action(
    action: Dict[str, Any],
    incident: Dict[str, Any] | None = None,
    approval_id: str | None = None,
    settings: Settings | None = None,
) -> Dict[str, Any]:
    """Execute or route a non-rollback action.

    This is intentionally a controlled shell. RunbookHermes can approve an
    action and record the handoff, but production mutations must be connected
    explicitly through ACTION_EXECUTION_BACKEND.

    Supported modes:
    - none: do not mutate anything; return a clear handoff payload.
    - custom_http: POST to ACTION_EXECUTION_API_BASE_URL/actions/execute.
    - kubernetes / argocd: reserved adapters, return not_configured until
      production credentials and command allowlists are implemented.
    - demo_file: record a demo success without touching external systems.
    """

    settings = settings or load_settings()
    action_type = action.get("action_type", "unknown")
    payload = {
        "status": "executor_not_configured",
        "action_type": action_type,
        "approval_id": approval_id,
        "incident_id": (incident or {}).get("incident_id"),
        "service": action.get("args", {}).get("service") or (incident or {}).get("service"),
        "backend": settings.action_execution_backend,
        "message": "No controlled executor is enabled for this non-rollback action.",
        "expected_next_step": "Implement a custom_http, kubernetes or argocd adapter before enabling production mutation.",
    }

    backend = settings.action_execution_backend.lower().strip()
    if backend in {"", "none"}:
        return payload

    if backend == "demo_file":
        return {
            **payload,
            "status": "demo_execution_recorded",
            "message": "Demo executor recorded approval for this action. No production system was changed.",
        }

    if backend == "custom_http":
        if not settings.action_execution_api_base_url:
            return {**payload, "status": "not_configured", "message": "ACTION_EXECUTION_API_BASE_URL is empty."}
        body = json.dumps({"action": action, "incident": incident or {}, "approval_id": approval_id}).encode("utf-8")
        req = urllib.request.Request(
            settings.action_execution_api_base_url.rstrip("/") + "/actions/execute",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {settings.action_execution_api_token}" if settings.action_execution_api_token else "",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=settings.action_execution_timeout_seconds) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return {**payload, "status": "custom_http_executed", "response": data}
        except Exception as exc:  # pragma: no cover - network dependent
            return {**payload, "status": "custom_http_error", "error": str(exc)}

    if backend in {"kubernetes", "argocd"}:
        return {
            **payload,
            "status": "adapter_shell_ready",
            "message": f"{backend} adapter shell is reserved. Add allowlisted operations, credentials, and recovery checks before enabling it.",
        }

    return {**payload, "status": "unknown_backend", "message": f"Unknown ACTION_EXECUTION_BACKEND={settings.action_execution_backend}"}
