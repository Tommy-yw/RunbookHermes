# Production-Oriented Deployment

This document explains how to deploy RunbookHermes against real company systems.

RunbookHermes is built from the merged repository:

```text
Hermes Agent upstream source
+ RunbookHermes AIOps extension layer
= RunbookHermes
```

You do **not** deploy official Hermes Agent first and then deploy RunbookHermes as a separate unrelated system. You deploy the merged RunbookHermes repository and run the production entry points you need.

---

## 1. Production Goal

A production-oriented RunbookHermes deployment should support the following workflow:

```text
Alertmanager / Feishu / WeCom / API
→ RunbookHermes Gateway / API
→ Hermes Agent Runner with runbook-hermes profile
→ observability evidence collection
→ IncidentMemory + EvidenceStack
→ root-cause hypothesis
→ action planning
→ approval
→ checkpoint
→ dry-run
→ controlled execution
→ recovery verification
→ audit timeline
→ runbook skill generation
```

The production goal is not blind automation.

The production goal is:

```text
Evidence-driven incident response
+ model-assisted reasoning
+ human-in-the-loop approval
+ controlled remediation
+ auditable recovery verification
+ reusable runbook knowledge
```

---

## 2. High-Level Production Architecture

Recommended production architecture:

```text
                    ┌──────────────────────────────┐
                    │ Alertmanager / Feishu / WeCom │
                    │ Web Console / API Clients     │
                    └───────────────┬──────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────┐
│              RunbookHermes API / Gateway Service             │
│  Web Console, incident APIs, webhook intake, approvals,       │
│  monitoring API, settings, digest, Swagger                    │
└───────────────┬──────────────────────────────────────────────┘
                │
                ▼
┌──────────────────────────────────────────────────────────────┐
│              Hermes Agent Runner / runbook-hermes profile     │
│  Agent loop, provider routing, tools, memory, context, skills │
└───────┬───────────┬──────────────┬───────────────┬───────────┘
        │           │              │               │
        ▼           ▼              ▼               ▼
┌───────────┐ ┌──────────┐ ┌─────────────┐ ┌──────────────────┐
│ Model     │ │ Store    │ │ Observability│ │ Execution Gateway │
│ Provider  │ │ DB/Cache │ │ Prom/Loki/Tr │ │ K8s/Argo/Internal │
└───────────┘ └──────────┘ └─────────────┘ └──────────────────┘
        │           │              │               │
        ▼           ▼              ▼               ▼
  LLM summary  Incident state  Evidence      Controlled actions
               Audit timeline  Metrics       Verify recovery
               Memory/skills    Logs/Trace
```

Recommended production services:

```text
runbookhermes-api
runbookhermes-agent
incident-store
redis or queue backend
model-provider endpoint
observability backends
messaging callbacks
controlled execution backend
audit sink
```

---

## 3. Production Components

### 3.1 RunbookHermes API / Gateway Service

This service runs:

```bash
uvicorn apps.runbook_api.app.main:app --host 0.0.0.0 --port 8000
```

Responsibilities:

* serve Web Console;
* expose Swagger API;
* receive Alertmanager webhooks;
* receive Feishu / WeCom callbacks;
* create and read incidents;
* expose approvals;
* expose monitoring dashboard data;
* expose runtime/interface status;
* trigger recovery verification;
* coordinate with RunbookHermes domain logic.

Production hardening requirements:

* run behind HTTPS ingress;
* enable authentication;
* add RBAC for operators and approvers;
* restrict webhook routes by signature / token;
* restrict internal-only APIs;
* enable access logs;
* persist audit events;
* run with explicit environment configuration.

---

### 3.2 Hermes Agent Runner

This is the Hermes-native agent execution path using the RunbookHermes profile.

Expected command:

```bash
hermes --profile runbook-hermes
```

Responsibilities:

* run the Hermes agent loop;
* use configured model providers;
* load RunbookHermes tools;
* use `IncidentMemory`;
* use `EvidenceStack`;
* load runbook skills;
* support conversational incident triage;
* coordinate tool calls and structured reasoning.

This process may run as:

* a dedicated long-running agent process;
* a worker triggered by incidents;
* a gateway-connected service;
* a job runner for asynchronous tasks.

In production, the API and the Agent Runner can be separated so that the Web/API layer does not block on long-running reasoning or external tool calls.

---

### 3.3 Incident Store

