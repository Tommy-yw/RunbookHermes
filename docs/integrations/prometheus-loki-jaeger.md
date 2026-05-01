# Prometheus / Loki / Jaeger Integration

This document explains how RunbookHermes connects to real observability systems: Prometheus for metrics, Loki for logs, and Jaeger or Tempo for traces.

RunbookHermes uses observability data as the evidence foundation for incident analysis. The model should not guess a root cause without evidence. Metrics, logs, traces, and deployment records should be collected first, compressed into EvidenceStack, and then used for root-cause explanation, action planning, approval, and recovery verification.

---

## 1. Integration Goal

The goal of this integration is to make RunbookHermes work against real operational signals:

```text
Prometheus metrics
+ Loki logs
+ Jaeger / Tempo traces
+ deploy history
→ evidence stack
→ root-cause hypothesis
→ action plan
→ approval
→ recovery verification
```

In production, RunbookHermes should answer questions such as:

```text
Did payment-service HTTP 503 increase?
Did p95 latency increase?
Are logs showing connection pool exhaustion?
Do traces show slow downstream calls to mysql-payment or coupon-service?
Was there a recent deployment?
Did the error rate recover after rollback?
```

---

## 2. Files Involved

RunbookHermes observability integration lives mainly in:

```text
integrations/observability/prometheus_backend.py
integrations/observability/loki_backend.py
integrations/observability/trace_backend.py
integrations/observability/deploy_backend.py
runbook_hermes/backends.py
runbook_hermes/tools.py
runbook_hermes/monitoring.py
plugins/runbook-hermes/__init__.py
```

Web/API display is handled by:

```text
apps/runbook_api/app/main.py
web/static/monitoring.html
web/static/incident.html
```

Local reference data is stored in:

```text
data/runbook_mock/
data/payment_demo/
demo/payment_system/
```

---

## 3. Backend Modes

RunbookHermes supports two important modes:

```text
mock mode
real mode
```

### 3.1 Mock Mode

Mock mode uses local files and is useful for:

* opening the Web Console quickly;
* creating sample incidents;
* testing UI and incident workflow;
* running without Docker;
* running without production access.

Example:

```bat
set OBS_BACKEND=mock
set DEPLOY_BACKEND=mock
set TRACE_BACKEND=mock
```

If these variables are not set, RunbookHermes may fall back to mock behavior depending on the implementation defaults.

### 3.2 Real Mode

Real mode connects to Prometheus, Loki, and Jaeger / Tempo.

Example:

```bat
set OBS_BACKEND=real
set PROMETHEUS_BASE_URL=http://127.0.0.1:9090
set LOKI_BASE_URL=http://127.0.0.1:3100
set TRACE_BACKEND=jaeger
set TRACE_PROVIDER_KIND=jaeger
set TRACE_BASE_URL=http://127.0.0.1:16686
```

In production, these should point to company systems:

```bash
OBS_BACKEND=real
PROMETHEUS_BASE_URL=https://prometheus.example.com
LOKI_BASE_URL=https://loki.example.com
TRACE_BACKEND=jaeger
TRACE_PROVIDER_KIND=jaeger
TRACE_BASE_URL=https://jaeger.example.com
```

---

## 4. Environment Variables

### 4.1 Metrics

```bash
OBS_BACKEND=real
PROMETHEUS_BASE_URL=https://prometheus.example.com
PROMETHEUS_AUTH_TOKEN=
PROMETHEUS_TIMEOUT_SECONDS=5
```

### 4.2 Logs

```bash
LOKI_BASE_URL=https://loki.example.com
LOKI_AUTH_TOKEN=
LOKI_TIMEOUT_SECONDS=5
LOKI_MAX_LINES=100
```

### 4.3 Traces

```bash
TRACE_BACKEND=jaeger
TRACE_PROVIDER_KIND=jaeger
TRACE_BASE_URL=https://jaeger.example.com
TRACE_AUTH_TOKEN=
TRACE_TIMEOUT_SECONDS=5
TRACE_MAX_RESULTS=20
```

### 4.4 Deploy History

```bash
DEPLOY_BACKEND=real
DEPLOY_API_BASE_URL=https://deploy.example.com
DEPLOY_API_TOKEN=
```

For local reference deployment:

```bat
set DEPLOY_BACKEND=demo_file
set DEMO_DEPLOY_STATE_FILE=data/payment_demo/deployments.json
```

---

## 5. Prometheus Integration

