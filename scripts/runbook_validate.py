from __future__ import annotations

import importlib.util, json
from pathlib import Path

from runbook_hermes.smoke import run_smoke
from plugins.memory import load_memory_provider
from plugins.context_engine import load_context_engine

ROOT = Path(__file__).resolve().parents[1]

class Ctx:
    def __init__(self):
        self.tools = []
        self.skills = []
    def register_tool(self, name, toolset, schema, handler, **kwargs):
        self.tools.append(name)
    def register_skill(self, name, path, description=""):
        self.skills.append(name)


def load_runbook_plugin():
    path = ROOT / "plugins" / "runbook-hermes" / "__init__.py"
    spec = importlib.util.spec_from_file_location("runbook_plugin", path, submodule_search_locations=[str(path.parent)])
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ctx = Ctx()
    mod.register(ctx)
    return ctx


def main():
    checks = {}
    checks["baseline"] = (ROOT / "HERMES_BASELINE.lock").exists()
    checks["profile"] = (ROOT / "profiles" / "runbook-hermes" / "config.yaml").exists()
    checks["soul"] = (ROOT / "profiles" / "runbook-hermes" / "SOUL.md").exists()
    ctx = load_runbook_plugin()
    checks["plugin_tools"] = set(["prom_query","prom_top_anomalies","loki_query","trace_search","recent_deploys","rollback_canary"]).issubset(set(ctx.tools))
    checks["plugin_skill"] = "payment-503-spike" in ctx.skills
    mp = load_memory_provider("incident_memory")
    checks["memory_provider"] = mp is not None and mp.name == "incident_memory" and mp.is_available()
    ce = load_context_engine("evidence_stack")
    checks["context_engine"] = ce is not None and ce.name == "evidence_stack"
    smoke = run_smoke()
    checks["smoke"] = smoke.get("ok") is True and smoke.get("approval_gate", {}).get("status") == "approval_required"
    ok = all(checks.values())
    result = {"ok": ok, "checks": checks, "smoke_summary": {"evidence_count": smoke.get("evidence_count"), "category": smoke.get("hypothesis", {}).get("category"), "execution": smoke.get("execution", {}).get("status")}}
    out = ROOT / ".artifacts"
    out.mkdir(exist_ok=True)
    (out / "runbook_validation_report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if ok else 1)

if __name__ == "__main__":
    main()
