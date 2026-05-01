# RunbookHermes final Web + monitoring upgrade

This patch upgrades the RunbookHermes Web console after the Stage 8 final overlay and fix patch.

## What changed

- Removed the old `Hermes-native runbook agent` hero badge from the Overview page.
- Renamed the Overview title to `AIOps 控制台`.
- Removed the long explanatory paragraph from the Overview hero.
- Simplified the sidebar brand so `RH` and `RunbookHermes` stay on one line.
- Added a new `Monitoring` navigation item.
- Added `/web/monitoring.html` for real-time multi-dimensional observability.
- Added `/monitoring/live` and `/monitoring/services/{service}` API endpoints.
- Added `runbook_hermes.monitoring` for service snapshots, time series, topology, logs, traces and deploy state.
- Added mock observability data for `coupon-service` and `order-service`, so the monitoring page shows payment, coupon and order dimensions even before real backends are configured.

## Monitoring scope

The monitoring page is designed to match the current RunbookHermes capabilities:

- HTTP 503, HTTP 504 and HTTP 429 error-rate visualization.
- p95 latency and QPS trend cards.
- payment-service, coupon-service and order-service health cards.
- service topology: payment -> order / coupon / mysql / redis.
- Loki-style log signals.
- Jaeger-style trace signals.
- demo deploy state.

## Real backend behavior

When environment variables are configured, the same UI reads from the real backend adapters:

- `OBS_BACKEND=real`
- `PROMETHEUS_BASE_URL=http://127.0.0.1:9090`
- `LOKI_BASE_URL=http://127.0.0.1:3100`
- `TRACE_BACKEND=jaeger`
- `TRACE_PROVIDER_KIND=jaeger`
- `TRACE_BASE_URL=http://127.0.0.1:16686`

When those are not configured, it uses the bundled mock data, which keeps the web console usable for local demonstration.

## Validation

Run:

```bash
PYTHONPATH=. python -S scripts/runbook_monitoring_validate.py
PYTHONPATH=. python -S scripts/runbook_stage8_validate.py
```

If FastAPI is installed, the validation also checks `/monitoring/live`, `/monitoring/services/payment-service` and `/web/monitoring.html`.
