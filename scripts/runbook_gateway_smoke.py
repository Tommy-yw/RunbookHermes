from __future__ import annotations

import argparse, json
from runbook_hermes.gateway.server import main as gateway_main
from runbook_hermes.gateway.alertmanager import normalize as alert
from runbook_hermes.gateway.feishu import normalize_card_callback, normalize_event
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def load(name):
    return json.loads((ROOT / "data" / "runbook_samples" / name).read_text())

def run_all():
    a = alert(load("alertmanager_payment_503.json"))
    f = normalize_event(load("feishu_event_create_incident.json"))
    c = normalize_card_callback(load("feishu_card_approval.json"))
    return {"ok": True, "alertmanager": a.to_dict(), "feishu_create": f.to_dict(), "feishu_approval": c.to_dict()}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run_all(), ensure_ascii=False, indent=2))
