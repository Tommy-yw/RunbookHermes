from __future__ import annotations

import time
from fastapi import FastAPI

from observability import log_event, metrics_response, observe, setup_tracing

setup_tracing()
app = FastAPI(title='coupon-service')

@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'coupon-service'}

@app.get('/coupon/validate')
def validate(slow: bool = False):
    with observe('/coupon/validate', 'GET') as set_status:
        if slow:
            time.sleep(1.2)
            log_event('WARN', 'coupon validation is slow', http_status=200, latency_ms=1200)
        else:
            log_event('INFO', 'coupon validation succeeded', http_status=200)
        set_status(200)
        return {'status': 'valid'}

@app.get('/metrics')
def metrics():
    return metrics_response()
