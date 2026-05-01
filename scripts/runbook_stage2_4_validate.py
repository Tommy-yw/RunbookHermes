from __future__ import annotations

import importlib
import json
from pathlib import Path

REQUIRED = [
    "apps/runbook_api/app/main.py",
    "web/static/incidents.html",
    "web/static/incident.html",
    "web/static/approvals.html",
    "web/static/digests.html",
    "runbook_hermes/incident_service.py",
    "runbook_hermes/model_client.py",
    "runbook_hermes/gateway/wecom.py",
    ".env.runbook.example",
    "docs/runbook-hermes/stage2-4-plan.md",
]

REQUIRED_IMPORTS = [
    "runbook_hermes.incident_service",
    "runbook_hermes.model_client",
    "runbook_hermes.gateway.wecom",
]

OPTIONAL_IMPORTS = [
    "apps.runbook_api.app.main",  # requires fastapi from the optional [web] extra
]


def main():
    missing = [p for p in REQUIRED if not Path(p).exists()]
    imports = {}
    for mod in REQUIRED_IMPORTS:
        try:
            importlib.import_module(mod)
            imports[mod] = True
        except Exception as exc:
            imports[mod] = str(exc)

    optional_imports = {}
    for mod in OPTIONAL_IMPORTS:
        try:
            importlib.import_module(mod)
            optional_imports[mod] = True
        except ModuleNotFoundError as exc:
            if exc.name == "fastapi":
                optional_imports[mod] = "optional_dependency_missing: install hermes-agent[web] or fastapi+uvicorn"
            else:
                optional_imports[mod] = str(exc)
        except Exception as exc:
            optional_imports[mod] = str(exc)

    ok = not missing and all(v is True for v in imports.values())
    result = {"ok": ok, "missing": missing, "imports": imports, "optional_imports": optional_imports}
    Path(".artifacts").mkdir(exist_ok=True)
    Path(".artifacts/runbook_stage2_4_validation_report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
