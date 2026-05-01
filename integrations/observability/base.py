from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class HTTPResult:
    ok: bool
    status: int
    data: Dict[str, Any]
    error: str = ""


def request_json(base_url: str, path: str, params: Dict[str, Any] | None = None, token: str = "", tenant: str = "", timeout: int = 5) -> HTTPResult:
    if not base_url:
        return HTTPResult(False, 0, {}, "base_url_not_configured")
    url = base_url.rstrip('/') + path
    if params:
        url += '?' + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None and v != ''})
    req = urllib.request.Request(url)
    if token:
        req.add_header('Authorization', f'Bearer {token}')
    if tenant:
        req.add_header('X-Scope-OrgID', tenant)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode('utf-8')
            return HTTPResult(True, resp.status, json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        return HTTPResult(False, exc.code, {}, body[:500])
    except Exception as exc:
        return HTTPResult(False, 0, {}, f'{type(exc).__name__}: {exc}')


def evidence_error(source: str, service: str, message: str) -> Dict[str, Any]:
    return {
        'evidence_id': f'ev_{source}_error',
        'source': source,
        'service': service,
        'summary': message,
        'raw_ref': f'{source}://error',
        'confidence': 0.2,
        'details': {'error': message},
    }
