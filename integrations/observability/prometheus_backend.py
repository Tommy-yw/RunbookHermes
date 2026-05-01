from __future__ import annotations

from typing import Any, Dict, List

from .base import evidence_error, request_json


def _value_from_vector(payload: Dict[str, Any]) -> float:
    try:
        result = payload.get('data', {}).get('result', [])
        if not result:
            return 0.0
        value = result[0].get('value', [0, '0'])[1]
        return float(value)
    except Exception:
        return 0.0


class PrometheusBackend:
    def __init__(self, base_url: str, token: str = '', tenant: str = '', timeout: int = 5):
        self.base_url = base_url
        self.token = token
        self.tenant = tenant
        self.timeout = timeout

    def query(self, query: str) -> Dict[str, Any]:
        return request_json(self.base_url, '/api/v1/query', {'query': query}, self.token, self.tenant, self.timeout).__dict__

    def query_range(self, query: str, start: str, end: str, step: str = '15s') -> Dict[str, Any]:
        return request_json(self.base_url, '/api/v1/query_range', {'query': query, 'start': start, 'end': end, 'step': step}, self.token, self.tenant, self.timeout).__dict__

    def prom_query(self, service: str, query: str = '', window: str = '15m') -> Dict[str, Any]:
        query = query or f'sum(rate(http_requests_total{{service="{service}",status="503"}}[5m]))'
        res = request_json(self.base_url, '/api/v1/query', {'query': query}, self.token, self.tenant, self.timeout)
        return {'status': 'success' if res.ok else 'error', 'service': service, 'query': query, 'window': window, 'data': res.data, 'error': res.error}

    def prom_top_anomalies(self, service: str, window: str = '15m') -> List[Dict[str, Any]]:
        checks = [
            ('http_503_rate', f'sum(rate(http_requests_total{{service="{service}",status="503"}}[5m]))'),
            ('http_504_rate', f'sum(rate(http_requests_total{{service="{service}",status="504"}}[5m]))'),
            ('http_429_rate', f'sum(rate(http_requests_total{{service="{service}",status="429"}}[5m]))'),
            ('p95_latency_seconds', f'histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{{service="{service}"}}[5m])) by (le))'),
        ]
        evidence: List[Dict[str, Any]] = []
        for metric, query in checks:
            res = request_json(self.base_url, '/api/v1/query', {'query': query}, self.token, self.tenant, self.timeout)
            if not res.ok:
                evidence.append(evidence_error('prometheus', service, f'Prometheus query failed for {metric}: {res.error}'))
                continue
            value = _value_from_vector(res.data)
            if value <= 0:
                continue
            evidence.append({
                'evidence_id': f'ev_metric_{metric}',
                'source': 'prometheus',
                'service': service,
                'summary': f'{metric} is {value:.4f}',
                'metric': metric,
                'value': value,
                'window': window,
                'raw_ref': f'prometheus://query?metric={metric}',
                'confidence': 0.86,
                'details': {'query': query, 'response': res.data},
            })
        if not evidence:
            evidence.append({
                'evidence_id': 'ev_metric_no_active_error_rate',
                'source': 'prometheus',
                'service': service,
                'summary': 'No active 503, 504 or 429 error-rate anomaly was returned by Prometheus.',
                'metric': 'http_error_rate',
                'value': 0,
                'window': window,
                'raw_ref': 'prometheus://query/no-active-error-rate',
                'confidence': 0.65,
            })
        return evidence
