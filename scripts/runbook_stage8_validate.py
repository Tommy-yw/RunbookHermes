from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _exists(path: str) -> bool:
    return (ROOT / path).exists()


def main() -> None:
    checks = {
        "web_pages": all(
            _exists(p)
            for p in [
                "web/static/index.html",
                "web/static/incidents.html",
                "web/static/incident.html",
                "web/static/approvals.html",
                "web/static/digests.html",
                "web/static/settings.html",
                "web/static/monitoring.html",
                "web/static/styles.css",
                "web/static/app.js",
            ]
        ),
        "api_app": _exists("apps/runbook_api/app/main.py"),
        "execution_shell": _exists("runbook_hermes/execution.py"),
        "payment_demo": _exists("demo/payment_system/docker-compose.yml"),
        "final_docs": _exists("docs/runbook-hermes/stage8-final-web-product.md")
        and _exists("docs/runbook-hermes/final-interface-map.md"),
    }

    with tempfile.TemporaryDirectory() as td:
        os.environ["RUNBOOK_STORE_DIR"] = td
        os.environ.setdefault("RUNBOOK_MODEL_ENABLED", "false")
        from runbook_hermes import incident_service as svc

        inc = svc.create_incident_from_scenario("payment_503_spike", source="stage8-validate")
        dashboard = svc.dashboard_summary()
        runtime = svc.runtime_status()
        checks["incident_service"] = bool(inc.get("incident_id") and dashboard.get("totals", {}).get("incidents", 0) >= 1)
        checks["runtime_status"] = runtime.get("status") == "ok" and "observability" in runtime and "execution" in runtime

        try:
            from fastapi.testclient import TestClient
            from apps.runbook_api.app.main import app

            client = TestClient(app)
            checks["api_health"] = client.get("/health").status_code == 200
            checks["api_dashboard"] = client.get("/dashboard/summary").status_code == 200
            checks["api_runtime"] = client.get("/runtime/status").status_code == 200
            checks["api_scenarios"] = client.get("/demo/scenarios").status_code == 200
            checks["api_monitoring_live"] = client.get("/monitoring/live").status_code == 200
            checks["api_monitoring_page"] = client.get("/web/monitoring.html").status_code == 200
            checks["api_web_static"] = client.get("/web/incidents.html").status_code == 200
            created = client.post("/demo/scenarios/coupon_504_timeout/incident").json()
            checks["api_create_scenario"] = bool(created.get("incident_id"))
        except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
            if exc.name == "fastapi":
                checks["api_optional_dependency"] = "fastapi_missing_install_hermes_agent_web_extra"
                checks["api_health"] = "skipped"
                checks["api_dashboard"] = "skipped"
                checks["api_runtime"] = "skipped"
                checks["api_scenarios"] = "skipped"
                checks["api_web_static"] = "skipped"
                checks["api_create_scenario"] = "skipped"
                checks["api_monitoring_live"] = "skipped"
                checks["api_monitoring_page"] = "skipped"
            else:
                checks["api_import_error"] = str(exc)
                checks["api_health"] = False
                checks["api_dashboard"] = False
                checks["api_runtime"] = False
                checks["api_scenarios"] = False
                checks["api_web_static"] = False
                checks["api_create_scenario"] = False
                checks["api_monitoring_live"] = False
                checks["api_monitoring_page"] = False
        except Exception as exc:  # pragma: no cover - dependency/environment dependent
            checks["api_import_error"] = str(exc)
            checks["api_health"] = False
            checks["api_dashboard"] = False
            checks["api_runtime"] = False
            checks["api_scenarios"] = False
            checks["api_web_static"] = False
            checks["api_create_scenario"] = False
            checks["api_monitoring_live"] = False
            checks["api_monitoring_page"] = False

    ok = all(v is True or v == "skipped" or (isinstance(v, str) and v.startswith("fastapi_missing")) for k, v in checks.items() if not k.endswith("_error"))
    report = {"ok": ok, "scope": "stage8-final-web-product", "checks": checks}
    out = ROOT / ".artifacts" / "stage8_validation_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
