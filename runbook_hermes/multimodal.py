from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .config import load_settings

SERVICE_RE = re.compile(r"\b([a-z][a-z0-9-]{1,60}-service)\b", re.I)
EDGE_RE = re.compile(r"([a-z][a-z0-9-]{1,60}(?:-service)?)\s*(?:-->|->|=>|→|calls?|depends\s+on|依赖|调用)\s*([a-z][a-z0-9-]{1,60}(?:-service)?)", re.I)
ERROR_PATTERNS = {
    "http_503": re.compile(r"\b503\b|connection pool|db_pool|mysql", re.I),
    "http_504": re.compile(r"\b504\b|timeout|timed out|超时", re.I),
    "http_429": re.compile(r"\b429\b|rate[ _-]?limit|限流", re.I),
    "latency": re.compile(r"p95|p99|latency|延迟|slow|spike", re.I),
    "deploy": re.compile(r"deploy|release|rollout|canary|v\d+\.\d+\.\d+|发布|变更", re.I),
}


@dataclass
class VisualReference:
    kind: str
    image_path: str = ""
    image_url: str = ""
    text_hint: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    source: str = "api"

    @classmethod
    def from_obj(cls, obj: Dict[str, Any] | "VisualReference") -> "VisualReference":
        if isinstance(obj, VisualReference):
            return obj
        payload = obj.get("payload") if isinstance(obj.get("payload"), dict) else {}
        return cls(
            kind=str(obj.get("kind") or obj.get("type") or "dashboard_image"),
            image_path=str(obj.get("image_path") or obj.get("path") or ""),
            image_url=str(obj.get("image_url") or obj.get("url") or ""),
            text_hint=str(obj.get("text_hint") or obj.get("ocr_text") or obj.get("caption") or ""),
            payload=payload,
            source=str(obj.get("source") or "api"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _jsonable(data: Any) -> str:
    try:
        return json.dumps(data, ensure_ascii=False, sort_keys=True)
    except Exception:
        return str(data)


def _ref_text(ref: VisualReference) -> str:
    parts = [ref.kind, ref.image_path, ref.image_url, ref.text_hint]
    if ref.payload:
        parts.append(_jsonable(ref.payload))
    return "\n".join(part for part in parts if part)


def _safe_image_ref(ref: VisualReference) -> Dict[str, Any]:
    out = {"kind": ref.kind, "source": ref.source}
    if ref.image_url:
        out["image_url"] = ref.image_url
    if ref.image_path:
        p = Path(ref.image_path)
        out["image_path"] = str(p)
        out["image_exists"] = p.exists()
    return out


def parse_topology(text: str, service: str = "") -> Dict[str, Any]:
    text = text or ""
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, str]] = []

    def normalize_node(name: str) -> str:
        node = (name or "").strip().lower()
        if not node.endswith("-service") and node in {"payment", "coupon", "order"}:
            node += "-service"
        return node

    def add_node(name: str) -> str:
        node = normalize_node(name)
        if not node:
            return ""
        nodes.setdefault(node, {"id": node, "kind": "service" if node.endswith("-service") else "dependency"})
        return node

    def add_edge(src: str, dst: str) -> None:
        src = add_node(src)
        dst = add_node(dst)
        if not src or not dst or src == dst:
            return
        edge = {"from": src, "to": dst, "label": "observed-dependency"}
        if edge not in edges:
            edges.append(edge)

    token_re = re.compile(r"[a-z][a-z0-9-]{1,60}(?:-service)?", re.I)
    for line in text.splitlines() or [text]:
        if any(marker in line for marker in ("->", "-->", "=>", "→")):
            parts = [p.strip() for p in re.split(r"(?:-->|->|=>|→)", line) if p.strip()]
            chain: List[str] = []
            for part in parts:
                m = token_re.search(part)
                if m:
                    chain.append(m.group(0))
            for left, right in zip(chain, chain[1:]):
                add_edge(left, right)
    for match in EDGE_RE.finditer(text):
        add_edge(match.group(1), match.group(2))
    for match in SERVICE_RE.finditer(text):
        add_node(match.group(1))
    if service:
        add_node(service)
    return {"status": "ok", "nodes": list(nodes.values()), "edges": edges, "node_count": len(nodes), "edge_count": len(edges)}


def _infer_findings(kind: str, text: str, service: str) -> List[str]:
    low = text.lower()
    findings: List[str] = []
    for label, pattern in ERROR_PATTERNS.items():
        if pattern.search(text):
            findings.append(label)
    if kind in {"grafana_screenshot", "monitoring_dashboard", "dashboard_image"} and not findings:
        findings.append("dashboard_visual_review_needed")
    if kind == "feishu_alert_card" and ("告警" in text or "alert" in low):
        findings.append("alert_card_context")
    if kind == "log_screenshot" and not any(x in findings for x in ("http_503", "http_504", "http_429")):
        findings.append("log_text_review_needed")
    if service and service in low:
        findings.append(f"service:{service}")
    # Preserve order while deduplicating.
    out: List[str] = []
    for item in findings:
        if item not in out:
            out.append(item)
    return out


