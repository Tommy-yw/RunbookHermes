from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> None:
    checks: dict[str, bool] = {}
    details: dict[str, object] = {}

    deploy_state = json.loads(_read("data/payment_demo/deployments.json"))
    version_text = _read("data/payment_demo/runtime/payment-service-version.txt").strip()
    checks["payment_demo_initial_version_v231"] = version_text == "v2.3.1" and deploy_state["services"]["payment-service"]["current_version"] == "v2.3.1"
    details["payment_demo_version"] = version_text

    obs_paths = [
        "demo/payment_system/services/payment_service/observability.py",
        "demo/payment_system/services/order_service/observability.py",
        "demo/payment_system/services/coupon_service/observability.py",
    ]
    obs_text = "\n".join(_read(p) for p in obs_paths)
    checks["http_status_codes_preserved"] = "except HTTPException as exc" in obs_text and "set_status(exc.status_code)" in obs_text and "status = '500'" not in obs_text and 'status = "500"' not in obs_text
    checks["jaeger_spans_created"] = "start_as_current_span" in obs_text and "http.status_code" in obs_text and "http.route" in obs_text

    os.environ["ACTION_EXECUTION_BACKEND"] = "custom_http"
    os.environ["ACTION_EXECUTION_API_BASE_URL"] = "http://executor.local"
    os.environ["ACTION_EXECUTION_API_TOKEN"] = "secret"
    os.environ["ACTION_EXECUTION_TIMEOUT_SECONDS"] = "9"
    from runbook_hermes.config import load_settings

    settings = load_settings()
    checks["action_execution_env_loaded"] = (
        settings.action_execution_backend == "custom_http"
        and settings.action_execution_api_base_url == "http://executor.local"
        and settings.action_execution_api_token == "secret"
        and settings.action_execution_timeout_seconds == 9
    )

    from runbook_hermes.events import ALLOWED_EVENTS

    checks["recovery_verified_allowed"] = "recovery.verified" in ALLOWED_EVENTS

    gateway_files = [
        "runbook_hermes/gateway/alertmanager.py",
        "runbook_hermes/gateway/feishu.py",
        "runbook_hermes/gateway/wecom.py",
    ]
    checks["gateway_normalizers_do_not_record_by_service"] = all("record_event" not in _read(path) for path in gateway_files)

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["RUNBOOK_STORE_DIR"] = tmp
        os.environ["ROLLBACK_BACKEND_KIND"] = "mock"
        os.environ["RUNBOOK_CONTROLLED_EXECUTION_ENABLED"] = "false"
        from runbook_hermes import incident_service as svc

        inc1 = svc.create_incident("payment-service HTTP 503 spike after v2.3.1 release", source="fix-patch-test")
        inc2 = svc.create_incident("payment-service HTTP 503 spike after v2.3.1 release", source="fix-patch-test")
        full1 = svc.get_incident(inc1["incident_id"])
        full2 = svc.get_incident(inc2["incident_id"])
        checks["approval_checkpoint_bound_to_incident_id"] = (
            len(full1.get("approvals", [])) == 1
            and len(full1.get("checkpoints", [])) == 1
            and full1["approvals"][0].get("incident_id") == inc1["incident_id"]
            and full1["checkpoints"][0].get("incident_id") == inc1["incident_id"]
            and len(full2.get("approvals", [])) == 1
            and full2["approvals"][0].get("incident_id") == inc2["incident_id"]
        )
        approval_id = full1.get("approval_id")
        svc.decide(approval_id, "approved", approver="fix-patch-test")
        events = svc.get_events(inc1["incident_id"])
        event_types = [event.get("event_type") for event in events]
        checks["recovery_event_records_correct_type"] = "recovery.verified" in event_types
        details["incident_binding_event_types"] = event_types

    ok = all(checks.values())
    report = {"ok": ok, "scope": "runbook-fix-patch", "checks": checks, "details": details}
    out = ROOT / ".artifacts"
    out.mkdir(exist_ok=True)
    (out / "runbook_fix_patch_validation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
