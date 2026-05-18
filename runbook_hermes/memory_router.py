from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .config import load_settings
from .memory_kinds import (
    FAULT_PATTERN,
    MANUAL_NOTE,
    SERVICE_GOVERNANCE,
    SERVICE_PROFILE,
    SKILL_INDEX,
    TEAM_PREFERENCE,
    notebook_for_kind,
)


SERVICE_RE = re.compile(r"\b([a-z][a-z0-9-]{1,60}-service)\b", re.I)
KNOWN_SERVICES = ("payment-service", "coupon-service", "order-service")
INCIDENT_TERMS = (
    "告警",
    "故障",
    "异常",
    "排障",
    "报警",
    "宕机",
    "超时",
    "错误率",
    "p1",
    "p2",
    "sev1",
    "sev2",
    "incident",
    "alert",
    "outage",
    "error",
    "failure",
    "timeout",
    "503",
    "504",
    "429",
    "spike",
)
REMEMBER_TERMS = ("记住", "请记住", "以后", "规则", "规范", "SOP", "runbook习惯", "团队习惯", "沉淀")
GOVERNANCE_TERMS = ("必须", "禁止", "不要", "不能", "审批", "二人", "双人", "高峰期", "回滚", "降级", "限流", "通知", "变更", "发布", "policy", "must", "never", "approval")
RECALL_TERMS = ("查一下", "查询", "搜索", "召回", "以前", "之前", "历史", "类似", "怎么处理", "怎么排", "recall", "search", "history")
SKILL_TERMS = ("保存成runbook", "保存成 runbook", "沉淀成runbook", "沉淀成 runbook", "保存成skill", "保存成 skill", "publish skill")
USER_PREF_TERMS = ("我喜欢", "我的偏好", "回答风格", "称呼我", "用中文", "详细解释", "简洁回答")


@dataclass
class RouteDecision:
    action: str
    target_plane: str
    message: str
    source: str = "chat"
    service: str = ""
    severity: str = "p2"
    environment: str = "prod"
    title: str = ""
    body: str = ""
    memory_kind: str = ""
    notebook: str = ""
    tags: List[str] = field(default_factory=list)
    confidence: float = 0.5
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _lower(text: str) -> str:
    return (text or "").strip().lower()


def extract_text_from_payload(payload: Dict[str, Any]) -> str:
    """Best-effort extraction for Feishu/Lark event payloads.

    Real Feishu events may carry `event.message.content` as a JSON string, while
    mock/demo events often use `event.summary` directly. This helper keeps the
    router independent from the gateway implementation.
    """
    if not isinstance(payload, dict):
        return str(payload or "")
    event = payload.get("event") if isinstance(payload.get("event"), dict) else payload
    candidates: List[Any] = [
        event.get("summary"),
        event.get("text"),
        event.get("content"),
        event.get("message"),
    ]
    message = event.get("message") if isinstance(event.get("message"), dict) else None
    if message:
        candidates.extend([message.get("content"), message.get("text"), message.get("summary")])
    for raw in candidates:
        if raw is None:
            continue
        if isinstance(raw, dict):
            for key in ("text", "summary", "content"):
                value = raw.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        text = str(raw).strip()
        if not text:
            continue
        if text.startswith("{") and text.endswith("}"):
            try:
                data = json.loads(text)
                for key in ("text", "summary", "content"):
                    value = data.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
            except Exception:
                pass
        return text
    return ""


def extract_service_name(text: str, payload: Optional[Dict[str, Any]] = None) -> str:
    if payload:
        event = payload.get("event") if isinstance(payload.get("event"), dict) else payload
        service = str(event.get("service") or _nested_dict(payload, "command").get("service") or "").strip()
        if service:
            return service
    m = SERVICE_RE.search(text or "")
    if m:
        return m.group(1).lower()
    low = _lower(text)
    for service in KNOWN_SERVICES:
        if service in low:
            return service
    if "coupon" in low:
        return "coupon-service"
    if "order" in low:
        return "order-service"
    if "payment" in low or "支付" in low:
        return "payment-service"
    return ""


def _severity(text: str, payload: Optional[Dict[str, Any]] = None) -> str:
    if payload:
        event = payload.get("event") if isinstance(payload.get("event"), dict) else payload
        raw = str(event.get("severity") or _nested_dict(payload, "command").get("severity") or "").lower().strip()
        if raw:
            return raw
    low = _lower(text)
    if "p0" in low or "sev0" in low:
        return "p0"
    if "p1" in low or "sev1" in low or "严重" in low:
        return "p1"
    if "p3" in low or "sev3" in low:
        return "p3"
    return "p2" if any(term in low for term in INCIDENT_TERMS) else "info"


