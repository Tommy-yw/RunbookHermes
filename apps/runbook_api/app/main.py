from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from runbook_hermes import incident_service as svc
from runbook_hermes.api_auth import auth_status as runbook_api_auth_status, require_runbook_api_auth
from runbook_hermes.resources import resource_path
from runbook_hermes import monitoring
from runbook_hermes.events import record_event
from runbook_hermes.gateway.alertmanager import normalize as normalize_alertmanager
from runbook_hermes.gateway.feishu import normalize_card_callback as normalize_feishu_card, normalize_event as normalize_feishu_event, verify_token as verify_feishu_token
from runbook_hermes.gateway.wecom import normalize_card_callback as normalize_wecom_card, normalize_event as normalize_wecom_event
from runbook_hermes.webhook_security import WebhookSecurityError, prepare_feishu_payload, prepare_wecom_payload

app = FastAPI(
    title="RunbookHermes API",
    version="1.0.0",
    description="Hermes-native RunbookHermes web/API layer for incident response, approval, observability, RAG, evaluation and runbook skill workflows.",
    dependencies=[Depends(require_runbook_api_auth)],
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

STATIC_DIR = resource_path("web", "static")
if STATIC_DIR.exists():
    app.mount("/web", StaticFiles(directory=str(STATIC_DIR), html=True), name="web")


def _model_dump(model: BaseModel) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()  # type: ignore[attr-defined]
    return model.dict()


class VisualReferenceRequest(BaseModel):
    kind: str = "dashboard_image"
    image_path: str = ""
    image_url: str = ""
    text_hint: str = ""
    payload: Dict[str, Any] = Field(default_factory=dict)
    source: str = "api"


class CreateIncidentRequest(BaseModel):
    summary: str = "payment-service HTTP 503 spike after release"
    service: str = "payment-service"
    severity: str = "p1"
    environment: str = "prod"
    source: str = "web"
    alert_name: str | None = None
    visual_refs: list[VisualReferenceRequest] = Field(default_factory=list)


class ApprovalDecisionRequest(BaseModel):
    decision: str
    approver: str = "operator"
    comment: str = ""
    confirm_execution: bool = False
    confirmation_token: str = ""
    second_confirmation: str = ""


class ReplayRequest(BaseModel):
    incident_id: str


class MemoryWriteRequest(BaseModel):
    kind: str = "manual_note"
    title: str
    body: str
    service: str = ""
    tags: list[str] = Field(default_factory=list)
    source: str = "api"
    incident_id: str = ""
    notebook: str | None = None


class MemoryFeedbackRequest(BaseModel):
    label: str = "helpful"
    comment: str = ""
    weight: float | None = None


class MemoryRouteRequest(BaseModel):
    message: str
    source: str = "api"
    metadata: Dict[str, Any] = Field(default_factory=dict)
    apply: bool = True


class SkillPublishRequest(BaseModel):
    skill_id: str = ""
    incident_id: str = ""
    service: str = ""
    title: str = ""
    body: str = ""


class RagIngestTextRequest(BaseModel):
    title: str
    body: str
    source: str = "api"
    service: str = ""
    tags: list[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    acl_tags: list[str] = Field(default_factory=list)
    permission_scope: str = "public"
    expires_at: float | None = None


class RagIngestPathRequest(BaseModel):
    path: str
    service: str = ""
    tags: list[str] = Field(default_factory=list)
    recursive: bool = True
    acl_tags: list[str] = Field(default_factory=list)
    permission_scope: str = "public"


class RagEvaluateRequest(BaseModel):
    queries: list[Dict[str, Any]] = Field(default_factory=list)
    service: str = ""
    limit: int = 5
    permission_scope: str = ""
    acl: list[str] = Field(default_factory=list)


class MultimodalAnalyzeRequest(BaseModel):
    service: str = "payment-service"
    summary: str = ""
    visual_refs: list[VisualReferenceRequest] = Field(default_factory=list)
    include_dashboard_snapshot: bool | None = None


class EvalRunRequest(BaseModel):
    case_ids: list[str] = Field(default_factory=list)
    persist: bool | None = None
    model_assist: bool | None = None


class EvalPostmortemRequest(BaseModel):
    case_id: str = ""
    incident_id: str = ""
    final_score: float
    reviewer: str = "operator"
    notes: str = ""
    labels: list[str] = Field(default_factory=list)


class TrainingBuildRequest(BaseModel):
    include_incidents: bool = True
    include_benchmark_cases: bool = True
    max_incidents: int | None = None
    min_reward: float | None = None


class TrainingCompressRequest(BaseModel):
    run_id: str = ""
    max_message_chars: int | None = None
    use_hermes_compressor: bool = False


class TrainingExportRequest(BaseModel):
    run_id: str = ""
    base_model: str = ""
    output_model_name: str = ""


class TrainingPipelineRequest(BaseModel):
    include_incidents: bool = True
    include_benchmark_cases: bool = True
    max_incidents: int | None = None
    min_reward: float | None = None
    base_model: str = ""
    output_model_name: str = ""
    use_hermes_compressor: bool = False
    dry_run: bool = True


class TrainingExternalLaunchRequest(BaseModel):
    run_id: str = ""
    confirmation_token: str = ""


@app.get("/")
def home() -> RedirectResponse:
    return RedirectResponse("/web/index.html")


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "ok", "service": "runbook-hermes-api", "version": "1.0.0"}


@app.get("/auth/status")
def auth_status() -> Dict[str, Any]:
    return {"status": "ok", "auth": runbook_api_auth_status()}


@app.get("/runtime/status")
def runtime_status() -> Dict[str, Any]:
    return svc.runtime_status()


@app.get("/integrations/status")
def integrations_status() -> Dict[str, Any]:
    return svc.runtime_status()


@app.get("/dashboard/summary")
def dashboard_summary() -> Dict[str, Any]:
    return svc.dashboard_summary()


@app.get("/memory/status")
def memory_status() -> Dict[str, Any]:
    return svc.memory_status()


@app.get("/memory/bridge/status")
def memory_bridge_status() -> Dict[str, Any]:
    return svc.memory_bridge_status()


@app.post("/memory/route")
def memory_route(req: MemoryRouteRequest) -> Dict[str, Any]:
    return svc.route_memory_message(req.message, source=req.source, metadata=req.metadata, apply=req.apply)


@app.get("/memory/search")
def memory_search(query: str = "", service: str = "", limit: int = 8, include_body: bool = False) -> Dict[str, Any]:
    return svc.search_memory(query, service=service, limit=limit, include_body=include_body)


@app.post("/memory")
def memory_write(req: MemoryWriteRequest) -> Dict[str, Any]:
    return svc.write_memory(req.kind, req.title, req.body, service=req.service, tags=req.tags, source=req.source, incident_id=req.incident_id, notebook=req.notebook)


@app.get("/memory/notebooks")
def memory_notebooks() -> Dict[str, Any]:
    return svc.memory_notebooks()


@app.post("/memory/reindex-skills")
def memory_reindex_skills() -> Dict[str, Any]:
    return svc.memory_reindex_skills()


@app.get("/memory/evolution/digest")
def memory_evolution_digest(limit: int = 8) -> Dict[str, Any]:
    return svc.memory_evolution_digest(limit=limit)


@app.post("/memory/{memory_id}/feedback")
def memory_feedback(memory_id: str, req: MemoryFeedbackRequest) -> Dict[str, Any]:
    return svc.memory_feedback(memory_id, req.label, comment=req.comment, weight=req.weight)


@app.get("/rag/status")
def rag_status() -> Dict[str, Any]:
    return svc.rag_status()


@app.get("/rag/documents")
def rag_documents(limit: int = 50) -> Dict[str, Any]:
    return svc.rag_documents(limit=limit)


@app.post("/rag/ingest-text")
def rag_ingest_text(req: RagIngestTextRequest) -> Dict[str, Any]:
    return svc.rag_ingest_text(
        req.title,
        req.body,
        source=req.source,
        service=req.service,
        tags=req.tags,
        metadata=req.metadata,
        acl_tags=req.acl_tags,
        permission_scope=req.permission_scope,
        expires_at=req.expires_at,
    )


@app.post("/rag/ingest-path")
def rag_ingest_path(req: RagIngestPathRequest) -> Dict[str, Any]:
    return svc.rag_ingest_path(req.path, service=req.service, tags=req.tags, recursive=req.recursive, acl_tags=req.acl_tags, permission_scope=req.permission_scope)


@app.get("/rag/search")
def rag_search(query: str = "", service: str = "", limit: int = 5, include_text: bool = False, permission_scope: str = "", acl: str = "") -> Dict[str, Any]:
    acl_items = [x.strip() for x in acl.split(",") if x.strip()] if acl else []
    return svc.rag_search(query, service=service, limit=limit, include_text=include_text, permission_scope=permission_scope, acl=acl_items)


@app.get("/rag/context")
def rag_context(query: str = "", service: str = "", limit: int = 5, permission_scope: str = "", acl: str = "") -> Dict[str, Any]:
    acl_items = [x.strip() for x in acl.split(",") if x.strip()] if acl else []
    return svc.rag_context(query, service=service, limit=limit, permission_scope=permission_scope, acl=acl_items)


@app.post("/rag/evaluate")
def rag_evaluate(req: RagEvaluateRequest) -> Dict[str, Any]:
    return svc.rag_evaluate(req.queries, service=req.service, limit=req.limit, permission_scope=req.permission_scope, acl=req.acl)


@app.post("/multimodal/analyze")
def multimodal_analyze(req: MultimodalAnalyzeRequest) -> Dict[str, Any]:
    return svc.multimodal_analyze(
        service=req.service,
        summary=req.summary,
        visual_refs=[_model_dump(ref) for ref in req.visual_refs],
        include_dashboard_snapshot=req.include_dashboard_snapshot,
    )


@app.get("/eval/benchmarks")
def eval_benchmarks() -> Dict[str, Any]:
    return svc.eval_cases()


@app.post("/eval/run")
def eval_run(req: EvalRunRequest) -> Dict[str, Any]:
    return svc.run_benchmark_eval(case_ids=req.case_ids, persist=req.persist, model_assist=req.model_assist)


@app.get("/eval/runs")
def eval_runs(limit: int = 10) -> Dict[str, Any]:
    return svc.latest_eval_runs(limit=limit)


@app.post("/eval/postmortem")
def eval_postmortem(req: EvalPostmortemRequest) -> Dict[str, Any]:
    return svc.save_eval_postmortem(case_id=req.case_id, incident_id=req.incident_id, final_score=req.final_score, reviewer=req.reviewer, notes=req.notes, labels=req.labels)


@app.get("/eval/postmortems")
def eval_postmortems(limit: int = 20) -> Dict[str, Any]:
    return svc.latest_eval_postmortems(limit=limit)


@app.get("/training/status")
def training_status() -> Dict[str, Any]:
    return svc.training_status()


@app.get("/training/runs")
def training_runs(limit: int = 10) -> Dict[str, Any]:
    return svc.training_runs(limit=limit)


@app.get("/training/datasets")
def training_datasets(limit: int = 20) -> Dict[str, Any]:
    return svc.training_datasets(limit=limit)


@app.post("/training/build-dataset")
def training_build_dataset(req: TrainingBuildRequest) -> Dict[str, Any]:
    return svc.training_build_dataset(
        include_incidents=req.include_incidents,
        include_benchmark_cases=req.include_benchmark_cases,
        max_incidents=req.max_incidents,
        min_reward=req.min_reward,
    )


@app.post("/training/compress")
def training_compress(req: TrainingCompressRequest) -> Dict[str, Any]:
    return svc.training_compress_dataset(
        run_id=req.run_id,
        max_message_chars=req.max_message_chars,
        use_hermes_compressor=req.use_hermes_compressor,
    )


@app.post("/training/export")
def training_export(req: TrainingExportRequest) -> Dict[str, Any]:
    return svc.training_export_dataset(run_id=req.run_id, base_model=req.base_model, output_model_name=req.output_model_name)


@app.post("/training/pipeline/run")
def training_pipeline_run(req: TrainingPipelineRequest) -> Dict[str, Any]:
    return svc.training_run_pipeline(
        include_incidents=req.include_incidents,
        include_benchmark_cases=req.include_benchmark_cases,
        max_incidents=req.max_incidents,
        min_reward=req.min_reward,
        base_model=req.base_model,
        output_model_name=req.output_model_name,
        use_hermes_compressor=req.use_hermes_compressor,
        dry_run=req.dry_run,
    )


@app.post("/training/external-launch")
def training_external_launch(req: TrainingExternalLaunchRequest) -> Dict[str, Any]:
    return svc.training_external_launch(run_id=req.run_id, confirmation_token=req.confirmation_token)


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
    return svc.create_incident(
        req.summary,
        req.service,
        req.severity,
        req.environment,
        req.source,
        req.alert_name,
        visual_refs=[_model_dump(ref) for ref in req.visual_refs],
    )


@app.get("/incidents/{incident_id}")
def get_incident(incident_id: str) -> Dict[str, Any]:
    incident = svc.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="incident not found")
    return incident


