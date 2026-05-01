# RunbookHermes Stages 5-7

This overlay adds a small but real payment demo system and replaces the previous pure mock boundary with real observability adapter implementations.

## Stage 5: payment demo system

The demo system lives in `demo/payment_system` and contains:

- `payment-service`
- `order-service`
- `coupon-service`
- MySQL
- Redis
- Prometheus
- Loki
- Promtail
- Jaeger
- Grafana

The default incident is specific: `payment-service` version `v2.3.1` returns HTTP 503 after deployment because of a simulated DB pool regression.

Two additional faults are included:

1. `COUPON_504_TIMEOUT`: coupon-service delay causes payment-service HTTP 504.
2. `ORDER_429_RATE_LIMIT`: order-service rate limiting causes HTTP 429.

## Stage 6: real observability adapters

The following adapters now contain real HTTP calls:

- `integrations/observability/prometheus_backend.py`
- `integrations/observability/loki_backend.py`
- `integrations/observability/trace_backend.py`
- `integrations/observability/deploy_backend.py`

Set these variables to use the demo stack:

```bash
export OBS_BACKEND=real
export DEPLOY_BACKEND=demo_file
export TRACE_BACKEND=jaeger
export TRACE_PROVIDER_KIND=jaeger
export PROMETHEUS_BASE_URL=http://127.0.0.1:9090
export LOKI_BASE_URL=http://127.0.0.1:3100
export TRACE_BASE_URL=http://127.0.0.1:16686
```

## Stage 7: controlled execution

`rollback_canary(dry_run=false)` now follows this path:

1. create checkpoint
2. create approval
3. wait for approval
4. write demo version file from `v2.3.1` to `v2.3.0`
5. update `data/payment_demo/deployments.json`
6. run recovery verification

This is still scoped to the local payment demo. It does not touch production infrastructure.
