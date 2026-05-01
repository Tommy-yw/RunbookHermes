from __future__ import annotations

from fastapi import FastAPI, HTTPException

from observability import log_event, metrics_response, observe, setup_tracing

setup_tracing()
app = FastAPI(title='order-service')

@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'order-service'}

@app.post('/orders/reserve')
def reserve(rate_limit: bool = False):
    with observe('/orders/reserve', 'POST') as set_status:
        if rate_limit:
            log_event('WARN', 'rate_limit_exceeded while reserving order inventory', http_status=429)
            set_status(429)
            raise HTTPException(status_code=429, detail='rate_limit_exceeded')
        log_event('INFO', 'order inventory reserved', http_status=200)
        set_status(200)
        return {'status': 'reserved'}

@app.get('/metrics')
def metrics():
    return metrics_response()
