# Contributing to RunbookHermes

Thank you for your interest in contributing to RunbookHermes.

RunbookHermes is a Hermes-native AIOps agent built by adapting the official Hermes Agent codebase into an incident-response system. It combines Hermes Agent's runtime, provider routing, tool system, memory, context engine, skills, gateway, and safety boundaries with RunbookHermes-specific capabilities for observability evidence, root-cause analysis, approval-gated remediation, recovery verification, and runbook learning.

This document explains how to contribute safely and productively.

---

## 1. Project Structure

RunbookHermes contains two major layers:

```text
Hermes Agent upstream foundation
+ RunbookHermes AIOps extension layer
```

When contributing, it is important to understand which layer you are changing.

### 1.1 Hermes Agent Foundation

Examples:

```text
agent/
gateway/
hermes_cli/
tools/
toolsets.py
run_agent.py
cli.py
```

These files come mainly from the upstream Hermes Agent project.

Be careful when modifying this layer. Changes here may affect the general Hermes runtime, not only RunbookHermes.

### 1.2 RunbookHermes Extension Layer

Examples:

```text
profiles/runbook-hermes/
plugins/runbook-hermes/
plugins/memory/incident_memory/
plugins/context_engine/evidence_stack/
runbook_hermes/
apps/runbook_api/
web/static/
integrations/observability/
toolservers/observability_mcp/
skills/runbooks/
demo/payment_system/
docs/
```

Most RunbookHermes contributions should happen in this layer.

---

## 2. Good Contribution Areas

High-value contributions include:

* observability adapter improvements;
* Prometheus query templates;
* Loki log summarization;
* Jaeger / Tempo trace summarization;
* deploy-history adapters;
* Feishu / WeCom production callback hardening;
* controlled executor adapters;
* Kubernetes / Argo CD / Argo Rollouts integration;
* IncidentMemory improvements;
* EvidenceStack improvements;
* runbook skills for real incident classes;
* Web Console improvements;
* Memory Browser page;
* Skill Forge page;
* durable storage backend;
* RBAC and audit logging;
* deployment templates;
* documentation and examples.

---

## 3. Non-Goals

Please avoid contributions that turn RunbookHermes into:

```text
an unrestricted shell execution bot;
a model-only RCA generator without evidence;
a production rollback bot without approval;
a dashboard that does not use Hermes-native concepts;
a memory system that stores every raw log line;
a replacement for existing deploy platforms;
a tool that hides operational risk from humans.
```

RunbookHermes should remain focused on:

```text
evidence-driven incident response;
Hermes-native agent architecture;
human-in-the-loop approval;
checkpoint and dry-run safety;
controlled execution;
recovery verification;
operational memory;
runbook skill learning;
production-oriented integration boundaries.
```

---

## 4. Development Setup

Recommended Python version:

```text
Python 3.11
```

Create an environment:

```bash
conda create -n runbookhermes311 python=3.11 pip -y
conda activate runbookhermes311
```

Install dependencies from the repository root:

```bash
python -m pip install -e ".[web]"
```

Set `PYTHONPATH`:

On Windows Anaconda Prompt:

```bat
set PYTHONPATH=.
```

On macOS / Linux / WSL:

```bash
export PYTHONPATH=.
```

Start the Web/API service:

```bash
python -m uvicorn apps.runbook_api.app.main:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/web/index.html
http://127.0.0.1:8000/web/monitoring.html
http://127.0.0.1:8000/docs
```

---

## 5. Local Reference Environment

RunbookHermes includes a local reference payment environment.

Start it with:

```bash
cd demo/payment_system
docker compose up --build
```

This starts:

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

Then configure RunbookHermes against local observability:

