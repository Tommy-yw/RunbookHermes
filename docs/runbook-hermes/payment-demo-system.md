# Payment demo system

Start the system:

```bash
cd demo/payment_system
docker compose up --build
```

Generate the default HTTP 503 failure:

```bash
python scripts/generate_traffic.py --fault PAYMENT_503_AFTER_DEPLOY --requests 60
```

RunbookHermes should then be configured with:

```bash
export OBS_BACKEND=real
export DEPLOY_BACKEND=demo_file
export TRACE_BACKEND=jaeger
export ROLLBACK_BACKEND_KIND=demo_file
export RUNBOOK_CONTROLLED_EXECUTION_ENABLED=true
export PROMETHEUS_BASE_URL=http://127.0.0.1:9090
export LOKI_BASE_URL=http://127.0.0.1:3100
export TRACE_BASE_URL=http://127.0.0.1:16686
```

Create an incident using the API or Hermes profile, then approve the rollback. The demo version file at `data/payment_demo/runtime/payment-service-version.txt` will change from `v2.3.1` to `v2.3.0`.
