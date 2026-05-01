from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from runbook_hermes import incident_service as svc
from runbook_hermes import monitoring
from runbook_hermes.events import record_event
from runbook_hermes.gateway.alertmanager import normalize as normalize_alertmanager
from runbook_hermes.gateway.feishu import normalize_card_callback as normalize_feishu_card, normalize_event as normalize_feishu_event
from runbook_hermes.gateway.wecom import normalize_card_callback as normalize_wecom_card, normalize_event as normalize_wecom_event

app = FastAPI(
    title="RunbookHermes API",
    version="1.0.0",
    description="Hermes-native RunbookHermes web/API layer for incident response, approval, observability and runbook skill workflows.",
)

STATIC_DIR = Path(__file__).resolve().parents[3] / "web" / "static"
if STATIC_DIR.exists():
    app.mount("/web", StaticFiles(directory=str(STATIC_DIR), html=True), name="web")


class CreateIncidentRequest(BaseModel):
    summary: str = "payment-service HTTP 503 spike after release"
    service: str = "payment-service"
    severity: str = "p1"
    environment: str = "prod"
    source: str = "web"
    alert_name: str | None = None


class ApprovalDecisionRequest(BaseModel):
    decision: str
    approver: str = "operator"
    comment: str = ""


class ReplayRequest(BaseModel):
    incident_id: str


@app.get("/")
def home() -> RedirectResponse:
    return RedirectResponse("/web/index.html")


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "ok", "service": "runbook-hermes-api", "version": "1.0.0"}


@app.get("/runtime/status")
def runtime_status() -> Dict[str, Any]:
    return svc.runtime_status()


@app.get("/integrations/status")
def integrations_status() -> Dict[str, Any]:
    return svc.runtime_status()


@app.get("/dashboard/summary")
def dashboard_summary() -> Dict[str, Any]:
    return svc.dashboard_summary()


@app.get("/monitoring/live")
def monitoring_live() -> Dict[str, Any]:
    return monitoring.live_overview()


@app.get("/monitoring/services/{service}")
def monitoring_service(service: str) -> Dict[str, Any]:
    return monitoring.service_snapshot(service)


@app.get("/demo/scenarios")
def list_demo_scenarios() -> list[Dict[str, Any]]:
    return svc.list_scenarios()


@app.post("/demo/scenarios/{scenario_id}/incident")
def create_demo_scenario_incident(scenario_id: str) -> Dict[str, Any]:
    result = svc.create_incident_from_scenario(scenario_id, source="demo-scenario")
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=f"scenario not found: {scenario_id}")
    return result


@app.get("/incidents")
def list_incidents() -> list[Dict[str, Any]]:
    return svc.list_incidents()


@app.post("/incidents")
def create_incident(req: CreateIncidentRequest) -> Dict[str, Any]:
    return svc.create_incident(req.summary, req.service, req.severity, req.environment, req.source, req.alert_name)


@app.get("/incidents/{incident_id}")
def get_incident(incident_id: str) -> Dict[str, Any]:
    incident = svc.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="incident not found")
    return incident


@app.get("/incidents/{incident_id}/events")
def get_incident_events(incident_id: str) -> list[Dict[str, Any]]:
    return svc.get_events(incident_id)


@app.get("/approvals")
def list_approvals() -> list[Dict[str, Any]]:
    return svc.list_approvals()


@app.post("/approvals/{approval_id}/decision")
def decide_approval(approval_id: str, req: ApprovalDecisionRequest) -> Dict[str, Any]:
    return svc.decide(approval_id, req.decision, req.approver, req.comment)


@app.get("/incidents/{incident_id}/checkpoints")
def list_checkpoints(incident_id: str) -> list[Dict[str, Any]]:
    return svc.list_checkpoints(incident_id)


@app.post("/incidents/{incident_id}/rollback/restore-last")
def restore_last_checkpoint(incident_id: str) -> Dict[str, Any]:
    return svc.restore_last_checkpoint(incident_id)


@app.post("/replay")
def replay(req: ReplayRequest) -> Dict[str, Any]:
    return svc.replay(req.incident_id)


@app.get("/skills")
def list_skills() -> list[Dict[str, Any]]:
    return svc.list_skills()


@app.get("/skills/{skill_id}/download")
def download_skill(skill_id: str) -> PlainTextResponse:
    skill = svc.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="skill not found")
    return PlainTextResponse(skill.get("body", ""), media_type="text/markdown")


@app.post("/cron/daily_health_digest")
def daily_health_digest() -> Dict[str, Any]:
    return svc.daily_digest()


