from __future__ import annotations

from runbook_bootstrap import PROJECT_ROOT, bootstrap
bootstrap()
ROOT = PROJECT_ROOT

import sys
from pathlib import Path


import json
from pathlib import Path

ROOT = PROJECT_ROOT
FORBIDDEN = ["legacy_runbook", "IncidentOrchestrator.create_and_run"]
SKIP = {"legacy_runbook"}

def main():
    hits = []
    for path in [ROOT / "runbook_hermes", ROOT / "plugins" / "runbook-hermes", ROOT / "plugins" / "memory" / "incident_memory", ROOT / "plugins" / "context_engine" / "evidence_stack"]:
        if not path.exists():
            continue
        for file in path.rglob("*.py"):
            text = file.read_text(encoding="utf-8", errors="ignore")
            for token in FORBIDDEN:
                if token in text:
                    hits.append({"file": str(file.relative_to(ROOT)), "token": token})
    result = {"ok": not hits, "legacy_imports_found": hits}
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if not hits else 1)

if __name__ == "__main__":
    main()
