# RunbookHermes Payment Demo System

This is a small local business system for RunbookHermes to observe.
It is intentionally simple and only exists to prove that RunbookHermes can query real Prometheus, Loki and Jaeger signals instead of local mock JSON.

## Services

- `payment-service` on `http://127.0.0.1:8080`
- `order-service` on `http://127.0.0.1:8081`
- `coupon-service` on `http://127.0.0.1:8082`
- MySQL on `127.0.0.1:3306`
- Redis on `127.0.0.1:6379`
- Prometheus on `http://127.0.0.1:9090`
- Loki on `http://127.0.0.1:3100`
- Jaeger on `http://127.0.0.1:16686`
- Grafana on `http://127.0.0.1:3000`

## Faults

The default fault is specific and uses HTTP 503 explicitly:

1. `PAYMENT_503_AFTER_DEPLOY`: `payment-service` version `v2.3.1` returns HTTP 503 and logs `connection pool exhausted`.
2. `COUPON_504_TIMEOUT`: `coupon-service` is slow, so `payment-service` returns HTTP 504.
3. `ORDER_429_RATE_LIMIT`: `order-service` returns HTTP 429 under reservation load.

## Start

```bash
cd demo/payment_system
docker compose up --build
```

Generate traffic:

```bash
python scripts/generate_traffic.py --fault PAYMENT_503_AFTER_DEPLOY --requests 60
```

## Connect RunbookHermes to this demo

From the repository root:

```bash
export OBS_BACKEND=real
export DEPLOY_BACKEND=demo_file
export TRACE_BACKEND=jaeger
export TRACE_PROVIDER_KIND=jaeger
export ROLLBACK_BACKEND_KIND=demo_file
export RUNBOOK_CONTROLLED_EXECUTION_ENABLED=true
export PROMETHEUS_BASE_URL=http://127.0.0.1:9090
export LOKI_BASE_URL=http://127.0.0.1:3100
export TRACE_BASE_URL=http://127.0.0.1:16686
export DEMO_DEPLOY_STATE_FILE=data/payment_demo/deployments.json
export DEMO_VERSION_FILE=data/payment_demo/runtime/payment-service-version.txt
```

Then run RunbookHermes API and create an incident.