@app.get("/incidents/{incident_id}/events")
def get_incident_events(incident_id: str) -> list[Dict[str, Any]]:
    return svc.get_events(incident_id)


@app.get("/incidents/{incident_id}/memory-context")
def get_incident_memory_context(incident_id: str) -> Dict[str, Any]:
    result = svc.incident_memory_context(incident_id)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="incident not found")
    return result


@app.post("/incidents/{incident_id}/multimodal-evidence")
def attach_incident_multimodal_evidence(incident_id: str, req: MultimodalAnalyzeRequest) -> Dict[str, Any]:
    result = svc.attach_multimodal_evidence(
        incident_id,
        visual_refs=[_model_dump(ref) for ref in req.visual_refs],
        include_dashboard_snapshot=req.include_dashboard_snapshot,
    )
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="incident not found")
    return result


@app.get("/approvals")
def list_approvals() -> list[Dict[str, Any]]:
    return svc.list_approvals()


@app.post("/approvals/{approval_id}/decision")
def decide_approval(approval_id: str, req: ApprovalDecisionRequest) -> Dict[str, Any]:
    return svc.decide(
        approval_id,
        req.decision,
        req.approver,
        req.comment,
        execution_context={"confirm_execution": req.confirm_execution, "confirmation_token": req.confirmation_token or req.second_confirmation, "second_confirmation": req.second_confirmation},
    )


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


