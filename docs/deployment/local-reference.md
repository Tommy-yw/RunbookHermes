# Local Reference Deployment

This document explains how to run RunbookHermes locally with the Web Console, incident workflow, monitoring dashboard, and the local reference payment environment.

The local reference deployment is designed for:

* validating the RunbookHermes architecture;
* demonstrating the full incident-response workflow;
* testing Prometheus / Loki / Jaeger integration locally;
* recording GitHub screenshots and demo videos;
* understanding how the production integration path works before connecting real company systems.

It is not a separate product from RunbookHermes. It is a local reference environment included inside the merged RunbookHermes repository.

---

## 1. Deployment Model

RunbookHermes is a merged codebase:

```text
Hermes Agent upstream source
+ RunbookHermes AIOps extension layer
= RunbookHermes
```

For local reference deployment, you usually run two or three processes:

```text
Process 1: RunbookHermes Web/API
Process 2: local payment reference environment, optional but recommended
Process 3: traffic generator or API commands, optional
```

You do **not** deploy official Hermes Agent separately first and then deploy RunbookHermes as a second unrelated system.

You run entry points from the merged RunbookHermes repository.

---

## 2. Repository Path

This document assumes your local repository path is:

```text
E:\agent\run\runbookhermes-work\hermes-agent-2026.4.23
```

If your actual path is different, replace the path in the commands below.

---

## 3. Python Environment

Recommended Python version:

```text
Python 3.11
```

On Windows with Anaconda Prompt:

```bat
conda create -n runbookhermes311 python=3.11 pip -y
conda activate runbookhermes311
```

Enter the repository root:

```bat
cd /d E:\agent\run\runbookhermes-work\hermes-agent-2026.4.23
```

Set `PYTHONPATH`:

```bat
set PYTHONPATH=.
```

Install the project dependencies:

```bat
python -m pip install -e ".[web]"
```

If you only want to inspect the Web Console and API, this is enough to start.

---

## 4. Mode A: Run Web/API Only

Use this mode when you want to open the Web Console, create sample incidents, inspect approvals, view the monitoring page with mock fallback data, and test API routes.

Start RunbookHermes Web/API:

```bat
conda activate runbookhermes311
cd /d E:\agent\run\runbookhermes-work\hermes-agent-2026.4.23
set PYTHONPATH=.
python -m uvicorn apps.runbook_api.app.main:app --host 127.0.0.1 --port 8000
```

Keep this terminal open.

Open the Web Console:

```text
http://127.0.0.1:8000/web/index.html
```

Useful pages:

```text
http://127.0.0.1:8000/web/index.html
http://127.0.0.1:8000/web/monitoring.html
http://127.0.0.1:8000/web/incidents.html
http://127.0.0.1:8000/web/approvals.html
http://127.0.0.1:8000/web/digests.html
http://127.0.0.1:8000/web/settings.html
http://127.0.0.1:8000/docs
```

If the browser shows an old cached page, press:

```text
Ctrl + F5
```

---

## 5. Create Sample Incidents Without Docker

Open a second Anaconda Prompt.

```bat
conda activate runbookhermes311
cd /d E:\agent\run\runbookhermes-work\hermes-agent-2026.4.23
set PYTHONPATH=.
```

Check available local scenarios:

```bat
curl http://127.0.0.1:8000/demo/scenarios
```

Create a payment-service HTTP 503 incident:

```bat
curl -X POST http://127.0.0.1:8000/demo/scenarios/payment_503_spike/incident
```

Create a coupon-service HTTP 504 incident:

```bat
curl -X POST http://127.0.0.1:8000/demo/scenarios/coupon_504_timeout/incident
```

Create an order-service HTTP 429 incident:

```bat
curl -X POST http://127.0.0.1:8000/demo/scenarios/order_429_rate_limit/incident
```

If a scenario ID is different in your local build, use the IDs returned by:

```bat
curl http://127.0.0.1:8000/demo/scenarios
```

Then open:

```text
http://127.0.0.1:8000/web/incidents.html
```

Click an incident ID, for example:

```text
inc_xxxxxx
```

The detail page should show:

* executive summary;
* evidence cards;
* root-cause hypothesis;
* optional model-assisted summary section;
* action plan;
* approval record;
* checkpoint record;
* event timeline;
* generated runbook skill;
* raw incident JSON.