Prometheus is used for metrics evidence.

RunbookHermes tools:

```text
prom_query
prom_top_anomalies
```

Typical evidence from Prometheus:

```text
HTTP 503 rate
HTTP 504 rate
HTTP 429 rate
QPS
p95 latency
error ratio
service availability
```

### 5.1 Prometheus HTTP APIs

RunbookHermes should use:

```text
GET /api/v1/query
GET /api/v1/query_range
```

### 5.2 Example Queries

The exact query names depend on your metrics schema.

Local reference service may expose metrics similar to:

```text
http_requests_total{service="payment-service", status="503"}
http_request_duration_seconds_bucket{service="payment-service"}
```

Example HTTP 503 rate query:

```promql
sum(rate(http_requests_total{service="payment-service",status="503"}[5m]))
```

Example QPS query:

```promql
sum(rate(http_requests_total{service="payment-service"}[5m]))
```

Example p95 latency query:

```promql
histogram_quantile(
  0.95,
  sum(rate(http_request_duration_seconds_bucket{service="payment-service"}[5m])) by (le)
)
```

### 5.3 Production Query Mapping

In production, your company metrics may use different labels:

```text
app
service
job
namespace
cluster
env
status
code
http_status
route
```

Before connecting production Prometheus, map your real labels to RunbookHermes queries.

Recommended mapping file or configuration:

```text
service label: service or app
status label: status or code
namespace label: namespace
environment label: env or environment
```

### 5.4 Prometheus Safety Limits

Production query safety is important.

Recommended limits:

```text
query timeout
max query range
service allowlist
namespace allowlist
label allowlist
max returned series
```

RunbookHermes should avoid unbounded queries such as:

```promql
{__name__=~".*"}
```

or wide-range queries across all services.

---

## 6. Loki Integration

Loki is used for log evidence.

RunbookHermes tool:

```text
loki_query
```

Typical evidence from Loki:

```text
connection pool exhausted
upstream timeout
rate limit exceeded
payment dependency timeout
database connection timeout
panic / exception spikes
```

### 6.1 Loki HTTP APIs

RunbookHermes should use:

```text
GET /loki/api/v1/query_range
```

### 6.2 Example Queries

Example payment-service connection pool query:

```logql
{service="payment-service"} |= "connection pool exhausted"
```

Example coupon timeout query:

```logql
{service="coupon-service"} |= "timeout"
```

Example order rate-limit query:

```logql
{service="order-service"} |= "rate limit"
```

### 6.3 Log Evidence Compression

Raw logs can be huge. RunbookHermes should not send all raw logs to the model.

Recommended log evidence summary:

```text
evidence_id: ev_log_connection_pool
source: loki
service: payment-service
pattern: connection pool exhausted
count: 238
sample_lines: 3 to 5 redacted lines
time_range: last 10 minutes
```

### 6.4 Production Log Safety

Before connecting production Loki:

* redact secrets;
* avoid full raw request bodies;
* limit returned lines;
* restrict service and namespace labels;
* restrict time range;
* avoid sending sensitive logs to external models;
* preserve evidence IDs and summaries instead of raw dumps.

---

## 7. Jaeger / Tempo Trace Integration

Traces are used to understand call-chain behavior.

RunbookHermes tool:

```text
trace_search
```

Typical trace evidence:

```text
payment-service → mysql-payment latency increase
payment-service → coupon-service timeout
order-service rate-limit dependency impact
slow downstream calls
error spans
increased p95 duration
```

### 7.1 Jaeger API

For Jaeger, RunbookHermes can use:

```text
GET /api/traces?service=payment-service
```

Additional filters may include:

```text
lookback
tags
minDuration
maxDuration
operation
limit
```

### 7.2 Tempo API

If using Tempo, adapt `trace_backend.py` to the query API used by your Tempo deployment.

Common production choices:

```text
Jaeger query API
Tempo query frontend
OpenTelemetry collector + trace backend
```

### 7.3 Trace Evidence Summary

Trace payloads can be large. RunbookHermes should summarize them.

Recommended summary:

```text
evidence_id: ev_trace_mysql_latency
source: jaeger
service: payment-service
downstream: mysql-payment
p95_ms: 1800
error_rate: 0.32
sample_trace_ids: [trace_id_1, trace_id_2]
time_range: last 10 minutes
```

### 7.4 Production Trace Safety

Before connecting production traces:

* do not expose sensitive span attributes;
* redact user identifiers;
* restrict service allowlist;
* limit trace count;
* avoid full trace dumps into model prompts;
* keep sample trace IDs for audit and manual inspection.

---

## 8. Deploy History Integration

Metrics, logs, and traces are stronger when correlated with deployment records.

RunbookHermes uses deploy evidence to answer:

```text
Was this service recently released?
What version changed?
Who deployed it?
What was the previous version?
Is rollback possible?
```

Local reference deployment uses:

```text
data/payment_demo/deployments.json
```

Production options:

```text
internal release platform
Argo CD
Argo Rollouts
Kubernetes Deployment revision
GitHub Actions deployment records
GitLab CI deployment records
custom deploy API
```

Recommended deploy evidence shape:

```json
{
  "service": "payment-service",
  "environment": "prod",
  "current_version": "v2.3.1",
  "previous_version": "v2.3.0",
  "deployed_at": "2026-04-29T10:00:00Z",
  "deployed_by": "release-bot",
  "change_id": "deploy-123",
  "rollback_supported": true
}
```

---

## 9. Evidence Flow in RunbookHermes

A typical evidence flow:

```text
Alertmanager alert
→ incident created
→ prom_top_anomalies
→ prom_query
→ loki_query
→ trace_search
→ recent_deploys
→ EvidenceStack
→ root-cause hypothesis
→ action policy
→ approval
→ checkpoint
→ controlled execution
→ verify_recovery
```

Example payment-service HTTP 503 incident:

```text
Prometheus:
  HTTP 503 rate increased

Loki:
  connection pool exhausted repeated

Jaeger:
  payment-service → mysql-payment latency increased

Deploy:
  payment-service v2.3.1 released recently

Hypothesis:
  v2.3.1 introduced database connection pool regression

Action:
  rollback payment-service to v2.3.0

Safety:
  approval + checkpoint + dry-run required
```

---

## 10. Monitoring Dashboard Data

The Web Console Monitoring page uses:

```text
GET /monitoring/live
GET /monitoring/services/{service}
```

The page displays:

* service health matrix;
* HTTP 503 / 504 / 429 signals;
* QPS;
* p95 latency;
* log signals;
* trace signals;
* deploy state;
* topology;
* backend mode.

If `OBS_BACKEND=mock`, it uses local fallback data.

If `OBS_BACKEND=real`, it queries configured observability backends.

---

## 11. Local Reference Setup

Start local reference services:

```bat
cd /d E:\agent\run\runbookhermes-work\hermes-agent-2026.4.23\demo\payment_system
docker compose up --build
```

Start RunbookHermes with real local observability:

```bat
cd /d E:\agent\run\runbookhermes-work\hermes-agent-2026.4.23
set PYTHONPATH=.

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

python -m uvicorn apps.runbook_api.app.main:app --host 127.0.0.1 --port 8000
```

Generate traffic:

```bat
cd /d E:\agent\run\runbookhermes-work\hermes-agent-2026.4.23\demo\payment_system
python scripts\generate_traffic.py --fault PAYMENT_503_AFTER_DEPLOY --requests 60
python scripts\generate_traffic.py --fault COUPON_504_TIMEOUT --requests 40
python scripts\generate_traffic.py --fault ORDER_429_RATE_LIMIT --requests 40
```

Open:

```text
http://127.0.0.1:8000/web/monitoring.html
```

---

## 12. Production Setup Example

Example production variables:

```bash
OBS_BACKEND=real
PROMETHEUS_BASE_URL=https://prometheus.company.internal
PROMETHEUS_AUTH_TOKEN=${PROMETHEUS_TOKEN}

LOKI_BASE_URL=https://loki.company.internal
LOKI_AUTH_TOKEN=${LOKI_TOKEN}

TRACE_BACKEND=jaeger
TRACE_PROVIDER_KIND=jaeger
TRACE_BASE_URL=https://jaeger.company.internal
TRACE_AUTH_TOKEN=${TRACE_TOKEN}

DEPLOY_BACKEND=real
DEPLOY_API_BASE_URL=https://deploy.company.internal
DEPLOY_API_TOKEN=${DEPLOY_TOKEN}
```

Recommended production rules:

```text
read-only observability access
query allowlist
service allowlist
namespace allowlist
short query time ranges by default
summarize before model input
record evidence IDs
store audit timeline
fail gracefully if one backend is unavailable
```

---

## 13. Recovery Verification

