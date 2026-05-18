from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional


@dataclass
class HTTPResult:
    ok: bool
    status: int
    data: Dict[str, Any]
    error: str = ""


@dataclass(frozen=True)
class QueryWindow:
    start: str = ""
    end: str = ""
    step: str = "15s"
    lookback_seconds: int = 1800

    def as_loki_ns(self) -> Dict[str, int | str]:
        now_ns = int(time.time() * 1_000_000_000)
        start_ns = now_ns - self.lookback_seconds * 1_000_000_000
        return {"start": self.start or start_ns, "end": self.end or now_ns}

    def as_unix_seconds(self) -> Dict[str, int | str]:
        now = int(time.time())
        return {"start": self.start or now - self.lookback_seconds, "end": self.end or now}


def request_json(
    base_url: str,
    path: str,
    params: Dict[str, Any] | None = None,
    token: str = "",
    tenant: str = "",
    timeout: int = 5,
    headers: Mapping[str, str] | None = None,
) -> HTTPResult:
    if not base_url:
        return HTTPResult(False, 0, {}, "base_url_not_configured")
    url = base_url.rstrip("/") + path
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None and v != ""})
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if tenant:
        req.add_header("X-Scope-OrgID", tenant)
    for key, value in (headers or {}).items():
        if value:
            req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return HTTPResult(True, resp.status, json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return HTTPResult(False, exc.code, {}, body[:1000])
    except Exception as exc:
        return HTTPResult(False, 0, {}, f"{type(exc).__name__}: {exc}")


def normalize_evidence(
    *,
    source: str,
    service: str,
    summary: str,
    evidence_id: str,
    confidence: float = 0.75,
    raw_ref: str = "",
    details: Dict[str, Any] | None = None,
    **extra: Any,
) -> Dict[str, Any]:
    item = {
        "evidence_id": evidence_id,
        "source": source,
        "service": service,
        "summary": summary,
        "raw_ref": raw_ref or f"{source}://{service}",
        "confidence": confidence,
        "details": details or {},
        "adapter_version": "observability.v2",
    }
    item.update({k: v for k, v in extra.items() if v is not None})
    return item


def evidence_error(source: str, service: str, message: str) -> Dict[str, Any]:
    return normalize_evidence(
        source=source,
        service=service,
        evidence_id=f"ev_{source}_error",
        summary=message,
        raw_ref=f"{source}://error",
        confidence=0.2,
        details={"error": message},
        status="error",
    )