@app.get("/skills/publisher/status")
def skills_publisher_status() -> Dict[str, Any]:
    return svc.skill_publisher_status()


@app.post("/skills/publish")
def skills_publish(req: SkillPublishRequest) -> Dict[str, Any]:
    return svc.publish_skill(skill_id=req.skill_id, title=req.title, body=req.body, service=req.service, incident_id=req.incident_id)


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


def _feishu_payload_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=401, detail=f"Feishu webhook verification failed: {exc}")


def _wecom_payload_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=401, detail=f"WeCom webhook verification failed: {exc}")


@app.post("/gateway/feishu/events")
@app.post("/gateway/feishu/webhook")
async def feishu_events(request: Request) -> Dict[str, Any]:
    try:
        payload = prepare_feishu_payload(request.headers, await request.body())
    except WebhookSecurityError as exc:
        raise _feishu_payload_error(exc) from exc
    if payload.get("type") == "url_verification" and payload.get("challenge"):
        if not verify_feishu_token(payload):
            raise _feishu_payload_error(ValueError("Feishu verification token mismatch"))
        return {"challenge": payload.get("challenge")}
    try:
        cmd = normalize_feishu_event(payload)
    except ValueError as exc:
        raise _feishu_payload_error(exc) from exc
    if cmd.event_type == "view_root_cause":
        incident_id = payload.get("incident_id") or (payload.get("event") or {}).get("incident_id")
        if incident_id:
            record_event(incident_id, "gateway.feishu.received", cmd.to_dict())
        return {"status": "ok", "command": cmd.to_dict(), "incident": svc.get_incident(incident_id) if incident_id else {}}
    if cmd.event_type == "approve_or_reject_action":
        incident_id = svc.find_incident_id_for_approval(cmd.approval_id)
        if incident_id:
            record_event(incident_id, "gateway.feishu.received", cmd.to_dict())
        return {"status": "ok", "command": cmd.to_dict(), "approval": svc.decide(cmd.approval_id or "", cmd.decision or "rejected", cmd.user_name or "feishu", execution_context={"confirmation_token": cmd.second_confirmation or ""})}

    settings = svc.load_settings() if hasattr(svc, "load_settings") else None
    feishu_router_enabled = bool(getattr(settings, "runbook_feishu_memory_router_enabled", True)) if settings else True
    if feishu_router_enabled and cmd.summary:
        route = svc.route_memory_message(cmd.summary, source="feishu", metadata={"command": cmd.to_dict(), "payload": payload, "alert_name": cmd.alert_name}, apply=True)
        action = (route.get("route") or {}).get("action")
        if action != "create_incident":
            return {"status": "ok", "command": cmd.to_dict(), "memory_route": route}
        incident = route.get("incident") or {}
    else:
        incident = svc.create_incident(cmd.summary, cmd.service, cmd.severity, cmd.environment, "feishu", cmd.alert_name)
    if incident.get("incident_id"):
        record_event(incident["incident_id"], "gateway.feishu.received", cmd.to_dict())
    return {"status": "ok", "command": cmd.to_dict(), "incident": incident}