After a remediation action, RunbookHermes should verify recovery.

Recovery verification may check:

```text
HTTP 503 rate decreased
HTTP 504 rate decreased
HTTP 429 rate decreased
p95 latency normalized
log error pattern decreased
trace errors decreased
new version is active
service health is stable
```

This should be done through the same observability adapters.

Example recovery check:

```text
Before rollback:
  HTTP 503 rate = 18%
  p95 latency = 1800ms

After rollback:
  HTTP 503 rate = 0.3%
  p95 latency = 130ms

Result:
  recovery verified
```

---

## 14. Failure Handling

Observability systems may fail.

RunbookHermes should handle partial failure:

```text
Prometheus unavailable
Loki unavailable
Trace backend unavailable
Deploy API unavailable
```

Recommended behavior:

* record backend failure in timeline;
* continue with available evidence;
* lower confidence if evidence is incomplete;
* do not claim root cause certainty without evidence;
* show backend status in Settings / Monitoring page;
* allow operator to retry evidence collection.

---

## 15. Security and Privacy

Observability data may contain sensitive information.

Do not send these to external model providers by default:

* secrets;
* tokens;
* raw customer data;
* payment data;
* full request bodies;
* full trace payloads;
* high-volume raw logs.

Recommended protections:

* redact logs;
* limit sample lines;
* summarize evidence;
* use evidence IDs;
* use internal model gateway for sensitive data;
* audit model requests;
* restrict access to raw evidence.

---

## 16. Query Hardening Checklist

Before using production observability:

* [ ] Prometheus base URL configured.
* [ ] Loki base URL configured.
* [ ] Jaeger / Tempo base URL configured.
* [ ] Auth tokens stored in secret manager.
* [ ] Query timeout configured.
* [ ] Query time range limit configured.
* [ ] Max log lines configured.
* [ ] Max trace results configured.
* [ ] Service allowlist configured.
* [ ] Namespace allowlist configured.
* [ ] Redaction enabled for logs.
* [ ] Evidence summaries used for model input.
* [ ] Backend errors are recorded in timeline.
* [ ] Monitoring page shows backend status.

---

## 17. Troubleshooting

### Monitoring page shows mock data

Check:

```bat
set OBS_BACKEND
set PROMETHEUS_BASE_URL
set LOKI_BASE_URL
set TRACE_BASE_URL
```

Restart RunbookHermes after setting environment variables.

### Prometheus query returns empty result

Check:

* service label name;
* status label name;
* metric name;
* query time range;
* whether traffic was generated;
* whether Prometheus is scraping the service;
* whether the target is healthy in Prometheus.

Open:

```text
http://127.0.0.1:9090/targets
```

for local reference deployment.

### Loki query returns no logs

Check:

* Promtail is running;
* log file path exists;
* Loki labels match the query;
* time range is correct;
* logs were generated after Loki started.

### Jaeger has no traces

Check:

* Jaeger is running;
* service exports spans;
* OTLP endpoint is configured;
* request traffic was generated;
* service name matches query;
* trace sampling is enabled.

Open:

```text
http://127.0.0.1:16686
```

for local reference deployment.

### Evidence is too noisy

Reduce:

```text
log line count
trace count
metric range
sample payload size
```

Then rely on EvidenceStack summaries.

---

## 18. Recommended Production Rollout

### Stage 1: Read-Only Observability

Connect real Prometheus, Loki, and Jaeger / Tempo with read-only credentials.

Do not enable execution.

Goal:

```text
Prove RunbookHermes can collect real evidence and build useful incident summaries.
```

### Stage 2: Deploy Correlation

Connect deploy history.

Goal:

```text
Correlate incidents with recent changes.
```

### Stage 3: Recovery Verification

Use real metrics and logs to verify recovery after human-led remediation.

Goal:

```text
Prove RunbookHermes can close the incident loop.
```

### Stage 4: Controlled Execution Dry-Run

Connect executor dry-run only.

Goal:

```text
Validate action safety before execution.
```

### Stage 5: Controlled Execution with Approval

Enable limited execution only after:

```text
approval
checkpoint
dry-run
allowlist
audit
recovery verification
```

---

## 19. One-Sentence Summary

Prometheus, Loki, and Jaeger provide the evidence layer for RunbookHermes: metrics show what changed, logs explain what failed, traces show where latency or errors occurred, and EvidenceStack turns these signals into a compact, auditable context for model-assisted incident response.
