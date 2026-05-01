from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any, Dict, List

from .backends import get_observability_backend
from .config import load_settings
from .incident_service import dashboard_summary

ROOT = Path(__file__).resolve().parent.parent
MONITORED_SERVICES = ["payment-service", "coupon-service", "order-service"]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _extract_metrics(evidence: List[Dict[str, Any]]) -> Dict[str, float]:
    metrics = {
        "http_503_rate": 0.0,
        "http_504_rate": 0.0,
        "http_429_rate": 0.0,
        "p95_latency_seconds": 0.0,
        "qps": 0.0,
    }
    for item in evidence:
        metric = str(item.get("metric", "")).lower()
        value = _safe_float(item.get("value", 0.0))
        if "503" in metric:
            metrics["http_503_rate"] = max(metrics["http_503_rate"], value)
        elif "504" in metric:
            metrics["http_504_rate"] = max(metrics["http_504_rate"], value)
        elif "429" in metric:
            metrics["http_429_rate"] = max(metrics["http_429_rate"], value)
        elif "p95" in metric or "latency" in metric:
            metrics["p95_latency_seconds"] = max(metrics["p95_latency_seconds"], value)
        elif "qps" in metric or "request" in metric:
            metrics["qps"] = max(metrics["qps"], value)
    if not metrics["qps"]:
        # Good enough for the local demo: derive a visual-only load estimate.
        metrics["qps"] = round(12 + metrics["http_503_rate"] * 80 + metrics["http_504_rate"] * 60 + metrics["http_429_rate"] * 40, 2)
    return metrics


def _health_from_metrics(metrics: Dict[str, float]) -> Dict[str, Any]:
    error_score = max(metrics["http_503_rate"], metrics["http_504_rate"], metrics["http_429_rate"])
    latency = metrics["p95_latency_seconds"]
    if error_score >= 0.12 or latency >= 1.5:
        return {"state": "critical", "score": 28, "label": "Critical"}
    if error_score >= 0.04 or latency >= 0.8:
        return {"state": "degraded", "score": 62, "label": "Degraded"}
    return {"state": "healthy", "score": 92, "label": "Healthy"}


def _timeseries(metrics: Dict[str, float], points: int = 18) -> List[Dict[str, Any]]:
    now = int(time.time())
    base_503 = metrics["http_503_rate"]
    base_504 = metrics["http_504_rate"]
    base_429 = metrics["http_429_rate"]
    latency = max(metrics["p95_latency_seconds"], 0.12)
    qps = max(metrics["qps"], 8.0)
    rows = []
    for idx in range(points):
        # Deterministic wave, no random dependency. This keeps Web demos stable.
        p = idx / max(points - 1, 1)
        wave = 0.5 + 0.5 * math.sin(idx * 0.83)
        ramp = 0.35 + 0.65 * p
        rows.append(
            {
                "ts": now - (points - idx - 1) * 30,
                "http_503_rate": round(base_503 * ramp * (0.82 + 0.28 * wave), 4),
                "http_504_rate": round(base_504 * ramp * (0.78 + 0.22 * wave), 4),
                "http_429_rate": round(base_429 * ramp * (0.76 + 0.20 * wave), 4),
                "p95_latency_seconds": round(latency * ramp * (0.82 + 0.24 * wave), 3),
                "qps": round(qps * (0.88 + 0.22 * wave), 2),
            }
        )
    return rows


def _read_deploy_state() -> Dict[str, Any]:
    settings = load_settings()
    data = _load_json(settings.demo_deploy_state_file, {})
    if not isinstance(data, dict):
        return {}
    return data


def service_snapshot(service: str) -> Dict[str, Any]:
    backend = get_observability_backend()
    metrics_evidence = backend.prom_top_anomalies(service, "15m")
    log_evidence = backend.loki_query(service, "", limit=8)
    trace_evidence = backend.trace_search(service, error_only=True)
    deploy_evidence = backend.recent_deploys(service, since="2h")
    metrics = _extract_metrics(metrics_evidence)
    health = _health_from_metrics(metrics)
    return {
        "service": service,
        "health": health,
        "metrics": metrics,
        "series": _timeseries(metrics),
        "evidence": {
            "metrics": metrics_evidence,
            "logs": log_evidence,
            "traces": trace_evidence,
            "deploys": deploy_evidence,
        },
        "signals": {
            "error_rate_max": max(metrics["http_503_rate"], metrics["http_504_rate"], metrics["http_429_rate"]),
            "latency_p95_seconds": metrics["p95_latency_seconds"],
            "qps": metrics["qps"],
            "log_matches": sum(_safe_float(item.get("count", 0)) for item in log_evidence),
            "trace_error_count": sum(_safe_float(item.get("error_count", item.get("error_rate", 0))) for item in trace_evidence),
        },
    }


def live_overview() -> Dict[str, Any]:
    settings = load_settings()
    services = [service_snapshot(service) for service in MONITORED_SERVICES]
    deploy_state = _read_deploy_state()
    critical = [s for s in services if s["health"]["state"] == "critical"]
    degraded = [s for s in services if s["health"]["state"] == "degraded"]
    return {
        "status": "ok",
        "generated_at": time.time(),
        "mode": {
            "obs_backend": settings.obs_backend,
            "trace_backend": settings.trace_backend,
            "trace_provider_kind": settings.trace_provider_kind,
            "deploy_backend": settings.deploy_backend,
            "rollback_backend_kind": settings.rollback_backend_kind,
            "controlled_execution_enabled": settings.controlled_execution_enabled,
        },
        "totals": {
            "services": len(services),
            "critical": len(critical),
            "degraded": len(degraded),
            "healthy": len(services) - len(critical) - len(degraded),
        },
        "services": services,
        "topology": {
            "nodes": [
                {"id": "payment-service", "kind": "service", "state": next((s["health"]["state"] for s in services if s["service"] == "payment-service"), "unknown")},
                {"id": "order-service", "kind": "service", "state": next((s["health"]["state"] for s in services if s["service"] == "order-service"), "unknown")},
                {"id": "coupon-service", "kind": "service", "state": next((s["health"]["state"] for s in services if s["service"] == "coupon-service"), "unknown")},
                {"id": "mysql-payment", "kind": "database", "state": "dependency"},
                {"id": "redis", "kind": "cache", "state": "dependency"},
            ],
            "edges": [
                {"from": "payment-service", "to": "order-service", "label": "reserve order"},
                {"from": "payment-service", "to": "coupon-service", "label": "validate coupon"},
                {"from": "payment-service", "to": "mysql-payment", "label": "write payment"},
                {"from": "payment-service", "to": "redis", "label": "idempotency/cache"},
            ],
        },
        "deploy_state": deploy_state,
        "dashboard": dashboard_summary(),
    }
