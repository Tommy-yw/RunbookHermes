# RunbookHermes Final Interface Map

## Model

Environment:

```env
RUNBOOK_MODEL_ENABLED=true
RUNBOOK_MODEL_BASE_URL=https://your-openai-compatible-endpoint/v1
RUNBOOK_MODEL_API_KEY=...
RUNBOOK_MODEL_NAME=your-cheap-model
```

API:

```text
GET /incidents/{incident_id}/model-summary
```

## Web/API

```text
GET  /
GET  /health
GET  /runtime/status
GET  /dashboard/summary
GET  /demo/scenarios
POST /demo/scenarios/{scenario_id}/incident
GET  /incidents
POST /incidents
GET  /incidents/{incident_id}
GET  /incidents/{incident_id}/events
GET  /approvals
POST /approvals/{approval_id}/decision
GET  /skills
GET  /skills/{skill_id}/download
POST /incidents/{incident_id}/verify-recovery
```

## Feishu/Lark

Routes:

```text
POST /gateway/feishu/events
POST /gateway/feishu/card-callback
POST /gateway/feishu/webhook
```

Environment:

```env
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_VERIFICATION_TOKEN=
FEISHU_ENCRYPT_KEY=
FEISHU_CALLBACK_BASE_URL=
FEISHU_BOT_WEBHOOK_URL=
FEISHU_BOT_SECRET=
```

## WeCom

Routes:

```text
POST /gateway/wecom/events
POST /gateway/wecom/card-callback
POST /gateway/wecom/webhook
```

Environment:

```env
WECOM_CORP_ID=
WECOM_AGENT_ID=
WECOM_SECRET=
WECOM_TOKEN=
WECOM_ENCODING_AES_KEY=
WECOM_CALLBACK_BASE_URL=
```

## Observability

Environment:

```env
OBS_BACKEND=real
PROMETHEUS_BASE_URL=http://127.0.0.1:9090
LOKI_BASE_URL=http://127.0.0.1:3100
TRACE_BACKEND=jaeger
TRACE_PROVIDER_KIND=jaeger
TRACE_BASE_URL=http://127.0.0.1:16686
```

Tools:

```text
prom_query
prom_top_anomalies
loki_query
trace_search
recent_deploys
```

## Controlled execution

Environment:

```env
ROLLBACK_BACKEND_KIND=demo_file
RUNBOOK_CONTROLLED_EXECUTION_ENABLED=true
ACTION_EXECUTION_BACKEND=none
```

For production non-rollback actions:

```env
ACTION_EXECUTION_BACKEND=custom_http|kubernetes|argocd
ACTION_EXECUTION_API_BASE_URL=
ACTION_EXECUTION_API_TOKEN=
```

Production mutation remains disabled until you implement the specific adapter and allowlist.