The local reference build may use a JSON store such as:

```text
.runbook_hermes_store/
```

Production should replace this with a durable database:

```text
PostgreSQL
MySQL
SQLite for small single-node deployment
```

The store should persist:

* incidents;
* evidence summaries;
* hypotheses;
* action plans;
* approvals;
* checkpoints;
* execution attempts;
* recovery verification results;
* event timeline;
* generated skills;
* service profiles;
* incident memory records;
* audit records.

Recommended production direction:

```text
PostgreSQL for multi-user deployment
SQLite for simple single-host deployment
Redis for short-lived queues / locks / cache
```

---

### 3.4 Observability Backends

RunbookHermes should connect to real company observability systems:

```text
Prometheus
Loki
Jaeger or Tempo
Deploy history source
```

Environment variables:

```bash
OBS_BACKEND=real
PROMETHEUS_BASE_URL=https://prometheus.example.com
LOKI_BASE_URL=https://loki.example.com
TRACE_BACKEND=jaeger
TRACE_PROVIDER_KIND=jaeger
TRACE_BASE_URL=https://jaeger.example.com
DEPLOY_BACKEND=real
```

Relevant adapter files:

```text
integrations/observability/prometheus_backend.py
integrations/observability/loki_backend.py
integrations/observability/trace_backend.py
integrations/observability/deploy_backend.py
```

Production requirements:

* service accounts with read-only observability permissions;
* query timeout limits;
* query range limits;
* tenant / namespace restrictions;
* allowlist for services and labels;
* safe default queries;
* request tracing and audit logs;
* failure handling when a backend is unavailable.

---

### 3.5 Model Provider

RunbookHermes can use an OpenAI-compatible model endpoint for model-assisted summaries and operator-facing explanations.

Environment variables:

```bash
RUNBOOK_MODEL_ENABLED=true
RUNBOOK_MODEL_BASE_URL=https://your-openai-compatible-endpoint/v1
RUNBOOK_MODEL_API_KEY=your_api_key
RUNBOOK_MODEL_NAME=your_model_name
RUNBOOK_MODEL_TEMPERATURE=0
```

Production requirements:

* do not store API keys in source code;
* use secret manager or Kubernetes Secret;
* set temperature low for incident analysis;
* apply request timeout;
* avoid sending unnecessary raw logs to the model;
* rely on EvidenceStack summaries and evidence IDs;
* record model output in incident timeline or audit store;
* make model use optional and fail-safe.

Model output should assist operators, not bypass evidence or approval boundaries.

---

### 3.6 Feishu / WeCom Integration

RunbookHermes includes Feishu and WeCom gateway shells.

Production Feishu variables:

```bash
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_VERIFICATION_TOKEN=
FEISHU_ENCRYPT_KEY=
FEISHU_CALLBACK_BASE_URL=https://runbookhermes.example.com
FEISHU_BOT_WEBHOOK_URL=
FEISHU_BOT_SECRET=
```

Production WeCom variables:

```bash
WECOM_CORP_ID=
WECOM_AGENT_ID=
WECOM_SECRET=
WECOM_TOKEN=
WECOM_ENCODING_AES_KEY=
WECOM_CALLBACK_BASE_URL=https://runbookhermes.example.com
```

Expected routes:

```text
/gateway/feishu/events
/gateway/feishu/card-callback
/gateway/wecom/events
/gateway/wecom/card-callback
```

Production requirements:

* public HTTPS callback URL;
* request signature verification;
* encryption / decryption if enabled;
* replay protection;
* approval permission checks;
* card callback validation;
* mapping user identity to approver identity;
* audit every approve / reject decision;
* fail closed when verification fails.

---

### 3.7 Controlled Execution Backend

RunbookHermes should not directly mutate production systems through unrestricted shell commands.

Production remediation should go through a controlled executor backend.

Supported design options:

```text
custom_http executor
Kubernetes executor
Argo CD executor
Argo Rollouts executor
internal release platform executor
```

Environment variables for custom HTTP executor:

```bash
ACTION_EXECUTION_BACKEND=custom_http
ACTION_EXECUTION_API_BASE_URL=https://executor.example.com
ACTION_EXECUTION_API_TOKEN=your_token
ACTION_EXECUTION_TIMEOUT_SECONDS=5
RUNBOOK_CONTROLLED_EXECUTION_ENABLED=true
```

The executor should implement:

