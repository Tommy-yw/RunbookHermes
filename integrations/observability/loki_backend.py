from __future__ import annotations

import time
from typing import Any, Dict, List

from .base import evidence_error, request_json


class LokiBackend:
    def __init__(self, base_url: str, token: str = '', tenant: str = '', timeout: int = 5):
        self.base_url = base_url
        self.token = token
        self.tenant = tenant
        self.timeout = timeout

    def loki_query(self, service: str, query: str = '', start: str = '', end: str = '', limit: int = 20) -> List[Dict[str, Any]]:
        selector = f'{{service="{service}"}}'
        search = query or 'connection pool exhausted'
        loki_query = f'{selector} |= "{search}"' if search else selector
        now_ns = int(time.time() * 1_000_000_000)
        start_ns = now_ns - 30 * 60 * 1_000_000_000
        params = {'query': loki_query, 'limit': limit, 'direction': 'backward', 'start': start or start_ns, 'end': end or now_ns}
        res = request_json(self.base_url, '/loki/api/v1/query_range', params, self.token, self.tenant, self.timeout)
        if not res.ok:
            return [evidence_error('loki', service, f'Loki query failed: {res.error}')]
        evidence: List[Dict[str, Any]] = []
        streams = res.data.get('data', {}).get('result', [])
        count = 0
        samples: List[str] = []
        for stream in streams:
            for _, line in stream.get('values', [])[:limit]:
                count += 1
                if len(samples) < 3:
                    samples.append(line[:240])
        evidence.append({
            'evidence_id': 'ev_log_loki_query',
            'source': 'loki',
            'service': service,
            'summary': f'Loki returned {count} matching log lines for query: {search}',
            'matched_terms': [search] if search else [],
            'count': count,
            'raw_ref': f'loki://query?service={service}',
            'confidence': 0.84 if count else 0.55,
            'details': {'query': loki_query, 'samples': samples},
        })
        return evidence