def _title(text: str, service: str, prefix: str) -> str:
    compact = re.sub(r"\s+", " ", text or "").strip()
    compact = compact[:120] or prefix
    if service and service not in compact:
        return f"{service}: {compact}"
    return compact


def _memory_kind(text: str) -> str:
    low = _lower(text)
    if any(term.lower() in low for term in GOVERNANCE_TERMS) and any(term in low for term in ("审批", "必须", "禁止", "不能", "不要", "policy", "must", "never")):
        return SERVICE_GOVERNANCE
    if any(term in low for term in ("503", "504", "429", "timeout", "超时", "故障", "错误率", "根因", "异常")):
        return FAULT_PATTERN
    if any(term in low for term in ("依赖", "owner", "负责人", "上游", "下游", "拓扑", "服务画像", "service profile")):
        return SERVICE_PROFILE
    if any(term in low for term in ("团队", "我们", "习惯", "优先", "高峰期", "通知", "排障")):
        return TEAM_PREFERENCE
    return MANUAL_NOTE


def _notebook_for_kind(kind: str) -> str:
    return notebook_for_kind(kind)


def _nested_dict(obj: Any, key: str) -> Dict[str, Any]:
    if isinstance(obj, dict) and isinstance(obj.get(key), dict):
        return obj[key]
    return {}


def extract_environment(payload: Optional[Dict[str, Any]] = None, default: str = "prod") -> str:
    """Return environment from common Runbook/Feishu/Alertmanager metadata shapes.

    This intentionally avoids chained conditional expressions; the previous
    version parsed {"environment": "staging"} as prod when no event object was
    present because of Python operator precedence.
    """
    if not isinstance(payload, dict):
        return default
    candidates: List[Any] = [payload.get("environment")]
    for container_key in ("event", "command", "payload", "alert", "incident"):
        obj = _nested_dict(payload, container_key)
        if obj:
            candidates.append(obj.get("environment"))
            nested_event = _nested_dict(obj, "event")
            if nested_event:
                candidates.append(nested_event.get("environment"))
            nested_cmd = _nested_dict(obj, "command")
            if nested_cmd:
                candidates.append(nested_cmd.get("environment"))
    for raw in candidates:
        value = str(raw or "").strip()
        if value:
            return value.lower()
    return default


