from __future__ import annotations

import json
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable

from .config import Settings, load_settings

_MUTATION_BACKENDS = {"custom_http", "kubernetes", "argocd", "demo_file"}


def _audit_id(incident: Dict[str, Any] | None, action: Dict[str, Any]) -> str:
    incident_id = (incident or {}).get("incident_id") or "standalone"
    action_type = str(action.get("action_type") or "unknown").replace(" ", "_")
    return f"audit_{incident_id}_{action_type}_{int(time.time())}_{uuid.uuid4().hex[:8]}"


def _allowed_operations(settings: Settings) -> set[str]:
    return {str(op).strip().lower() for op in (settings.action_execution_allowed_operations or ()) if str(op).strip()}


def _operation_allowed(action_type: str, settings: Settings) -> bool:
    allowed = _allowed_operations(settings)
    if not allowed:
        return False
    normalized = str(action_type or "").strip().lower()
    return normalized in allowed or "*" in allowed


def _approval_record(approval_id: str | None) -> Dict[str, Any]:
    if not approval_id:
        return {}
    try:
        from .approval import get_approval

        return get_approval(approval_id) or {}
    except Exception:  # pragma: no cover - defensive boundary
        return {}


def _confirmation_sources(action: Dict[str, Any], execution_context: Dict[str, Any], approval: Dict[str, Any]) -> Iterable[str]:
    args = action.get("args") if isinstance(action.get("args"), dict) else {}
    values = [
        execution_context.get("confirmation_token"),
        execution_context.get("confirm_token"),
        execution_context.get("second_confirmation"),
        execution_context.get("secondary_confirmation"),
        action.get("confirmation_token"),
        action.get("confirm_token"),
        action.get("second_confirmation"),
        action.get("secondary_confirmation"),
        args.get("confirmation_token"),
        args.get("confirm_token"),
        args.get("second_confirmation"),
        args.get("secondary_confirmation"),
        approval.get("confirmation_token"),
        approval.get("second_confirmation"),
        approval.get("secondary_confirmation"),
        approval.get("comment"),
    ]
    for value in values:
        if value is not None and str(value).strip():
            yield str(value).strip()


def _confirm_flag(action: Dict[str, Any], execution_context: Dict[str, Any], approval: Dict[str, Any]) -> bool:
    args = action.get("args") if isinstance(action.get("args"), dict) else {}
    return bool(
        execution_context.get("confirm_execution")
        or action.get("confirm_execution")
        or args.get("confirm_execution")
        or args.get("confirmed")
        or approval.get("confirm_execution")
    )


def _second_confirmation_ok(
    action: Dict[str, Any],
    execution_context: Dict[str, Any],
    settings: Settings,
    *,
    approval: Dict[str, Any],
    audit_id: str,
    approval_id: str | None,
    action_type: str,
) -> tuple[bool, str]:
    if not settings.action_execution_require_second_confirmation:
        return True, "not_required"

    expected_tokens = {"confirmed", f"confirm:{audit_id}", f"confirm:{action_type}"}
    if approval_id:
        expected_tokens.add(f"confirm:{approval_id}")
    if settings.action_execution_confirmation_token:
        expected_tokens.add(settings.action_execution_confirmation_token)

    normalized_sources = [source.lower() for source in _confirmation_sources(action, execution_context, approval)]
    for source in normalized_sources:
        for token in expected_tokens:
            token_norm = str(token).lower()
            if source == token_norm or token_norm in source:
                return True, "confirmed"

    if _confirm_flag(action, execution_context, approval) and not settings.action_execution_confirmation_token:
        return True, "confirmed"

    if settings.action_execution_confirmation_token:
        return False, "confirmation_token_mismatch"
    return False, "missing_confirm_execution"


def _audit_path(settings: Settings) -> Path | None:
    raw = getattr(settings, "action_execution_audit_log_file", None)
    if not raw:
        return None
    path = Path(raw)
    if str(path).strip().lower() in {"", "none", "off", "false"}:
        return None
    return path


def _finalize(settings: Settings, record: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(record)
    out.setdefault("audited_at", time.time())
    path = _audit_path(settings)
    if not path:
        return out
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(out, ensure_ascii=False, sort_keys=True) + "\n")
        out["audit_log_file"] = str(path)
    except Exception as exc:  # pragma: no cover - filesystem dependent
        out["audit_write_error"] = str(exc)
    return out


