from __future__ import annotations

import json

from runbook_hermes import incident_service as svc
from runbook_hermes.gateway.alertmanager import normalize as normalize_alertmanager
from runbook_hermes.gateway.feishu import normalize_event as normalize_feishu
from runbook_hermes.gateway.wecom import normalize_event as normalize_wecom


def main():
    incident = svc.create_incident("payment-service HTTP 503 spike after release", "payment-service", "p1", "prod", "smoke")
    assert incident.get("incident_id")
    assert incident.get("status") in {"approval_pending", "completed"}
    approvals = svc.list_approvals()
    assert approvals, "expected approval gate for rollback"
    approved = svc.decide(approvals[0]["approval_id"], "approved", "smoke")
    assert approved.get("status") == "approved"
    assert svc.get_events(incident["incident_id"])
    assert svc.daily_digest()["status"] == "ok"
    assert svc.weekly_digest()["status"] == "ok"
    assert svc.replay(incident["incident_id"])["status"] == "replayed"

    alert_cmd = normalize_alertmanager({
        "commonLabels": {"service": "payment-service", "severity": "p1", "environment": "prod", "alert_name": "payment_503_spike"},
        "commonAnnotations": {"summary": "payment-service HTTP 503 spike after release"},
        "alerts": [{"startsAt": "2026-04-26T10:00:00Z", "generatorURL": "https://prom.example/graph"}],
    })
    assert alert_cmd.source == "alertmanager"

    feishu_cmd = normalize_feishu({"event": {"event_type": "create_incident", "service": "payment-service", "summary": "payment-service HTTP 503"}})
    assert feishu_cmd.source == "feishu"

    wecom_cmd = normalize_wecom({"service": "payment-service", "summary": "payment-service HTTP 503"})
    assert wecom_cmd.source == "wecom"

    print(json.dumps({"ok": True, "incident_id": incident["incident_id"], "approval_id": approvals[0]["approval_id"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