@app.post("/gateway/feishu/card-callback")
async def feishu_card_callback(request: Request) -> Dict[str, Any]:
    try:
        payload = prepare_feishu_payload(request.headers, await request.body())
    except WebhookSecurityError as exc:
        raise _feishu_payload_error(exc) from exc
    try:
        cmd = normalize_feishu_card(payload)
    except ValueError as exc:
        raise _feishu_payload_error(exc) from exc
    incident_id = svc.find_incident_id_for_approval(cmd.approval_id)
    if incident_id:
        record_event(incident_id, "gateway.feishu.card_callback", cmd.to_dict())
    result = svc.decide(cmd.approval_id or "", cmd.decision or "rejected", cmd.user_name or "feishu", execution_context={"confirmation_token": cmd.second_confirmation or ""})
    return {"status": "ok", "command": cmd.to_dict(), "approval": result}


@app.get("/gateway/wecom/events", response_class=PlainTextResponse)
@app.get("/gateway/wecom/webhook", response_class=PlainTextResponse)
async def wecom_url_verification(request: Request) -> PlainTextResponse:
    try:
        payload = prepare_wecom_payload(request.query_params, request.headers, await request.body())
    except WebhookSecurityError as exc:
        raise _wecom_payload_error(exc) from exc
    return PlainTextResponse(str(payload.get("echostr", "")))