```bash
export OBS_BACKEND=real
export DEPLOY_BACKEND=demo_file
export TRACE_BACKEND=jaeger
export TRACE_PROVIDER_KIND=jaeger
export ROLLBACK_BACKEND_KIND=demo_file
export RUNBOOK_CONTROLLED_EXECUTION_ENABLED=true

export PROMETHEUS_BASE_URL=http://127.0.0.1:9090
export LOKI_BASE_URL=http://127.0.0.1:3100
export TRACE_BASE_URL=http://127.0.0.1:16686

export DEMO_DEPLOY_STATE_FILE=data/payment_demo/deployments.json
export DEMO_VERSION_FILE=data/payment_demo/runtime/payment-service-version.txt
```

On Windows Anaconda Prompt, use `set` instead of `export`.

Generate traffic:

```bash
cd demo/payment_system
python scripts/generate_traffic.py --fault PAYMENT_503_AFTER_DEPLOY --requests 60
python scripts/generate_traffic.py --fault COUPON_504_TIMEOUT --requests 40
python scripts/generate_traffic.py --fault ORDER_429_RATE_LIMIT --requests 40
```

---

## 6. Validation Before Pull Request

Before opening a pull request, run validation from the repository root:

```bash
python -S scripts/runbook_validate.py
python -S scripts/runbook_gateway_smoke.py
python -S scripts/runbook_no_legacy_imports.py
python -S scripts/runbook_monitoring_validate.py
python -S scripts/runbook_stage8_validate.py
```

Also run Python compile check for changed Python modules:

```bash
python -S -m compileall -q runbook_hermes apps/runbook_api integrations plugins scripts
```

If your change touches the local payment reference environment, also test:

```bash
cd demo/payment_system
docker compose up --build
```

Then verify the Web Console and Monitoring page.

---

## 7. Pull Request Guidelines

A good pull request should include:

* clear title;
* concise description;
* affected area;
* motivation;
* implementation summary;
* testing performed;
* screenshots for UI changes;
* migration notes if needed;
* security considerations if execution, secrets, or production callbacks are involved.

Recommended PR title format:

```text
area: short description
```

Examples:

```text
observability: add Tempo trace adapter
web: add Memory Browser page
executor: add custom HTTP dry-run support
docs: add production deployment guide
skills: add Redis latency runbook skill
```

---

## 8. Commit Message Guidelines

Use readable commit messages.

Examples:

```text
Add Loki log summary limits
Add approval idempotency handling
Document production executor rollout plan
Improve incident detail timeline rendering
```

Avoid vague commits:

```text
update
fix
misc
change stuff
```

---

## 9. Documentation Contributions

Documentation is important for RunbookHermes because the project combines Hermes Agent concepts with AIOps production workflows.

Good documentation contributions include:

* architecture explanations;
* deployment guides;
* integration guides;
* runbook examples;
* screenshots;
* troubleshooting notes;
* security and production-readiness checklists.

Important docs:

```text
docs/architecture/hermes-runbook-mapping.md
docs/deployment/local-reference.md
docs/deployment/production.md
docs/integrations/model-provider.md
docs/integrations/prometheus-loki-jaeger.md
docs/integrations/feishu-wecom.md
docs/integrations/rollback-executor.md
docs/operations/approval-checkpoint-recovery.md
docs/operations/memory-and-skills.md
```

When adding screenshots, place them under:

```text
docs/assets/
```

Use descriptive file names:

```text
overview.png
monitoring-overview.png
incident-evidence.png
approval-center.png
```

---

## 10. Adding a New Observability Adapter

If you add or improve an observability adapter, consider:

* read-only access by default;
* query timeout;
* query range limit;
* service allowlist;
* namespace allowlist;
* evidence ID generation;
* result summarization;
* model-safe output;
* backend error handling;
* tests or smoke scripts;
* documentation.

The adapter should return evidence summaries, not unlimited raw data.

---

## 11. Adding a New Executor

Executor contributions are security-sensitive.

A new executor must not allow arbitrary model-generated commands.

Executor contributions should include:

* structured action schema;
* dry-run support;
* service allowlist;
* environment allowlist;
* action allowlist;
* authentication;
* timeout;
* idempotency;
* audit events;
* failure handling;
* recovery verification hook;
* documentation.

Risky actions should require:

```text
approval
checkpoint
dry-run
controlled execution
recovery verification
audit timeline
```

---

## 12. Adding a New Runbook Skill

Runbook skills live under:

```text
skills/runbooks/
```

A good runbook skill should include:

* when to use it;
* affected service or service class;
* symptoms;
* evidence to collect;
* likely root causes;
* safe read-only tools;
* risky actions;
* approval requirements;
* checkpoint requirements;
* recovery verification steps;
* escalation rules;
* source incident references if available.

Avoid skills that say only:

```text
If service fails, rollback.
```

A good RunbookHermes skill should be evidence-driven and safety-aware.

---

## 13. Web UI Contributions

Web UI files live in:

```text
web/static/
```

Important pages:

```text
index.html
monitoring.html
incidents.html
incident.html
approvals.html
digests.html
settings.html
styles.css
app.js
```

UI contributions should:

* preserve a professional AIOps console style;
* make evidence visible;
* make safety boundaries visible;
* avoid hiding approval and checkpoint state;
* show backend readiness clearly;
* include screenshots in PRs;
* avoid adding heavy frontend dependencies unless necessary.

---

## 14. Security Guidelines

Never commit:

```text
.env
.env.runbook
API keys
model keys
Feishu secrets
WeCom secrets
executor tokens
production logs
customer data
private certificates
local database files
.runbook_hermes_store/
```

Use `.env.example` or `.env.runbook.example` for templates only.

If a contribution touches any of the following, include a security note:

* production execution;
* callback verification;
* identity mapping;
* model provider;
* raw logs;
* trace payloads;
* secrets;
* authentication;
* RBAC;
* audit logs.

---

## 15. Handling Upstream Hermes Changes

RunbookHermes is built on top of Hermes Agent.

When pulling in upstream Hermes changes:

1. keep upstream changes separate from RunbookHermes feature work when possible;
2. check whether upstream changes affect profiles, providers, tools, memory, context, gateway, or execution;
3. re-run RunbookHermes validation scripts;
4. verify `profiles/runbook-hermes/` still loads;
5. verify RunbookHermes tools still register;
6. verify Web/API still works;
7. update `docs/upstream/` only if needed.

Avoid mixing large upstream sync and RunbookHermes feature changes in one PR.

---

## 16. Issue Guidelines

When opening an issue, include:

* what you were trying to do;
* local or production mode;
* operating system;
* Python version;
* relevant environment variables without secrets;
* command used;
* expected behavior;
* actual behavior;
* logs or screenshots;
* whether Docker / Prometheus / Loki / Jaeger were running.

For integration requests, include:

* target system;
* API docs if available;
* auth method;
* expected evidence or action shape;
* safety requirements;
* production constraints.

---

## 17. Review Checklist

Reviewers should check:

* Does this preserve Hermes-native architecture?
* Does it keep evidence visible?
* Does it avoid unsafe production mutation?
* Does it preserve approval and checkpoint boundaries?
* Does it handle errors gracefully?
* Does it avoid leaking secrets or raw sensitive data?
* Does it include tests or validation notes?
* Does it update docs if behavior changes?
* Does it keep local reference mode working?
* Does it avoid unnecessary large dependencies?

---

## 18. Code Style

General guidance:

* keep functions small and readable;
* prefer explicit data structures;
* avoid hidden side effects;
* validate external inputs;
* handle missing backends gracefully;
* return structured errors;
* keep UI copy clear and operator-focused;
* write documentation for production-facing behavior.

RunbookHermes values operational clarity over clever code.

---

## 19. Community Expectations

Please be respectful and practical.

RunbookHermes is an incident-response project. Discussions should focus on:

* reliability;
* safety;
* observability;
* production integration;
* operator experience;
* clear evidence;
* clear boundaries.

Disagreements are welcome when they improve the design.

---

## 20. One-Sentence Contribution Principle

A good RunbookHermes contribution makes the agent more evidence-driven, safer to operate, easier to deploy, easier to integrate, or better at turning incidents into reusable operational knowledge.
