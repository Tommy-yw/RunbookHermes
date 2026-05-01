# Real observability and controlled demo rollback

## Prometheus

`prom_query` and `prom_top_anomalies` call:

- `/api/v1/query`
- `/api/v1/query_range` when needed later

The first implemented anomaly set checks HTTP 503, HTTP 504, HTTP 429 and p95 latency.

## Loki

`loki_query` calls `/loki/api/v1/query_range` and expects logs to carry a `service` label. The local demo uses Promtail file scraping with labels for `payment-service`, `order-service` and `coupon-service`.

## Trace

The local demo uses Jaeger first. `trace_search` calls `/api/traces?service=...`.

## Deploy and rollback

`DEPLOY_BACKEND=demo_file` reads `data/payment_demo/deployments.json`.

`ROLLBACK_BACKEND_KIND=demo_file` writes `data/payment_demo/runtime/payment-service-version.txt` after approval. This is a real state change for the local demo system, but it is not production rollback.
