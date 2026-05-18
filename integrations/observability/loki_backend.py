from __future__ import annotations

from typing import Any, Dict, List

from .base import QueryWindow, evidence_error, normalize_evidence, request_json


class LokiBackend:
    def __init__(self, base_url: str, token: str = "", tenant: str = "", timeout: int = 5, service_label: str = "service"):
        self.base_url = base_url
        self.token = token
        self.tenant = tenant
        self.timeout = timeout
        self.service_label = service_label or "service"

    def loki_query(self, service: str, query: str = "", start: str = "", end: str = "", limit: int = 20) -> List[Dict[str, Any]]:
        selector = f'{{{self.service_label}="{service}"}}'
        search = query or "connection pool exhausted"
        loki_query = f'{selector} |= "{search}"' if search else selector
        window = QueryWindow(start=start, end=end)
        bounds = window.as_loki_ns()
        params = {"query": loki_query, "limit": limit, "direction": "backward", "start": bounds["start"], "end": bounds["end"]}
        res = request_json(self.base_url, "/loki/api/v1/query_range", params, self.token, self.tenant, self.timeout)
        if not res.ok:
            return [evidence_error("loki", service, f"Loki query failed: {res.error}")]
        evidence: List[Dict[str, Any]] = []
        streams = res.data.get("data", {}).get("result", [])
        count = 0
        samples: List[str] = []
        labels: List[Dict[str, Any]] = []
        for stream in streams:
            if isinstance(stream.get("stream"), dict) and len(labels) < 3:
                labels.append(stream.get("stream", {}))
            for _, line in stream.get("values", [])[:limit]:
                count += 1
                if len(samples) < 3:
                    samples.append(str(line)[:240])
        evidence.append(
            normalize_evidence(
                source="loki",
                service=service,
                evidence_id="ev_log_loki_query",
                summary=f"Loki returned {count} matching log lines for query: {search}",
                raw_ref=f"loki://query?service={service}",
                confidence=0.84 if count else 0.55,
                details={"query": loki_query, "samples": samples, "labels": labels},
                matched_terms=[search] if search else [],
                count=count,
            )
        )
        return evidence
