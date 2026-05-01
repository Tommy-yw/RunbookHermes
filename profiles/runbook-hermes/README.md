# RunbookHermes Profile

This profile turns Hermes into an incident/runbook-oriented agent.

## Model

Copy `.env.example` to your Hermes profile env and set a cheap OpenAI-compatible key:

```bash
cp profiles/runbook-hermes/.env.example ~/.hermes/profiles/runbook-hermes/.env
```

Set:

```env
RUNBOOK_MODEL_ENABLED=true
RUNBOOK_MODEL_API_KEY=your_key
RUNBOOK_MODEL_BASE_URL=https://openrouter.ai/api/v1
RUNBOOK_MODEL_NAME=your-cheap-model
```

Hermes itself still owns the main inference runtime. The Runbook API helper only uses these values for incident/card summaries.

## Web/API

After applying the overlay and installing the optional web dependencies:

```bash
python -m pip install -e ".[web]"
python -m uvicorn apps.runbook_api.app.main:app --host 127.0.0.1 --port 8000
```

Open:

- http://127.0.0.1:8000/docs
- http://127.0.0.1:8000/web/incidents.html
- http://127.0.0.1:8000/web/approvals.html
- http://127.0.0.1:8000/web/digests.html