---

## 6. Mode B: Local Reference Payment Environment

Use this mode when you want RunbookHermes to connect to real local services instead of only mock fallback data.

This mode requires Docker Desktop.

Start Docker Desktop first.

Then open a terminal and run:

```bat
conda activate runbookhermes311
cd /d E:\agent\run\runbookhermes-work\hermes-agent-2026.4.23\demo\payment_system
docker compose up --build
```

This starts the local reference payment environment:

```text
payment-service
order-service
coupon-service
mysql
redis
prometheus
loki
promtail
jaeger
grafana
```

Common local URLs:

```text
Prometheus: http://127.0.0.1:9090
Loki:       http://127.0.0.1:3100
Jaeger:     http://127.0.0.1:16686
Grafana:    http://127.0.0.1:3000
```

Keep this Docker terminal open.

---

## 7. Start RunbookHermes Against Local Observability

Open another Anaconda Prompt.

```bat
conda activate runbookhermes311
cd /d E:\agent\run\runbookhermes-work\hermes-agent-2026.4.23
set PYTHONPATH=.
```

Configure local real backends:

```bat
set OBS_BACKEND=real
set DEPLOY_BACKEND=demo_file
set TRACE_BACKEND=jaeger
set TRACE_PROVIDER_KIND=jaeger
set ROLLBACK_BACKEND_KIND=demo_file
set RUNBOOK_CONTROLLED_EXECUTION_ENABLED=true

set PROMETHEUS_BASE_URL=http://127.0.0.1:9090
set LOKI_BASE_URL=http://127.0.0.1:3100
set TRACE_BASE_URL=http://127.0.0.1:16686

set DEMO_DEPLOY_STATE_FILE=data/payment_demo/deployments.json
set DEMO_VERSION_FILE=data/payment_demo/runtime/payment-service-version.txt
```

Start the Web/API service:

```bat
python -m uvicorn apps.runbook_api.app.main:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/web/monitoring.html
```

The Monitoring page should show payment, coupon, and order service signals.

---

## 8. Generate Local Fault Traffic

Open another Anaconda Prompt.

```bat
conda activate runbookhermes311
cd /d E:\agent\run\runbookhermes-work\hermes-agent-2026.4.23\demo\payment_system
```

Generate payment-service HTTP 503 fault traffic:

```bat
python scripts\generate_traffic.py --fault PAYMENT_503_AFTER_DEPLOY --requests 60
```

Generate coupon-service HTTP 504 fault traffic:

```bat
python scripts\generate_traffic.py --fault COUPON_504_TIMEOUT --requests 40
```

Generate order-service HTTP 429 fault traffic:

```bat
python scripts\generate_traffic.py --fault ORDER_429_RATE_LIMIT --requests 40
```

Then refresh:

```text
http://127.0.0.1:8000/web/monitoring.html
```

You should see changing error-rate, latency, QPS, log, and trace signals.

---

## 9. Suggested Local Demo Flow

A clean local demonstration flow is:

### Step 1: Open Overview

```text
http://127.0.0.1:8000/web/index.html
```

Explain:

```text
RunbookHermes is a Hermes-native AIOps control plane.
It tracks incidents, approvals, generated skills, critical services, and monitoring signals.
```

### Step 2: Open Monitoring

```text
http://127.0.0.1:8000/web/monitoring.html
```

Explain:

```text
The agent can observe service health through metrics, logs, traces, and deploy state.
This is the evidence source for incident analysis.
```

### Step 3: Create Incident

Open:

```text
http://127.0.0.1:8000/web/incidents.html
```

Create one of the local scenarios:

* payment-service HTTP 503;
* coupon-service HTTP 504;
* order-service HTTP 429.

Explain:

```text
Different entry sources such as Web, Alertmanager, Feishu, WeCom, or API are normalized into RunbookHermes incidents.
```

### Step 4: Open Incident Detail

Click the incident ID.

Show:

* evidence;
* root cause;
* action plan;
* timeline;
* generated skill;
* raw JSON.

Explain:

```text
RunbookHermes does not ask the model to guess from nothing.
It builds an evidence stack first, then explains root cause and proposes a safe action.
```

### Step 5: Open Approvals

```text
http://127.0.0.1:8000/web/approvals.html
```

Explain:

```text
Risky actions are gated by approval and checkpoint.
This prevents the agent from blindly mutating production systems.
```