def execute_non_rollback_action(
    action: Dict[str, Any],
    incident: Dict[str, Any] | None = None,
    approval_id: str | None = None,
    settings: Settings | None = None,
    execution_context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Execute or route a non-rollback action through controlled gates.

    Rollbacks use their own checkpoint-backed path. All other mutations must
    pass: explicit backend, operation allowlist, approved approval_id, second
    confirmation, and audit metadata propagation.
    """

    settings = settings or load_settings()
    execution_context = execution_context or {}
    action_type = str(action.get("action_type", "unknown"))
    audit_id = str(execution_context.get("audit_id") or action.get("audit_id") or _audit_id(incident, action))
    payload = {
        "status": "executor_not_configured",
        "audit_id": audit_id,
        "action_type": action_type,
        "approval_id": approval_id,
        "incident_id": (incident or {}).get("incident_id"),
        "service": action.get("args", {}).get("service") if isinstance(action.get("args"), dict) else (incident or {}).get("service"),
        "backend": settings.action_execution_backend,
        "allowed_operations": sorted(_allowed_operations(settings)),
        "second_confirmation_required": bool(settings.action_execution_require_second_confirmation),
        "message": "No controlled executor is enabled for this non-rollback action.",
        "expected_next_step": "Configure ACTION_EXECUTION_BACKEND, ACTION_EXECUTION_ALLOWED_TYPES/ACTION_EXECUTION_ALLOWED_OPERATIONS, and second confirmation before enabling production mutation.",
    }

    def finish(update: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return _finalize(settings, {**payload, **(update or {})})

    backend = settings.action_execution_backend.lower().strip()
    if backend in {"", "none"}:
        return finish()

    if backend in _MUTATION_BACKENDS:
        if not _operation_allowed(action_type, settings):
            return finish(
                {
                    "status": "operation_not_allowlisted",
                    "message": f"Action type {action_type!r} is not in ACTION_EXECUTION_ALLOWED_TYPES/ACTION_EXECUTION_ALLOWED_OPERATIONS.",
                }
            )
        approval = _approval_record(approval_id)
        if not approval or approval.get("status") != "approved":
            return finish({"status": "approval_required", "message": "Approved approval_id is required before executor handoff."})
        confirmed, reason = _second_confirmation_ok(
            action,
            execution_context,
            settings,
            approval=approval,
            audit_id=audit_id,
            approval_id=approval_id,
            action_type=action_type,
        )
        if not confirmed:
            return finish(
                {
                    "status": "second_confirmation_required" if reason == "missing_confirm_execution" else "second_confirmation_failed",
                    "confirmation_reason": reason,
                    "accepted_confirmation_examples": [f"confirm:{approval_id}" if approval_id else "", f"confirm:{audit_id}", f"confirm:{action_type}", settings.action_execution_confirmation_token, "confirmed"],
                    "message": "Approved non-rollback mutations require explicit second confirmation before executor handoff.",
                }
            )

    if backend == "demo_file":
        return finish(
            {
                "status": "demo_execution_recorded",
                "message": "Demo executor recorded approval for this action. No production system was changed.",
            }
        )

    if backend == "custom_http":
        if not settings.action_execution_api_base_url:
            return finish({"status": "not_configured", "message": "ACTION_EXECUTION_API_BASE_URL is empty."})
        body = json.dumps({"audit_id": audit_id, "action": action, "incident": incident or {}, "approval_id": approval_id}).encode("utf-8")
        headers = {"Content-Type": "application/json", "X-Runbook-Audit-Id": audit_id}
        if settings.action_execution_api_token:
            headers["Authorization"] = f"Bearer {settings.action_execution_api_token}"
        req = urllib.request.Request(
            settings.action_execution_api_base_url.rstrip("/") + "/actions/execute",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=settings.action_execution_timeout_seconds) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return finish({"status": "custom_http_executed", "response": data})
        except Exception as exc:  # pragma: no cover - network dependent
            return finish({"status": "custom_http_error", "error": str(exc)})

    if backend in {"kubernetes", "argocd"}:
        return finish(
            {
                "status": "adapter_shell_ready",
                "message": f"{backend} adapter shell passed allowlist/approval/confirmation gates, but the adapter is still reserved until credentials and recovery checks are implemented.",
            }
        )

    return finish({"status": "unknown_backend", "message": f"Unknown ACTION_EXECUTION_BACKEND={settings.action_execution_backend}"})
