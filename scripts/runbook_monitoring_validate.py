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
        "monitoring_page": _exists("web/static/monitoring.html"),
        "monitoring_module": _exists("runbook_hermes/monitoring.py"),
        "mock_coupon_metrics": _exists("data/runbook_mock/mock_metrics/coupon-service.json"),
        "mock_order_metrics": _exists("data/runbook_mock/mock_metrics/order-service.json"),
        "sidebar_updated": False,
        "overview_copy_updated": False,
    }
    app_js = (ROOT / "web/static/app.js").read_text(encoding="utf-8") if _exists("web/static/app.js") else ""
    index_html = (ROOT / "web/static/index.html").read_text(encoding="utf-8") if _exists("web/static/index.html") else ""
    checks["sidebar_updated"] = "Hermes-native Incident Agent" not in app_js and "Monitoring" in app_js
    checks["overview_copy_updated"] = "Hermes-native runbook agent" not in index_html and "AIOps 控制台" in index_html

    with tempfile.TemporaryDirectory() as td:
        os.environ["RUNBOOK_STORE_DIR"] = td
        os.environ.setdefault("RUNBOOK_MODEL_ENABLED", "false")
        from runbook_hermes import monitoring

        live = monitoring.live_overview()
        checks["monitoring_live"] = live.get("status") == "ok" and len(live.get("services", [])) >= 3
        checks["monitoring_services_have_series"] = all(s.get("series") for s in live.get("services", []))
        checks["monitoring_has_topology"] = bool(live.get("topology", {}).get("nodes"))

        try:
            from fastapi.testclient import TestClient
            from apps.runbook_api.app.main import app

            client = TestClient(app)
            checks["api_monitoring_live"] = client.get("/monitoring/live").status_code == 200
            checks["api_monitoring_service"] = client.get("/monitoring/services/payment-service").status_code == 200
            checks["api_monitoring_page"] = client.get("/web/monitoring.html").status_code == 200
        except ModuleNotFoundError as exc:
            if exc.name == "fastapi":
                checks["api_optional_dependency"] = "fastapi_missing_install_web_extra"
                checks["api_monitoring_live"] = "skipped"
                checks["api_monitoring_service"] = "skipped"
                checks["api_monitoring_page"] = "skipped"
            else:
                checks["api_import_error"] = str(exc)
                checks["api_monitoring_live"] = False
                checks["api_monitoring_service"] = False
                checks["api_monitoring_page"] = False
        except Exception as exc:
            checks["api_import_error"] = str(exc)
            checks["api_monitoring_live"] = False
            checks["api_monitoring_service"] = False
            checks["api_monitoring_page"] = False

    ok = all(v is True or v == "skipped" or (isinstance(v, str) and v.startswith("fastapi_missing")) for k, v in checks.items() if not k.endswith("_error"))
    report = {"ok": ok, "scope": "web-monitoring-final", "checks": checks}
    out = ROOT / ".artifacts" / "runbook_monitoring_validation_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