### Step 6: Verify Recovery

On the incident detail page, click:

```text
Verify recovery
```

Explain:

```text
A remediation is not complete until metrics, logs, or traces indicate recovery.
```

### Step 7: Open Digests and Skills

```text
http://127.0.0.1:8000/web/digests.html
```

Explain:

```text
RunbookHermes turns incident experience into reusable runbook skills.
This is the learning loop inherited from the Hermes Agent skill concept.
```

---

## 10. Optional: Model-Assisted Summary

RunbookHermes can use an OpenAI-compatible model endpoint for model-assisted summaries.

Example:

```bat
set RUNBOOK_MODEL_ENABLED=true
set RUNBOOK_MODEL_BASE_URL=https://your-openai-compatible-endpoint/v1
set RUNBOOK_MODEL_API_KEY=your_api_key
set RUNBOOK_MODEL_NAME=your_model_name
set RUNBOOK_MODEL_TEMPERATURE=0
```

Restart RunbookHermes Web/API after setting these variables.

Then open an incident detail page and use:

```text
Generate summary
```

The model-assisted summary is optional. The rest of the evidence, root cause, action, approval, checkpoint, and timeline workflow still works without it.

---

## 11. Optional: Hermes-Native Chat Path

The Web Console is the operator control plane. It is not primarily a chat UI.

For Hermes-native agent conversation, use the RunbookHermes profile:

```bash
hermes --profile runbook-hermes
```

On Windows, the upstream Hermes Agent project may be more reliable under WSL2 for full CLI / terminal-agent usage. The RunbookHermes Web/API can run under Windows Anaconda as shown above.

Example prompt:

```text
payment-service HTTP 503 is rising after release. Please collect evidence first, identify the most likely root cause, and propose a safe remediation plan with approval requirements.
```

---

## 12. Validation Scripts

From the repository root:

```bat
conda activate runbookhermes311
cd /d E:\agent\run\runbookhermes-work\hermes-agent-2026.4.23
set PYTHONPATH=.
```

Run:

```bat
python -S scripts/runbook_validate.py
python -S scripts/runbook_gateway_smoke.py
python -S scripts/runbook_no_legacy_imports.py
python -S scripts/runbook_monitoring_validate.py
python -S scripts/runbook_stage8_validate.py
```

These scripts validate key RunbookHermes integration points.

---

## 13. Troubleshooting

### Browser shows old UI

Press:

```text
Ctrl + F5
```

This forces the browser to reload cached frontend files.

### `monitoring.html` returns 404

Check that the file exists:

```bat
dir web\static\monitoring.html
```

If it does not exist, your latest UI/monitoring overlay was not merged into the current repository.

### Anaconda Prompt does not enter the E drive

Use:

```bat
cd /d E:\agent\run\runbookhermes-work\hermes-agent-2026.4.23
```

Not:

```bat
cd E:\agent\run\runbookhermes-work\hermes-agent-2026.4.23
```

In CMD / Anaconda Prompt, `cd /d` is required when switching drives.

### `python` is not recognized

Use Anaconda Prompt and activate the environment:

```bat
conda activate runbookhermes311
python --version
```

### Port 8000 is already in use

Use another port:

```bat
python -m uvicorn apps.runbook_api.app.main:app --host 127.0.0.1 --port 8001
```

Open:

```text
http://127.0.0.1:8001/web/index.html
```

### Docker services do not start

Make sure Docker Desktop is running, then retry:

```bat
cd /d E:\agent\run\runbookhermes-work\hermes-agent-2026.4.23\demo\payment_system
docker compose up --build
```

---

## 14. What This Local Reference Deployment Proves

The local reference environment proves that RunbookHermes can connect the following pieces into one incident workflow:

```text
service signal
→ metrics / logs / traces / deploy evidence
→ incident record
→ evidence stack
→ root-cause hypothesis
→ action plan
→ approval
→ checkpoint
→ controlled execution boundary
→ recovery verification
→ timeline
→ generated runbook skill
```

This is the same architectural path used for production integration. In production, you replace local reference systems with real company systems.

---

## 15. Next Step

After the local reference deployment is working, continue with:

```text
docs/deployment/production.md
```

That document explains how to adapt the local reference architecture to a production-oriented deployment with real observability, model, messaging, storage, and execution systems.
