from __future__ import annotations

import json
import logging
import os
import time
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Callable, Iterator

from fastapi import HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

try:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
except Exception:  # pragma: no cover
    trace = None

SERVICE_NAME = os.getenv("SERVICE_NAME", "service")
LOG_FILE = os.getenv("LOG_FILE", f"/tmp/{SERVICE_NAME}.log")
Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()])
logger = logging.getLogger(SERVICE_NAME)

REQUESTS = Counter("http_requests_total", "HTTP requests", ["service", "endpoint", "method", "status"])
DURATION = Histogram("http_request_duration_seconds", "HTTP request duration seconds", ["service", "endpoint"])

_TRACING_READY = False


def setup_tracing() -> None:
    """Configure OTLP tracing for the local payment demo services.

    The previous demo image configured an OTLP exporter but did not create
    request spans.  This function keeps the exporter setup small and idempotent;
    observe() below creates one span per handled endpoint.
    """
    global _TRACING_READY
    if _TRACING_READY or trace is None:
        return
    endpoint = os.getenv("JAEGER_OTLP_ENDPOINT")
    if not endpoint:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": SERVICE_NAME}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    _TRACING_READY = True


def log_event(level: str, message: str, **fields) -> None:
    payload = {"ts": time.time(), "level": level, "service": SERVICE_NAME, "message": message}
    payload.update(fields)
    logger.info(json.dumps(payload, ensure_ascii=False))


@contextmanager
def observe(endpoint: str, method: str = "GET") -> Iterator[Callable[[int | str], None]]:
    """Record Prometheus metrics and a Jaeger/OTLP span for a request.

    The status setter returned to handlers is authoritative.  If a handler sets
    503/504/429 and then raises FastAPI HTTPException, the Prometheus label stays
    503/504/429 instead of being overwritten as 500.
    """
    start = time.time()
    state = {"status": "200"}
    tracer = trace.get_tracer(SERVICE_NAME) if trace is not None else None
    span_cm = tracer.start_as_current_span(f"{method} {endpoint}") if tracer is not None else nullcontext()

    with span_cm as span:
        if span is not None:
            span.set_attribute("service.name", SERVICE_NAME)
            span.set_attribute("http.method", method)
            span.set_attribute("http.route", endpoint)

        def set_status(status: int | str) -> None:
            state["status"] = str(status)
            if span is not None:
                try:
                    span.set_attribute("http.status_code", int(status))
                except (TypeError, ValueError):
                    span.set_attribute("http.status_code", str(status))

        try:
            yield set_status
        except HTTPException as exc:
            # Preserve explicit application status codes such as 503, 504 and 429.
            set_status(exc.status_code)
            if span is not None:
                span.set_attribute("error", exc.status_code >= 500)
                span.set_attribute("exception.type", "HTTPException")
                span.set_attribute("exception.message", str(exc.detail))
            raise
        except Exception as exc:
            if state.get("status") == "200":
                set_status(500)
            if span is not None:
                span.set_attribute("error", True)
                span.set_attribute("exception.type", type(exc).__name__)
                span.set_attribute("exception.message", str(exc))
            raise
        finally:
            status = state.get("status", "500")
            if span is not None:
                try:
                    span.set_attribute("http.status_code", int(status))
                except (TypeError, ValueError):
                    span.set_attribute("http.status_code", status)
                span.set_attribute("runbook.endpoint", endpoint)
            REQUESTS.labels(SERVICE_NAME, endpoint, method, status).inc()
            DURATION.labels(SERVICE_NAME, endpoint).observe(time.time() - start)


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