* action allowlist;
* service allowlist;
* environment allowlist;
* dry-run endpoint;
* execute endpoint;
* status endpoint;
* rollback failure handling;
* recovery verification hook;
* audit event emission.

Production execution flow:

```text
action planned
→ policy guard
→ approval requested
→ approval granted
→ checkpoint created
→ dry-run
→ execute through controlled backend
→ verify recovery
→ write audit timeline
```

---

## 4. Environment Variable Groups

### 4.1 Runtime

```bash
RUNBOOK_PROFILE=runbook-hermes
RUNBOOK_ENVIRONMENT=prod
RUNBOOK_STORE_BACKEND=postgres
RUNBOOK_LOG_LEVEL=INFO
```

### 4.2 Web/API

```bash
RUNBOOK_API_HOST=0.0.0.0
RUNBOOK_API_PORT=8000
RUNBOOK_PUBLIC_BASE_URL=https://runbookhermes.example.com
```

### 4.3 Model

```bash
RUNBOOK_MODEL_ENABLED=true
RUNBOOK_MODEL_BASE_URL=https://your-openai-compatible-endpoint/v1
RUNBOOK_MODEL_API_KEY=your_api_key
RUNBOOK_MODEL_NAME=your_model_name
RUNBOOK_MODEL_TEMPERATURE=0
```

### 4.4 Observability

```bash
OBS_BACKEND=real
PROMETHEUS_BASE_URL=https://prometheus.example.com
LOKI_BASE_URL=https://loki.example.com
TRACE_BACKEND=jaeger
TRACE_PROVIDER_KIND=jaeger
TRACE_BASE_URL=https://jaeger.example.com
DEPLOY_BACKEND=real
```

### 4.5 Feishu

```bash
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_VERIFICATION_TOKEN=
FEISHU_ENCRYPT_KEY=
FEISHU_CALLBACK_BASE_URL=https://runbookhermes.example.com
FEISHU_BOT_WEBHOOK_URL=
FEISHU_BOT_SECRET=
```

### 4.6 WeCom

```bash
WECOM_CORP_ID=
WECOM_AGENT_ID=
WECOM_SECRET=
WECOM_TOKEN=
WECOM_ENCODING_AES_KEY=
WECOM_CALLBACK_BASE_URL=https://runbookhermes.example.com
```

### 4.7 Execution

```bash
RUNBOOK_CONTROLLED_EXECUTION_ENABLED=true
ACTION_EXECUTION_BACKEND=custom_http
ACTION_EXECUTION_API_BASE_URL=https://executor.example.com
ACTION_EXECUTION_API_TOKEN=your_token
ACTION_EXECUTION_TIMEOUT_SECONDS=5
```

---

## 5. Production Deployment Option A: Single Host

A simple production-oriented single-host deployment can run:

```text
runbookhermes-api
runbookhermes-agent
postgres or sqlite
redis
reverse proxy
```

Example process layout:

```text
systemd service: runbookhermes-api
systemd service: runbookhermes-agent
systemd service: redis
external database or local postgres
nginx / caddy reverse proxy
```

This is suitable for:

* internal pilot;
* small team deployment;
* controlled staging environment;
* non-critical incident assistant usage.

Minimum hardening:

* HTTPS;
* authentication;
* no plaintext secrets in files;
* write logs to persistent location;
* back up database;
* restrict executor access;
* restrict observability access.

---

## 6. Production Deployment Option B: Docker Compose

A Docker Compose deployment can include:

```text
runbookhermes-api
runbookhermes-agent
postgres
redis
nginx
```

Suggested compose structure:

```yaml
services:
  runbookhermes-api:
    image: runbookhermes:latest
    command: uvicorn apps.runbook_api.app.main:app --host 0.0.0.0 --port 8000
    env_file:
      - .env.runbook
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - redis

  runbookhermes-agent:
    image: runbookhermes:latest
    command: hermes --profile runbook-hermes
    env_file:
      - .env.runbook
    depends_on:
      - postgres
      - redis

  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: runbookhermes
      POSTGRES_USER: runbookhermes
      POSTGRES_PASSWORD: change_me
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7

volumes:
  postgres_data:
```

This is a reference layout. Adjust image names, secrets, storage, networking, and TLS for your environment.

---

## 7. Production Deployment Option C: Kubernetes

A Kubernetes deployment should split components clearly.

Recommended resources:

```text
Deployment: runbookhermes-api
Deployment: runbookhermes-agent
Service: runbookhermes-api
Ingress: HTTPS public/internal route
Secret: model keys, Feishu keys, WeCom keys, executor token
ConfigMap: non-secret runtime configuration
StatefulSet or external DB: PostgreSQL
Deployment or external service: Redis
NetworkPolicy: restrict outbound and inbound access
ServiceAccount: limited runtime permission
```

API deployment responsibilities:

```text
Web Console
Alertmanager webhook
Feishu / WeCom callback
Approval API
Monitoring API
Incident API
```

Agent deployment responsibilities:

```text
Hermes profile execution
model calls
tool calls
memory/context/skill operations
async incident reasoning
```

Important Kubernetes hardening:

* run as non-root;
* mount secrets as environment or files;
* restrict egress to observability, model, messaging, executor;
* restrict ingress to API/Gateway only;
* add readiness and liveness probes;
* use resource limits;
* set rollout strategy;
* persist audit logs;
* use separate service accounts for API and executor.

---

## 8. Ingress and Callback Routes

Production callback routes must be reachable from external systems.

Example public base URL:

```text
https://runbookhermes.example.com
```

Routes:

```text
GET  /web/index.html
GET  /web/monitoring.html
GET  /docs
POST /gateway/alertmanager
POST /gateway/feishu/events
POST /gateway/feishu/card-callback
POST /gateway/wecom/events
POST /gateway/wecom/card-callback
GET  /incidents
GET  /incidents/{incident_id}
GET  /incidents/{incident_id}/events
POST /approvals/{approval_id}/decision
POST /incidents/{incident_id}/verify-recovery
```

Ingress requirements:

* HTTPS only;
* request size limits;
* timeout configuration for long tool calls;
* rate limiting for public callbacks;
* IP allowlist when possible;
* request logging;
* WAF or gateway verification if available.

---

## 9. Authentication and RBAC

Production RunbookHermes should not expose Web Console and execution APIs without authentication.

Recommended roles:

```text
viewer       read incidents, evidence, monitoring
operator     create incidents, trigger evidence collection, verify recovery
approver     approve or reject risky actions
admin        configure integrations and execution backends
auditor      read audit timeline and historical records
```

Sensitive operations requiring RBAC:

* approve action;
* reject action;
* execute controlled action;
* verify recovery;
* change settings;
* configure model provider;
* configure executor backend;
* download raw incident payloads.

Fail-closed rule:

```text
If identity cannot be verified, do not execute production actions.
```

---

## 10. Security Boundaries

RunbookHermes should enforce the following boundaries:

### 10.1 Read-Only by Default

Observability tools should be read-only:

```text
Prometheus query
Loki query
Trace query
Deploy history read
```

### 10.2 Risk Classification

Actions should be classified:

```text
read_only
write_safe
write_risky
destructive
```

### 10.3 Approval Required

The following should require approval:

* rollback;
* route mutation;
* scaling mutation;
* restart;
* config mutation;
* deploy mutation;
* database-affecting operation.

### 10.4 Checkpoint Required

Before risky execution, record:

* incident ID;
* service;
* environment;
* current version;
* target version or action;
* current key metrics;
* deploy state;
* approval ID;
* operator identity;
* timestamp.

### 10.5 Dry-Run First

Production executor should provide dry-run before execute.

### 10.6 Verify Recovery

After execution, RunbookHermes must check metrics, logs, traces, or deploy status before marking incident recovered.

---

## 11. Observability Query Safety

Production observability queries can be expensive.

Recommended limits:

```text
max query range
max log lines
max trace count
query timeout
service allowlist
namespace allowlist
label allowlist
```

RunbookHermes should summarize evidence before sending it to the model.

Do not send raw high-volume logs to the model unless explicitly required and approved.

---

## 12. Audit Logging

Every production incident should have an audit timeline.

Audit events should include:

```text
incident.created
evidence.collected
hypothesis.generated
action.planned
approval.requested
approval.resolved
checkpoint.created
dry_run.started
dry_run.completed
action.executed
action.failed
recovery.verified
skill.generated
operator.comment_added
```

Audit events should include:

* timestamp;
* actor;
* source;
* service;
* environment;
* incident ID;
* action ID;
* approval ID;
* evidence IDs;
* result;
* error message if failed.

---

## 13. Production Readiness Checklist

