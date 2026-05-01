from __future__ import annotations

import json, sys
from pathlib import Path
from .alertmanager import normalize as normalize_alertmanager
from .feishu import normalize_card_callback, normalize_event


def main(argv=None):
    argv = argv or sys.argv[1:]
    sample = argv[0] if argv else "alertmanager"
    root = Path(__file__).resolve().parents[2] / "data" / "runbook_samples"
    if sample == "alertmanager":
        payload = json.loads((root / "alertmanager_payment_503.json").read_text())
        cmd = normalize_alertmanager(payload)
    elif sample == "feishu-create":
        payload = json.loads((root / "feishu_event_create_incident.json").read_text())
        cmd = normalize_event(payload)
    else:
        payload = json.loads((root / "feishu_card_approval.json").read_text())
        cmd = normalize_card_callback(payload)
    print(json.dumps(cmd.to_dict(), ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