@app.post("/gateway/wecom/events")
@app.post("/gateway/wecom/webhook")
async def wecom_events(request: Request) -> Dict[str, Any]:
    try:
        payload = prepare_wecom_payload(request.query_params, request.headers, await request.body())
    except WebhookSecurityError as exc:
        raise _wecom_payload_error(exc) from exc
    cmd = normalize_wecom_event(payload)
    if cmd.event_type == "approve_or_reject_action":
        incident_id = svc.find_incident_id_for_approval(cmd.approval_id)
        if incident_id:
            record_event(incident_id, "gateway.wecom.received", cmd.to_dict())
        return {"status": "ok", "command": cmd.to_dict(), "approval": svc.decide(cmd.approval_id or "", cmd.decision or "rejected", cmd.user_name or "wecom", execution_context={"confirmation_token": cmd.second_confirmation or ""})}
    incident = svc.create_incident(cmd.summary, cmd.service, cmd.severity, cmd.environment, "wecom", cmd.alert_name)
    if incident.get("incident_id"):
        record_event(incident["incident_id"], "gateway.wecom.received", cmd.to_dict())
    return {"status": "ok", "command": cmd.to_dict(), "incident": incident}


@app.post("/gateway/wecom/card-callback")
async def wecom_card_callback(request: Request) -> Dict[str, Any]:
    try:
        payload = prepare_wecom_payload(request.query_params, request.headers, await request.body())
    except WebhookSecurityError as exc:
        raise _wecom_payload_error(exc) from exc
    cmd = normalize_wecom_card(payload)
    incident_id = svc.find_incident_id_for_approval(cmd.approval_id)
    if incident_id:
        record_event(incident_id, "gateway.wecom.card_callback", cmd.to_dict())
    result = svc.decide(cmd.approval_id or "", cmd.decision or "rejected", cmd.user_name or "wecom", execution_context={"confirmation_token": cmd.second_confirmation or ""})
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