@app.post("/cron/weekly_top_incidents")
def weekly_top_incidents() -> Dict[str, Any]:
    return svc.weekly_digest()


@app.post("/gateway/alertmanager")
def alertmanager_webhook(payload: Dict[str, Any]) -> Dict[str, Any]:
    cmd = normalize_alertmanager(payload)
    incident = svc.create_incident(cmd.summary, cmd.service, cmd.severity, cmd.environment, "alertmanager", cmd.alert_name)
    if incident.get("incident_id"):
        record_event(incident["incident_id"], "gateway.alertmanager.received", cmd.to_dict())
    return {"status": "ok", "command": cmd.to_dict(), "incident": incident}


@app.post("/gateway/feishu/events")
@app.post("/gateway/feishu/webhook")
def feishu_events(payload: Dict[str, Any]) -> Dict[str, Any]:
    cmd = normalize_feishu_event(payload)
    if cmd.event_type == "view_root_cause":
        incident_id = payload.get("incident_id") or (payload.get("event") or {}).get("incident_id")
        if incident_id:
            record_event(incident_id, "gateway.feishu.received", cmd.to_dict())
        return {"status": "ok", "command": cmd.to_dict(), "incident": svc.get_incident(incident_id) if incident_id else {}}
    if cmd.event_type == "approve_or_reject_action":
        incident_id = svc.find_incident_id_for_approval(cmd.approval_id)
        if incident_id:
            record_event(incident_id, "gateway.feishu.received", cmd.to_dict())
        return {"status": "ok", "command": cmd.to_dict(), "approval": svc.decide(cmd.approval_id or "", cmd.decision or "rejected", cmd.user_name or "feishu")}
    incident = svc.create_incident(cmd.summary, cmd.service, cmd.severity, cmd.environment, "feishu", cmd.alert_name)
    if incident.get("incident_id"):
        record_event(incident["incident_id"], "gateway.feishu.received", cmd.to_dict())
    return {"status": "ok", "command": cmd.to_dict(), "incident": incident}


@app.post("/gateway/feishu/card-callback")
def feishu_card_callback(payload: Dict[str, Any]) -> Dict[str, Any]:
    cmd = normalize_feishu_card(payload)
    incident_id = svc.find_incident_id_for_approval(cmd.approval_id)
    if incident_id:
        record_event(incident_id, "gateway.feishu.card_callback", cmd.to_dict())
    result = svc.decide(cmd.approval_id or "", cmd.decision or "rejected", cmd.user_name or "feishu")
    return {"status": "ok", "command": cmd.to_dict(), "approval": result}


@app.post("/gateway/wecom/events")
@app.post("/gateway/wecom/webhook")
def wecom_events(payload: Dict[str, Any]) -> Dict[str, Any]:
    cmd = normalize_wecom_event(payload)
    if cmd.event_type == "approve_or_reject_action":
        incident_id = svc.find_incident_id_for_approval(cmd.approval_id)
        if incident_id:
            record_event(incident_id, "gateway.wecom.received", cmd.to_dict())
        return {"status": "ok", "command": cmd.to_dict(), "approval": svc.decide(cmd.approval_id or "", cmd.decision or "rejected", cmd.user_name or "wecom")}
    incident = svc.create_incident(cmd.summary, cmd.service, cmd.severity, cmd.environment, "wecom", cmd.alert_name)
    if incident.get("incident_id"):
        record_event(incident["incident_id"], "gateway.wecom.received", cmd.to_dict())
    return {"status": "ok", "command": cmd.to_dict(), "incident": incident}


@app.post("/gateway/wecom/card-callback")
def wecom_card_callback(payload: Dict[str, Any]) -> Dict[str, Any]:
    cmd = normalize_wecom_card(payload)
    incident_id = svc.find_incident_id_for_approval(cmd.approval_id)
    if incident_id:
        record_event(incident_id, "gateway.wecom.card_callback", cmd.to_dict())
    result = svc.decide(cmd.approval_id or "", cmd.decision or "rejected", cmd.user_name or "wecom")
    return {"status": "ok", "command": cmd.to_dict(), "approval": result}


@app.post("/incidents/{incident_id}/verify-recovery")
def verify_recovery_endpoint(incident_id: str) -> Dict[str, Any]:
    from runbook_hermes.tools import verify_recovery

    incident = svc.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="incident not found")
    return __import__("json").loads(verify_recovery({"service": incident.get("service", "payment-service"), "window": "2m"}))


@app.get("/incidents/{incident_id}/model-summary")
def model_summary(incident_id: str) -> Dict[str, Any]:
    return svc.model_summary(incident_id)
