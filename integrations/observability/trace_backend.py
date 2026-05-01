from __future__ import annotations

from typing import Any, Dict, List

from .base import evidence_error, request_json


class JaegerTraceBackend:
    def __init__(self, base_url: str, token: str = '', timeout: int = 5):
        self.base_url = base_url
        self.token = token
        self.timeout = timeout

    def trace_search(self, service: str, start: str = '', end: str = '', error_only: bool = True) -> List[Dict[str, Any]]:
        params = {'service': service, 'lookback': '1h', 'limit': 20}
        res = request_json(self.base_url, '/api/traces', params, self.token, '', self.timeout)
        if not res.ok:
            return [evidence_error('trace', service, f'Jaeger query failed: {res.error}')]
        traces = res.data.get('data', [])
        slowest = 0
        error_count = 0
        downstream = ''
        for trace in traces:
            processes = trace.get('processes', {})
            for span in trace.get('spans', []):
                duration_ms = span.get('duration', 0) / 1000.0
                slowest = max(slowest, duration_ms)
                tags = {t.get('key'): t.get('value') for t in span.get('tags', [])}
                if tags.get('error') is True or tags.get('http.status_code') in {503, 504, '503', '504'}:
                    error_count += 1
                proc = processes.get(span.get('processID', ''), {})
                svc = proc.get('serviceName', '')
                if svc and svc != service:
                    downstream = svc
        if error_only and error_count == 0 and slowest == 0:
            return [{
                'evidence_id': 'ev_trace_no_error_spans',
                'source': 'trace',
                'service': service,
                'summary': 'No error trace spans were returned by Jaeger.',
                'raw_ref': f'jaeger://traces?service={service}',
                'confidence': 0.55,
            }]
        return [{
            'evidence_id': 'ev_trace_jaeger_latency',
            'source': 'trace',
            'service': service,
            'downstream': downstream or 'unknown',
            'p95_ms': slowest,
            'error_count': error_count,
            'summary': f'Jaeger returned {len(traces)} traces; slowest span is {slowest:.1f} ms; error spans={error_count}.',
            'raw_ref': f'jaeger://traces?service={service}',
            'confidence': 0.82,
            'details': {'trace_count': len(traces)},
        }]


class TempoTraceBackend(JaegerTraceBackend):
    """Placeholder using the same interface; implement Tempo search in a later hardening pass."""

    def trace_search(self, service: str, start: str = '', end: str = '', error_only: bool = True) -> List[Dict[str, Any]]:
        return [evidence_error('trace', service, 'Tempo adapter shell exists, but local demo uses Jaeger first.')]
