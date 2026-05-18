from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

from .base import QueryWindow, evidence_error, normalize_evidence, request_json


def _tag_map(tags: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for tag in tags or []:
        if not isinstance(tag, dict):
            continue
        out[str(tag.get("key"))] = tag.get("value")
    return out


def _status_is_error(tags: Dict[str, Any]) -> bool:
    code = tags.get("http.status_code") or tags.get("status.code") or tags.get("otel.status_code")
    if tags.get("error") is True or str(tags.get("error", "")).lower() == "true":
        return True
    try:
        return int(code) >= 500
    except Exception:
        return str(code).upper() == "ERROR"


class JaegerTraceBackend:
    def __init__(self, base_url: str, token: str = "", timeout: int = 5):
        self.base_url = base_url
        self.token = token
        self.timeout = timeout

    def trace_search(self, service: str, start: str = "", end: str = "", error_only: bool = True) -> List[Dict[str, Any]]:
        params = {"service": service, "lookback": "1h", "limit": 20}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        res = request_json(self.base_url, "/api/traces", params, self.token, "", self.timeout)
        if not res.ok:
            return [evidence_error("trace", service, f"Jaeger query failed: {res.error}")]
        traces = res.data.get("data", [])
        slowest = 0.0
        error_count = 0
        downstream = ""
        trace_ids: List[str] = []
        for trace in traces:
            if trace.get("traceID") and len(trace_ids) < 5:
                trace_ids.append(str(trace.get("traceID")))
            processes = trace.get("processes", {})
            for span in trace.get("spans", []):
                duration_ms = float(span.get("duration", 0) or 0) / 1000.0
                slowest = max(slowest, duration_ms)
                tags = _tag_map(span.get("tags", []))
                if _status_is_error(tags):
                    error_count += 1
                proc = processes.get(span.get("processID", ""), {})
                svc = proc.get("serviceName", "")
                if svc and svc != service:
                    downstream = svc
        if error_only and error_count == 0 and slowest == 0:
            return [
                normalize_evidence(
                    source="trace",
                    service=service,
                    evidence_id="ev_trace_no_error_spans",
                    summary="No error trace spans were returned by Jaeger.",
                    raw_ref=f"jaeger://traces?service={service}",
                    confidence=0.55,
                    details={"provider": "jaeger"},
                )
            ]
        return [
            normalize_evidence(
                source="trace",
                service=service,
                evidence_id="ev_trace_jaeger_latency",
                summary=f"Jaeger returned {len(traces)} traces; slowest span is {slowest:.1f} ms; error spans={error_count}.",
                raw_ref=f"jaeger://traces?service={service}",
                confidence=0.82,
                details={"trace_count": len(traces), "trace_ids": trace_ids, "provider": "jaeger"},
                downstream=downstream or "unknown",
                p95_ms=slowest,
                error_count=error_count,
            )
        ]


class TempoTraceBackend:
    def __init__(self, base_url: str, token: str = "", timeout: int = 5, tenant: str = ""):
        self.base_url = base_url
        self.token = token
        self.timeout = timeout
        self.tenant = tenant

    def trace_search(self, service: str, start: str = "", end: str = "", error_only: bool = True) -> List[Dict[str, Any]]:
        window = QueryWindow(start=start, end=end, lookback_seconds=3600)
        bounds = window.as_unix_seconds()
        # Tempo search supports tag filters in common deployments. The q form is
        # kept in details for operators using TraceQL-capable Tempo versions.
        traceql = f'{{ resource.service.name = "{service}" }}'
        params = {"tags": f"service.name={service}", "limit": 20, "start": bounds["start"], "end": bounds["end"]}
        res = request_json(self.base_url, "/api/search", params, self.token, self.tenant, self.timeout)
        if not res.ok:
            # Some Tempo gateways expose TraceQL search on /api/search with q.
            res = request_json(self.base_url, "/api/search", {"q": traceql, "limit": 20, "start": bounds["start"], "end": bounds["end"]}, self.token, self.tenant, self.timeout)
        if not res.ok:
            return [evidence_error("trace", service, f"Tempo query failed: {res.error}")]
        data = res.data.get("data", res.data)
        traces = data.get("traces") if isinstance(data, dict) else []
        if traces is None and isinstance(data, list):
            traces = data
        traces = traces or []
        error_count = 0
        slowest = 0.0
        trace_ids: List[str] = []
        for trace in traces:
            if not isinstance(trace, dict):
                continue
            tid = trace.get("traceID") or trace.get("traceId") or trace.get("id")
            if tid and len(trace_ids) < 5:
                trace_ids.append(str(tid))
            slowest = max(slowest, float(trace.get("durationMs") or trace.get("duration_ms") or trace.get("duration") or 0))
            root = str(trace.get("rootServiceName") or trace.get("serviceName") or "")
            status = str(trace.get("status") or trace.get("statusCode") or "").lower()
            if "error" in status or trace.get("error") is True:
                error_count += 1
            if error_only and root and root != service:
                # Still useful as downstream evidence; do not filter locally.
                pass
        return [
            normalize_evidence(
                source="trace",
                service=service,
                evidence_id="ev_trace_tempo_search",
                summary=f"Tempo returned {len(traces)} candidate traces; max reported duration is {slowest:.1f} ms; error traces={error_count}.",
                raw_ref=f"tempo://search?service={service}",
                confidence=0.80 if traces else 0.55,
                details={"provider": "tempo", "traceql": traceql, "trace_ids": trace_ids, "raw_count": len(traces)},
                p95_ms=slowest,
                error_count=error_count,
            )
        ]