class RunbookMemoryRouter:
    """Route Feishu/chat/Hermes turns into the right memory plane.

    The router is intentionally deterministic and conservative. It creates
    durable RunbookHermes domain memory only when messages are clearly about
    services, incidents, governance, fault patterns or runbook habits. Generic
    user preferences are left to Hermes native USER.md/session memory.
    """

    def __init__(self) -> None:
        self.settings = load_settings()

    def route_message(self, message: str, *, source: str = "chat", metadata: Optional[Dict[str, Any]] = None) -> RouteDecision:
        metadata = metadata or {}
        text = (message or extract_text_from_payload(metadata) or "").strip()
        low = _lower(text)
        service = extract_service_name(text, metadata)
        severity = _severity(text, metadata)
        environment = extract_environment(metadata)
        if not text:
            return RouteDecision(action="noop", target_plane="none", message="", source=source, confidence=1.0, reason="empty message", metadata=metadata)

        if any(term in low for term in SKILL_TERMS):
            return RouteDecision(
                action="publish_skill",
                target_plane="hermes_official_skills",
                message=text,
                source=source,
                service=service,
                title=_title(text, service, "RunbookHermes skill"),
                body=text,
                memory_kind=SKILL_INDEX,
                tags=["runbookhermes", "skill"],
                confidence=0.72,
                reason="message explicitly asks to save/publish a runbook skill",
                metadata=metadata,
            )

        if any(term in low for term in RECALL_TERMS) and (service or any(term in low for term in INCIDENT_TERMS + GOVERNANCE_TERMS)):
            return RouteDecision(
                action="recall",
                target_plane="runbook_hermes_domain_memory",
                message=text,
                source=source,
                service=service,
                severity=severity,
                environment=environment,
                title=_title(text, service, "RunbookHermes memory recall"),
                body=text,
                tags=["recall", source],
                confidence=0.76,
                reason="message asks for history/previous handling and mentions service or incident/governance terms",
                metadata=metadata,
            )

        explicit_remember = any(term.lower() in low for term in REMEMBER_TERMS)
        domain_governance = any(term.lower() in low for term in GOVERNANCE_TERMS)
        if explicit_remember and (service or domain_governance or any(term in low for term in INCIDENT_TERMS)):
            kind = _memory_kind(text)
            return RouteDecision(
                action="write_memory",
                target_plane="runbook_hermes_domain_memory",
                message=text,
                source=source,
                service=service,
                severity=severity,
                environment=environment,
                title=_title(text, service, "RunbookHermes domain memory"),
                body=text,
                memory_kind=kind,
                notebook=_notebook_for_kind(kind),
                tags=[kind, source] + ([service] if service else []),
                confidence=0.86,
                reason="explicit remember/rule message with RunbookHermes domain signal",
                metadata=metadata,
            )

        if any(term in low for term in INCIDENT_TERMS) and (service or "服务" in low or "系统" in low):
            return RouteDecision(
                action="create_incident",
                target_plane="runbook_hermes_incident_workflow",
                message=text,
                source=source,
                service=service or "payment-service",
                severity=severity if severity != "info" else "p2",
                environment=environment,
                title=_title(text, service, "RunbookHermes incident"),
                body=text,
                tags=["incident", source],
                confidence=0.82,
                reason="message looks like a service incident or alert",
                metadata=metadata,
            )

        if any(term in low for term in USER_PREF_TERMS) and not service:
            return RouteDecision(
                action="session_only",
                target_plane="hermes_native_user_or_session_memory",
                message=text,
                source=source,
                title="Hermes native user/session preference",
                body=text,
                confidence=0.74,
                reason="generic user preference should remain in Hermes native memory plane",
                metadata=metadata,
            )

        if service and domain_governance:
            kind = _memory_kind(text)
            return RouteDecision(
                action="write_memory",
                target_plane="runbook_hermes_domain_memory",
                message=text,
                source=source,
                service=service,
                severity=severity,
                environment=environment,
                title=_title(text, service, "RunbookHermes governance memory"),
                body=text,
                memory_kind=kind,
                notebook=_notebook_for_kind(kind),
                tags=[kind, source, service],
                confidence=0.67,
                reason="service-specific governance/team habit statement",
                metadata=metadata,
            )

        return RouteDecision(
            action="session_only",
            target_plane="hermes_native_session_memory",
            message=text,
            source=source,
            title="Hermes native session message",
            body=text,
            confidence=0.58,
            reason="no durable RunbookHermes domain memory signal detected",
            metadata=metadata,
        )

    def apply(self, decision: RouteDecision) -> Dict[str, Any]:
        if not self.settings.runbook_memory_router_enabled:
            return {"status": "disabled", "reason": "RUNBOOK_MEMORY_ROUTER_ENABLED=false", "route": decision.to_dict()}
        if decision.action == "write_memory":
            from .memory import get_memory_manager

            manager = get_memory_manager()
            indexed = manager.upsert_memory(
                kind=decision.memory_kind or MANUAL_NOTE,
                service=decision.service,
                title=decision.title,
                body=decision.body,
                tags=decision.tags,
                source=f"router:{decision.source}",
                incident_id=str(decision.metadata.get("incident_id") or ""),
                trust_score=0.62,
            )
            notebook = None
            if decision.notebook:
                notebook = manager.append_notebook(decision.notebook, decision.title, decision.body, source=f"router:{decision.source}")
            return {"status": "ok", "route": decision.to_dict(), "indexed_memory": indexed, "notebook": notebook}
        if decision.action == "recall":
            from .memory import get_memory_manager

            return {"status": "ok", "route": decision.to_dict(), "recall": get_memory_manager().recall_context(decision.message, service=decision.service, limit=self.settings.runbook_memory_context_limit)}
        if decision.action == "publish_skill":
            from .skill_publisher import get_skill_publisher

            skill = {
                "skill_id": str(decision.metadata.get("skill_id") or "router_skill"),
                "incident_id": str(decision.metadata.get("incident_id") or ""),
                "service": decision.service,
                "title": decision.title,
                "body": decision.body,
            }
            return {"status": "ok", "route": decision.to_dict(), "published": get_skill_publisher().publish_generated_skill(skill, incident=decision.metadata)}
        if decision.action == "create_incident":
            return {"status": "route_only", "route": decision.to_dict(), "message": "caller should create incident through incident_service.create_incident()"}
        return {"status": "ok", "route": decision.to_dict(), "result": "kept_in_hermes_native_session_memory"}
