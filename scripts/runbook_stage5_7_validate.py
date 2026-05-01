from __future__ import annotations

import json
import os
from pathlib import Path

from runbook_hermes.tools import rollback_canary, runbook_approval_decision, verify_recovery

ROOT = Path(__file__).resolve().parents[1]


def exists(path: str) -> bool:
    return (ROOT / path).exists()


def main() -> None:
    checks = {}
    checks["payment_demo_compose"] = exists("demo/payment_system/docker-compose.yml")
    checks["payment_service"] = exists("demo/payment_system/services/payment_service/main.py")
    checks["prometheus_config"] = exists("demo/payment_system/prometheus/prometheus.yml")
    checks["promtail_config"] = exists("demo/payment_system/promtail/promtail-config.yml")
    checks["demo_deploy_state"] = exists("data/payment_demo/deployments.json")
    checks["demo_version_file"] = exists("data/payment_demo/runtime/payment-service-version.txt")
    checks["no_ambiguous_status_terms"] = True
    for folder in ["runbook_hermes", "integrations", "toolservers", "profiles/runbook-hermes", "skills/runbooks", "data/runbook_mock", "data/runbook_samples", "docs/runbook-hermes", "scripts"]:
        root = ROOT / folder
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in {".py", ".md", ".json", ".yaml", ".yml", ".txt", ".example"}:
                text = path.read_text(encoding="utf-8", errors="ignore")
                bad_terms = ["5" + "xx", "_5" + "xx", "payment-" + "5" + "xx"]
                if any(term in text for term in bad_terms):
                    checks["no_ambiguous_status_terms"] = False
                    break

    version_path = ROOT / "data/payment_demo/runtime/payment-service-version.txt"
    deploy_path = ROOT / "data/payment_demo/deployments.json"
    original_version = version_path.read_text(encoding="utf-8") if version_path.exists() else ""
    original_deploy_state = deploy_path.read_text(encoding="utf-8") if deploy_path.exists() else ""

    executed = {}
    recovery = {}
    try:
        # Controlled demo rollback path: first call must request approval, then approved call writes demo version.
        os.environ["ROLLBACK_BACKEND_KIND"] = "demo_file"
        os.environ["RUNBOOK_CONTROLLED_EXECUTION_ENABLED"] = "true"
        os.environ["DEMO_VERSION_FILE"] = str(version_path)
        os.environ["DEMO_DEPLOY_STATE_FILE"] = str(deploy_path)
        gate = json.loads(rollback_canary({"service": "payment-service", "target_revision": "v2.3.0", "dry_run": False}))
        checks["approval_required_for_execution"] = bool(gate.get("status") == "approval_required" and gate.get("approval_id") and gate.get("checkpoint_id"))
        json.loads(runbook_approval_decision({"approval_id": gate.get("approval_id"), "decision": "approved", "approver": "stage5-7"}))
        executed = json.loads(rollback_canary({"service": "payment-service", "target_revision": "v2.3.0", "dry_run": False, "approval_id": gate.get("approval_id")}))
        checks["controlled_execution"] = executed.get("status") == "controlled_execution_succeeded"
        checks["version_file_updated"] = version_path.read_text(encoding="utf-8").strip() == "v2.3.0"
        recovery = json.loads(verify_recovery({"service": "payment-service"}))
        checks["verify_recovery"] = recovery.get("status") in {"recovered", "verification_query_sent"}
    finally:
        # Keep release artifacts in the failing v2.3.1 state.  Validation may
        # temporarily exercise rollback, but it must not package the rolled-back
        # state again.
        if original_version:
            version_path.write_text(original_version, encoding="utf-8")
        if original_deploy_state:
            deploy_path.write_text(original_deploy_state, encoding="utf-8")

    ok = all(checks.values())
    report = {"ok": ok, "scope": "stage5-7", "checks": checks, "execution": executed, "recovery": recovery, "state_restored_after_validation": True}
    out = ROOT / ".artifacts"
    out.mkdir(exist_ok=True)
    (out / "runbook_stage5_7_validation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
