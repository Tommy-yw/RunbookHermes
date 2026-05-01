# RunbookHermes Stage 2-4 Implementation Notes

This overlay extends the Hermes-native RunbookHermes baseline with three practical layers.

## Stage 2: Restore the Web/API console

The old week7 RunbookHermes had useful product-facing pages. This overlay restores a lightweight version without reusing the old self-written runtime as the main brain.

New files:

- `apps/runbook_api/app/main.py`
- `web/static/incidents.html`
- `web/static/incident.html`
- `web/static/approvals.html`
- `web/static/digests.html`

Run:

```bash
python -m pip install -e ".[web]"
python -m uvicorn apps.runbook_api.app.main:app --host 127.0.0.1 --port 8000
```

Open:

- `/docs`
- `/web/incidents.html`
- `/web/approvals.html`
- `/web/digests.html`

## Stage 3: Cheap model interface

Hermes remains responsible for the real agent/provider runtime. The added `runbook_hermes/model_client.py` is only a thin OpenAI-compatible helper for card summaries and web/API incident summaries.

Configure:

```env
RUNBOOK_MODEL_ENABLED=true
RUNBOOK_MODEL_BASE_URL=https://openrouter.ai/api/v1
RUNBOOK_MODEL_API_KEY=your_key
RUNBOOK_MODEL_NAME=your-cheap-model
RUNBOOK_MODEL_TEMPERATURE=0
```

Then use:

```text
GET /incidents/{incident_id}/model-summary
```

If the key is not configured, the API returns a deterministic disabled message.

## Stage 4: Feishu / WeCom interface shells

Feishu routes:

- `POST /gateway/feishu/events`
- `POST /gateway/feishu/card-callback`
- compatibility: `POST /gateway/feishu/webhook`

WeCom routes:

- `POST /gateway/wecom/events`
- `POST /gateway/wecom/card-callback`
- compatibility: `POST /gateway/wecom/webhook`

These routes normalize external payloads into RunbookHermes incident commands and approval decisions. They are intentionally not a full production Feishu/WeCom app yet. To productionize:

1. Create an app in Feishu or WeCom.
2. Configure callback URL to your deployed API route.
3. Fill the verification token / encrypt key / app secret environment variables.
4. Add real signature and decrypt handling if your app enables encryption.
5. Map the real platform event schema to the adapter functions.

## Current boundary

Still mock by default:

- Prometheus
- Loki
- Trace
- Deploy
- Rollback execution

The real adapter shells are kept under `integrations/observability/` and `runbook_hermes/backends.py`.
