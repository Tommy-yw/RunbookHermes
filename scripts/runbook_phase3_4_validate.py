from __future__ import annotations

from runbook_bootstrap import PROJECT_ROOT, bootstrap

bootstrap()
ROOT = PROJECT_ROOT

import json
import os
import sqlite3
import tempfile
import threading
from pathlib import Path


def _exists(path: str) -> bool:
    return (ROOT / path).exists()


def _reset_env() -> None:
    for key in list(os.environ):
        if key.startswith("RUNBOOK_") or key in {
            "ROLLBACK_BACKEND_KIND",
            "OBS_BACKEND",
            "TRACE_PROVIDER_KIND",
            "DEPLOY_BACKEND",
            "ACTION_EXECUTION_BACKEND",
            "ACTION_EXECUTION_ALLOWED_OPERATIONS",
        }:
            os.environ.pop(key, None)


def main() -> None:
    checks: dict[str, bool] = {}
    details: dict[str, object] = {}

    checks["phase3_files_present"] = all(
        _exists(path)
        for path in [
            "runbook_hermes/storage_schema.py",
            "runbook_hermes/store.py",
            "runbook_hermes/service_profiles.py",
            "data/runbook_profiles/services.json",
        ]
    )
    checks["phase4_files_present"] = all(
        _exists(path)
        for path in [
            "integrations/observability/base.py",
            "integrations/observability/prometheus_backend.py",
            "integrations/observability/loki_backend.py",
            "integrations/observability/trace_backend.py",
            "runbook_hermes/backends.py",
            "runbook_hermes/rca_guard.py",
            "runbook_hermes/action_policy.py",
        ]
    )

    from runbook_hermes.storage_schema import POSTGRES_DDL, POSTGRES_TABLES
    from runbook_hermes.store import JsonStore, SQLiteStore

    checks["postgres_typed_schema_declared"] = all(
        name in POSTGRES_DDL
        for name in ["incidents", "evidence", "hypotheses", "actions", "approvals", "checkpoints", "skills", "events", "kv"]
    ) and all(bucket in POSTGRES_TABLES for bucket in ["incidents", "evidence", "actions", "approvals"])
    details["postgres_tables"] = sorted(POSTGRES_TABLES.keys())

    with tempfile.TemporaryDirectory() as td:
        store = JsonStore(Path(td) / "json")

        def worker(idx: int) -> None:
            for j in range(40):
                store.append_event("inc_concurrent", "test.event", {"worker": idx, "n": j})

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        events = store.read("events").get("inc_concurrent", [])
        checks["json_store_concurrent_events_locked"] = len(events) == 320
        details["json_concurrent_event_count"] = len(events)

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "runbook.sqlite3"
        store = SQLiteStore(db_path)
        store.put("incidents", "inc_schema", {"service": "payment-service", "severity": "p1", "environment": "prod", "status": "open"})
        store.put("evidence", "ev_schema", {"incident_id": "inc_schema", "service": "payment-service", "source": "prometheus", "confidence": 0.91})
        store.put("actions", "act_schema", {"incident_id": "inc_schema", "action_type": "rollback_canary", "risk_level": "destructive", "requires_approval": True})
        store.put("approvals", "ap_schema", {"incident_id": "inc_schema", "service": "payment-service", "action": "rollback_canary", "status": "pending"})
        store.put("eval_runs", "run_schema", {"status": "ok"})
        store.append_event("inc_schema", "incident.created", {"status": "open"})
        con = sqlite3.connect(db_path)
        try:
            counts = {
                table: con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ["incidents", "evidence", "actions", "approvals", "events"]
            }
            kv_count = con.execute("SELECT COUNT(*) FROM kv_store WHERE bucket='eval_runs'").fetchone()[0]
        finally:
            con.close()
        checks["sqlite_backend_schema_tables"] = all(counts.get(table) == 1 for table in counts) and kv_count == 1
        details["sqlite_counts"] = counts | {"kv_eval_runs": kv_count}

    with tempfile.TemporaryDirectory() as td:
        _reset_env()
        os.environ["RUNBOOK_STORE_BACKEND"] = "sqlite"
        os.environ["RUNBOOK_STORE_DIR"] = td
        os.environ["RUNBOOK_STORE_SQLITE_PATH"] = str(Path(td) / "runbook_store.sqlite3")
        os.environ["RUNBOOK_MEMORY_ENABLED"] = "false"
        os.environ["RUNBOOK_RAG_ENABLED"] = "false"
        os.environ["RUNBOOK_MODEL_ENABLED"] = "false"
        os.environ["ROLLBACK_BACKEND_KIND"] = "mock"
        from runbook_hermes import incident_service as svc

        inc = svc.create_incident(
            "payment-service HTTP 503 spike after v2.3.1 release with MySQL connection pool exhaustion",
            source="phase3-4-validate",
        )
        hyp = inc.get("hypothesis") or {}
        action = inc.get("action") or {}
        graph = hyp.get("evidence_graph") or {}
        checks["sqlite_factory_incident_flow"] = bool(
            inc.get("incident_id") and inc.get("service_profile") and hyp.get("category") == "deploy_db_regression"
        )
        checks["evidence_graph_rca_present"] = bool(graph.get("nodes") and graph.get("edges") and hyp.get("rca_policy_rule"))
        checks["service_profile_action_plan"] = (
            action.get("action_type") == "rollback_canary" and action.get("args", {}).get("target_revision") == "v2.3.0"
        )
        details["incident_category"] = hyp.get("category")
        details["planned_action"] = {"type": action.get("action_type"), "target": action.get("args", {}).get("target_revision")}

    with tempfile.TemporaryDirectory() as td:
        _reset_env()
        os.environ["RUNBOOK_STORE_DIR"] = td
        os.environ["ROLLBACK_BACKEND_KIND"] = "kubernetes"
        os.environ["RUNBOOK_K8S_NAMESPACE"] = "payments"
        os.environ["RUNBOOK_K8S_ROLLBACK_MODE"] = "deployment_image"
        os.environ["RUNBOOK_K8S_IMAGE_REPOSITORY"] = "registry.example.com/payments/payment-service"
        from runbook_hermes.config import load_settings
        from runbook_hermes.backends import DeployBackend

        kube = DeployBackend(load_settings()).rollback_canary("payment-service", "v2.3.0", dry_run=True, checkpoint_id="ck_validate")
        checks["kubernetes_rollback_dry_run_command"] = (
            kube.get("status") == "dry_run_succeeded" and kube.get("command", [None])[0] == "kubectl" and "set" in kube.get("command", [])
        )
        details["kubernetes_command"] = kube.get("command")

        _reset_env()
        os.environ["RUNBOOK_STORE_DIR"] = td
        os.environ["ROLLBACK_BACKEND_KIND"] = "argocd"
        os.environ["RUNBOOK_ARGOCD_APP"] = "payment-service-prod"
        argo = DeployBackend(load_settings()).rollback_canary("payment-service", "v2.3.0", dry_run=True, checkpoint_id="ck_validate")
        checks["argocd_rollback_dry_run_command"] = (
            argo.get("status") == "dry_run_succeeded" and argo.get("command", [])[:3] == ["argocd", "app", "rollback"]
        )
        details["argocd_command"] = argo.get("command")

    ok = all(checks.values())
    report = {"ok": ok, "scope": "runbook-phase3-phase4", "checks": checks, "details": details}
    out = ROOT / ".artifacts"
    out.mkdir(exist_ok=True)
    (out / "runbook_phase3_4_validation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
