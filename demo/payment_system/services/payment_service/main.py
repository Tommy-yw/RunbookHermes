from __future__ import annotations

import os
import time
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException

from observability import log_event, metrics_response, observe, setup_tracing

setup_tracing()
app = FastAPI(title='payment-service')
ORDER_URL = os.getenv('ORDER_SERVICE_URL', 'http://127.0.0.1:8081')
COUPON_URL = os.getenv('COUPON_SERVICE_URL', 'http://127.0.0.1:8082')
VERSION_FILE = Path(os.getenv('PAYMENT_VERSION_FILE', '/app/runtime/payment-service-version.txt'))
FAULT_MODE = os.getenv('DEMO_FAULT_MODE', 'PAYMENT_503_AFTER_DEPLOY')


def version() -> str:
    try:
        return VERSION_FILE.read_text(encoding='utf-8').strip() or 'v2.3.1'
    except FileNotFoundError:
        return 'v2.3.1'


@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'payment-service', 'version': version(), 'fault_mode': FAULT_MODE}


@app.get('/version')
def current_version():
    return {'service': 'payment-service', 'version': version()}


@app.post('/pay')
def pay(order_id: str = 'order-demo', amount_cents: int = 1999):
    with observe('/pay', 'POST') as set_status:
        current = version()
        if current == 'v2.3.1' and FAULT_MODE == 'PAYMENT_503_AFTER_DEPLOY':
            log_event('ERROR', 'connection pool exhausted while creating payment record', version=current, http_status=503, dependency='mysql-payment')
            set_status(503)
            raise HTTPException(status_code=503, detail='connection pool exhausted')
        if FAULT_MODE == 'COUPON_504_TIMEOUT':
            try:
                httpx.get(f'{COUPON_URL}/coupon/validate', params={'slow': 'true'}, timeout=0.5)
            except Exception:
                log_event('ERROR', 'coupon-service request timed out; returning HTTP 504', version=current, http_status=504, dependency='coupon-service')
                set_status(504)
                raise HTTPException(status_code=504, detail='coupon-service timeout')
        if FAULT_MODE == 'ORDER_429_RATE_LIMIT':
            resp = httpx.post(f'{ORDER_URL}/orders/reserve', params={'rate_limit': 'true'}, timeout=1.0)
            if resp.status_code == 429:
                log_event('WARN', 'order-service reservation returned HTTP 429 rate_limit_exceeded', version=current, http_status=429, dependency='order-service')
                set_status(429)
                raise HTTPException(status_code=429, detail='order-service rate limited')
        log_event('INFO', 'payment accepted', version=current, http_status=200, order_id=order_id, amount_cents=amount_cents)
        set_status(200)
        return {'status': 'paid', 'order_id': order_id, 'version': current}


@app.get('/metrics')
def metrics():
    return metrics_response()