def _summary_for(kind: str, service: str, findings: List[str]) -> str:
    if kind == "grafana_screenshot":
        return f"Grafana screenshot analyzed for {service or 'service'}: " + (", ".join(findings) or "no strong visual anomaly extracted")
    if kind == "feishu_alert_card":
        return f"Feishu alert card image/payload analyzed for {service or 'service'}: " + (", ".join(findings) or "alert context captured")
    if kind == "topology_diagram":
        return f"Topology diagram parsed for {service or 'service'}: dependency nodes and edges extracted"
    if kind == "log_screenshot":
        return f"Log screenshot analyzed for {service or 'service'}: " + (", ".join(findings) or "log text captured")
    if kind in {"monitoring_dashboard", "dashboard_image"}:
        return f"Monitoring dashboard image/snapshot summarized for {service or 'service'}: " + (", ".join(findings) or "dashboard state captured")
    return f"Visual evidence analyzed for {service or 'service'}: " + (", ".join(findings) or kind)


def _try_hermes_vision(ref: VisualReference, prompt: str) -> Dict[str, Any]:
    settings = load_settings()
    if not settings.runbook_multimodal_use_hermes_vision:
        return {"status": "disabled", "reason": "RUNBOOK_MULTIMODAL_USE_HERMES_VISION=false"}
    image_arg = ref.image_path or ref.image_url
    if not image_arg:
        return {"status": "skipped", "reason": "no_image_ref"}
    try:
        from model_tools import handle_function_call

        raw = handle_function_call("vision_analyze", {"image": image_arg, "prompt": prompt})
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"text": raw}
        return {"status": "ok", "result": parsed}
    except Exception as exc:
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}


def analyze_visual_reference(ref: Dict[str, Any] | VisualReference, *, service: str = "", incident_id: str = "", summary: str = "") -> Dict[str, Any]:
    ref = VisualReference.from_obj(ref)
    kind = ref.kind.strip().lower().replace(" ", "_") or "dashboard_image"
    text = "\n".join(x for x in [summary, _ref_text(ref)] if x)
    topology = parse_topology(text, service=service) if kind == "topology_diagram" or "->" in text or "→" in text or "依赖" in text else {"status": "skipped"}
    findings = _infer_findings(kind, text, service)
    vision = _try_hermes_vision(ref, prompt=f"Analyze this AIOps {kind} for service={service}. Extract anomalies, labels, topology and evidence.")
    details = {
        "visual_ref": _safe_image_ref(ref),
        "findings": findings,
        "text_hint": ref.text_hint[:2000],
        "topology": topology,
        "vision": vision,
    }
    evidence = {
        "evidence_id": "",
        "source": f"multimodal:{kind}",
        "service": service,
        "summary": _summary_for(kind, service, findings),
        "raw_ref": ref.image_url or ref.image_path or f"payload://{kind}",
        "confidence": 0.72 if findings else 0.52,
        "details": details,
    }
    if incident_id:
        evidence["incident_id"] = incident_id
    return evidence


def dashboard_snapshot_evidence(service: str, incident_id: str = "") -> Dict[str, Any]:
    try:
        from . import monitoring

        snapshot = monitoring.service_snapshot(service)
        signals = snapshot.get("signals") or {}
        health = snapshot.get("health") or {}
        text = _jsonable({"health": health, "signals": signals, "metrics": snapshot.get("metrics")})
        ref = VisualReference(kind="monitoring_dashboard", text_hint=text, source="monitoring.live_overview")
        evidence = analyze_visual_reference(ref, service=service, incident_id=incident_id, summary=f"dashboard health={health.get('state')}")
        evidence["details"]["dashboard_snapshot"] = {"health": health, "signals": signals, "metrics": snapshot.get("metrics")}
        evidence["summary"] = f"Monitoring dashboard snapshot for {service}: health={health.get('state', 'unknown')}, error_rate_max={signals.get('error_rate_max')}, p95={signals.get('latency_p95_seconds')}s"
        evidence["confidence"] = 0.76
        return evidence
    except Exception as exc:
        return {
            "evidence_id": "",
            "source": "multimodal:monitoring_dashboard",
            "service": service,
            "summary": f"Monitoring dashboard snapshot unavailable: {type(exc).__name__}: {exc}",
            "raw_ref": "monitoring://dashboard-unavailable",
            "confidence": 0.25,
            "details": {"error": str(exc)},
        }


def collect_multimodal_evidence(
    *,
    service: str,
    summary: str = "",
    incident_id: str = "",
    visual_refs: Optional[Iterable[Dict[str, Any]]] = None,
    include_dashboard_snapshot: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    settings = load_settings()
    if not settings.runbook_multimodal_enabled:
        return []
    include_dashboard = settings.runbook_multimodal_collect_dashboards if include_dashboard_snapshot is None else bool(include_dashboard_snapshot)
    evidence: List[Dict[str, Any]] = []
    for obj in visual_refs or []:
        try:
            evidence.append(analyze_visual_reference(obj, service=service, incident_id=incident_id, summary=summary))
        except Exception as exc:
            evidence.append(
                {
                    "evidence_id": "",
                    "source": "multimodal:error",
                    "service": service,
                    "summary": f"Visual evidence analysis failed: {type(exc).__name__}: {exc}",
                    "raw_ref": "visual://error",
                    "confidence": 0.2,
                    "details": {"error": str(exc), "input": obj if isinstance(obj, dict) else str(obj)},
                }
            )
    if include_dashboard:
        evidence.append(dashboard_snapshot_evidence(service, incident_id=incident_id))
    for idx, item in enumerate(evidence, start=1):
        item.setdefault("service", service)
        item.setdefault("raw_ref", f"visual://{idx}")
        if not item.get("evidence_id"):
            item["evidence_id"] = f"ev_visual_{int(time.time())}_{idx}"
    return evidence