Before connecting RunbookHermes to real production systems, check:

### Runtime

* [ ] API service runs behind HTTPS.
* [ ] Web/API requires authentication.
* [ ] RBAC is enabled.
* [ ] Secrets are not in Git.
* [ ] Environment variables are managed by Secret / ConfigMap / secret manager.

### Observability

* [ ] Prometheus is connected with read-only permission.
* [ ] Loki is connected with read-only permission.
* [ ] Jaeger / Tempo is connected with read-only permission.
* [ ] Query timeout and range limits are configured.
* [ ] Service and namespace allowlists are configured.

### Model

* [ ] Model provider is configured.
* [ ] Model timeout is configured.
* [ ] Sensitive raw logs are not sent by default.
* [ ] Model output is recorded as assistant summary, not treated as unquestionable truth.

### Messaging

* [ ] Feishu / WeCom callback URL uses HTTPS.
* [ ] Signature verification is enabled.
* [ ] Encryption handling is enabled if required.
* [ ] Approver identity is mapped to internal identity.
* [ ] Card approve / reject actions are audited.

### Execution

* [ ] Controlled execution is disabled by default until executor is configured.
* [ ] Executor supports dry-run.
* [ ] Executor supports allowlist.
* [ ] Executor supports audit events.
* [ ] Risky actions require approval.
* [ ] Checkpoints are persisted.
* [ ] Recovery verification is required.

### Storage

* [ ] JSON store is replaced or backed by persistent storage.
* [ ] Incident history is durable.
* [ ] Audit timeline is durable.
* [ ] Backups are configured.

---

## 14. Staged Rollout Plan

Recommended rollout path:

### Stage 1: Read-Only Production Connection

Enable:

```text
Prometheus
Loki
Jaeger / Tempo
Deploy history read-only
Web Console
Incident creation
```

Disable:

```text
controlled execution
production rollback
write actions
```

Goal:

```text
Prove evidence collection and incident analysis on real data.
```

### Stage 2: Human Approval Workflow

Enable:

```text
Feishu / WeCom approval cards
approval records
checkpoint creation
operator identity mapping
```

Still disable:

```text
actual production mutation
```

Goal:

```text
Prove approval and audit workflow.
```

### Stage 3: Dry-Run Executor

Enable:

```text
custom executor dry-run
policy check
service allowlist
environment allowlist
```

Still disable:

```text
actual execution
```

Goal:

```text
Prove that the executor can safely validate actions.
```

### Stage 4: Controlled Execution for Low-Risk Services

Enable execution only for:

```text
staging
canary
a non-critical service
low-risk actions
```

Goal:

```text
Prove controlled execution and recovery verification.
```

### Stage 5: Production Execution with Strict Guardrails

Enable production actions only after:

```text
RBAC
audit
approval
checkpoint
dry-run
recovery verification
rollback failure handling
on-call ownership
emergency stop
```

Goal:

```text
Production-grade assisted remediation, not uncontrolled autonomy.
```

---

## 15. Operating RunbookHermes in Production

Daily operations should include:

* review open incidents;
* review pending approvals;
* review high-frequency faults;
* review generated runbook skills;
* check integration readiness status;
* check model failures;
* check observability query failures;
* check executor dry-run failures;
* export audit logs if needed.

Weekly operations should include:

* review top incident categories;
* refine runbook skills;
* update service profiles;
* tune alert-to-incident mapping;
* review approval latency;
* review false-positive RCA patterns;
* improve evidence collection queries.

---

## 16. Relationship to Local Reference Deployment

The local reference deployment proves the workflow:

```text
service signal
→ evidence
→ incident
→ hypothesis
→ action
→ approval
→ checkpoint
→ controlled boundary
→ recovery verification
→ skill
```

Production deployment keeps the same workflow but replaces local components:

```text
local payment service       → real payment system
local Prometheus            → company Prometheus
local Loki                  → company Loki
local Jaeger                → company Jaeger / Tempo
local deploy JSON           → real deploy system
local file rollback         → controlled executor backend
local JSON store            → database
local manual Web approval   → Feishu / WeCom / RBAC approval
```

---

## 17. One-Sentence Production Definition

A production-oriented RunbookHermes deployment is a Hermes-native incident-response system that connects real observability, messaging, model, storage, and controlled execution systems while enforcing approval, checkpoint, dry-run, recovery verification, and audit boundaries.
