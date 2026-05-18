from __future__ import annotations

from typing import Any, Dict, List

from .base import evidence_error, normalize_evidence, request_json


def _value_from_vector(payload: Dict[str, Any]) -> float:
    try:
        result = payload.get("data", {}).get("result", [])
        if not result:
            return 0.0
        value = result[0].get("value", [0, "0"])[1]
        return float(value)
    except Exception:
        return 0.0


class PrometheusBackend:
    def __init__(
        self,
        base_url: str,
        token: str = "",
        tenant: str = "",
        timeout: int = 5,
        service_label: str = "service",
    ):
        self.base_url = base_url
        self.token = token
        self.tenant = tenant
        self.timeout = timeout
        self.service_label = service_label or "service"

    def _selector(self, service: str, extra: str = "") -> str:
        labels = f'{self.service_label}="{service}"'
        if extra:
            labels += "," + extra.strip().strip(",")
        return "{" + labels + "}"

    def _status_rate_query(self, service: str, status: str) -> str:
        status_selector = self._selector(service, f'status="{status}"')
        return f"sum(rate(http_requests_total{status_selector}[5m]))"

    def query(self, query: str) -> Dict[str, Any]:
        return request_json(
            self.base_url,
            "/api/v1/query",
            {"query": query},
            self.token,
            self.tenant,
            self.timeout,
        ).__dict__

    def query_range(self, query: str, start: str, end: str, step: str = "15s") -> Dict[str, Any]:
        return request_json(
            self.base_url,
            "/api/v1/query_range",
            {"query": query, "start": start, "end": end, "step": step},
            self.token,
            self.tenant,
            self.timeout,
        ).__dict__

    def prom_query(self, service: str, query: str = "", window: str = "15m") -> Dict[str, Any]:
        query = query or self._status_rate_query(service, "503")
        res = request_json(
            self.base_url,
            "/api/v1/query",
            {"query": query},
            self.token,
            self.tenant,
            self.timeout,
        )
        return {
            "status": "success" if res.ok else "error",
            "service": service,
            "query": query,
            "window": window,
            "data": res.data,
            "error": res.error,
            "adapter": "prometheus",
        }

    def prom_top_anomalies(self, service: str, window: str = "15m") -> List[Dict[str, Any]]:
        latency_selector = self._selector(service)

        checks = [
            ("http_503_rate", self._status_rate_query(service, "503")),
            ("http_504_rate", self._status_rate_query(service, "504")),
            ("http_429_rate", self._status_rate_query(service, "429")),
            (
                "p95_latency_seconds",
                f"histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{latency_selector}[5m])) by (le))",
            ),
        ]

        evidence: List[Dict[str, Any]] = []

        for metric, query in checks:
            res = request_json(
                self.base_url,
                "/api/v1/query",
                {"query": query},
                self.token,
                self.tenant,
                self.timeout,
            )

            if not res.ok:
                evidence.append(
                    evidence_error(
                        "prometheus",
                        service,
                        f"Prometheus query failed for {metric}: {res.error}",
                    )
                )
                continue

            value = _value_from_vector(res.data)
            if value <= 0:
                continue

            evidence.append(
                normalize_evidence(
                    source="prometheus",
                    service=service,
                    evidence_id=f"ev_metric_{metric}",
                    summary=f"{metric} is {value:.4f}",
                    raw_ref=f"prometheus://query?metric={metric}",
                    confidence=0.86,
                    details={"query": query, "response": res.data},
                    metric=metric,
                    value=value,
                    window=window,
                )
            )

        if not evidence:
            evidence.append(
                normalize_evidence(
                    source="prometheus",
                    service=service,
                    evidence_id="ev_metric_no_active_error_rate",
                    summary="No active 503, 504 or 429 error-rate anomaly was returned by Prometheus.",
                    raw_ref="prometheus://query/no-active-error-rate",
                    confidence=0.65,
                    metric="http_error_rate",
                    value=0,
                    window=window,
                )
            )

        return evidence