# Hermes Agent → RunbookHermes Architecture Mapping

RunbookHermes is a Hermes-native AIOps agent built by adapting the official Hermes Agent codebase into a production-oriented incident-response system.

This document explains what RunbookHermes inherits from Hermes Agent, what it adds, what it does not replace, and how the two layers fit together.

---

## 1. Summary

RunbookHermes should be understood as:

```text
Hermes Agent upstream source
+ RunbookHermes AIOps / incident-response extension layer
= RunbookHermes
```

It is not a standalone dashboard placed beside Hermes Agent. It is not a separate rule engine. It is also not a full rewrite of Hermes.

The current implementation keeps the Hermes Agent foundation and adds a vertical AIOps layer for:

* payment-system incident intake;
* observability evidence collection;
* root-cause analysis;
* model-assisted incident summary;
* approval-gated actions;
* checkpoint and dry-run safety;
* controlled remediation interfaces;
* recovery verification;
* runbook skill generation;
* operational memory.

---

## 2. What Was Changed from Hermes Agent?

The RunbookHermes codebase was created by merging RunbookHermes overlay files into the official Hermes Agent source tree.

The intended design is:

```text
Do not break Hermes core.
Do not remove Hermes runtime capabilities.
Add a RunbookHermes layer on top of Hermes.
Use Hermes profile, plugin, memory, context, skills, gateway, tools, and execution concepts.
```

In practice, the RunbookHermes extension primarily adds new directories and files rather than rewriting Hermes core internals.

Major RunbookHermes additions include:

```text
profiles/runbook-hermes/                 # RunbookHermes Hermes profile and persona
plugins/runbook-hermes/                  # Runbook-specific Hermes plugin and tools
plugins/memory/incident_memory/          # IncidentMemory provider
plugins/context_engine/evidence_stack/   # EvidenceStack context engine
runbook_hermes/                          # AIOps domain logic
apps/runbook_api/                        # FastAPI Web/API service
web/static/                              # Web Console UI
integrations/observability/              # Prometheus / Loki / Trace / Deploy adapters
toolservers/observability_mcp/           # Observability toolserver boundary
skills/runbooks/                         # Runbook skills
demo/payment_system/                     # Local reference payment environment
data/payment_demo/                       # Reference deploy/runtime state
data/runbook_mock/                       # Mock fallback observability data
scripts/runbook_*.py                     # Validation and smoke scripts
docs/runbook-hermes/ and docs/*          # RunbookHermes documentation
```

A small number of shared project files, such as `pyproject.toml`, may be adjusted so the new RunbookHermes packages can be installed and imported correctly.

---

## 3. Layered Architecture

RunbookHermes has two layers:

```text
┌─────────────────────────────────────────────────────────────┐
│                    RunbookHermes Layer                      │
│ Incident APIs, Web Console, EvidenceStack, IncidentMemory,   │
│ observability adapters, approval, checkpoint, rollback,      │
│ recovery verification, runbook skills                        │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │ uses / extends
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Hermes Agent Foundation                   │
│ runtime loop, provider routing, tool system, gateway,        │
│ memory interfaces, context interfaces, skills, execution     │
│ boundary, CLI, platform services                             │
└─────────────────────────────────────────────────────────────┘
```

Hermes provides the general-purpose agent foundation. RunbookHermes provides the incident-response specialization.

---

## 4. Mapping Table

| Hermes Agent capability   | RunbookHermes adaptation                                                                                                                        | Status                         |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------ |
| Agent runtime / loop      | `runbook-hermes` profile turns Hermes into an incident-response agent.                                                                          | Preserved and specialized      |
| Provider / model routing  | Hermes provider architecture remains available; RunbookHermes also exposes OpenAI-compatible model-summary configuration for Web/API summaries. | Preserved + extended           |
| Tool system               | Adds observability, deployment, approval, policy, rollback, and recovery tools.                                                                 | Extended                       |
| Memory provider           | Adds `IncidentMemory` for service profiles, incident summaries, preferences, and skill index.                                                   | Domain-specific implementation |
| Context engine            | Adds `EvidenceStack` to compress alert, evidence, hypotheses, actions, and final answer.                                                        | Domain-specific implementation |
| Skills                    | Adds runbook skills for payment incident triage and common incident handling.                                                                   | Extended                       |
| Gateway                   | Keeps Hermes gateway foundation and adds Alertmanager, Feishu, WeCom, Web/API incident entry points.                                            | Extended                       |
| Execution backend concept | Adds local reference controlled rollback and production executor interfaces.                                                                    | Extended                       |
| Safety boundary           | Adds approval, checkpoint, dry-run, controlled execution, and recovery verification.                                                            | Extended for AIOps             |
| Web / API                 | Adds RunbookHermes control plane for incidents, approvals, monitoring, digest, and settings.                                                    | New application layer          |

---

## 5. Hermes Runtime and RunbookHermes Profile

Hermes Agent supports profiles that define how an agent behaves in a particular role.

RunbookHermes adds:

```text
profiles/runbook-hermes/config.yaml
profiles/runbook-hermes/SOUL.md
```

The purpose of the `runbook-hermes` profile is to turn Hermes from a general-purpose agent into an AIOps incident-response agent.

The profile should define or reference:

* incident-response behavior;
* tool allowlist;
* memory provider;
* context engine;
* model/provider configuration;
* safety policy;
* runbook-specific operating rules.

When using Hermes-native interaction, the expected entry is:

```bash
hermes --profile runbook-hermes
```

This is different from opening the Web Console. The Web Console is the operator control plane. The Hermes profile is the conversational agent path.

---

## 6. Tool System Mapping

Hermes Agent has a general tool system. RunbookHermes specializes that tool system for incident response.

RunbookHermes tools are designed around evidence collection and safe action planning, not arbitrary unrestricted execution.

Representative RunbookHermes tools include:

```text
prom_query
prom_top_anomalies
loki_query
trace_search
recent_deploys
rollback_canary
verify_recovery
incident_rca_guard
action_policy_guard
runbook_approval_decision
execute_controlled_action
```

These tools map to the incident-response flow:

```text
alert
→ collect metrics / logs / traces / deploy records
→ build evidence stack
→ generate hypothesis
→ plan action
→ check policy
→ request approval
→ create checkpoint
→ dry-run
→ controlled execution
→ verify recovery
→ record timeline
→ generate runbook skill
```

This is why RunbookHermes is not just a dashboard. The dashboard is only one interface to the underlying incident workflow.

---

## 7. Memory Mapping: Hermes Memory → IncidentMemory

Hermes Agent includes memory concepts for remembering useful information across sessions.

RunbookHermes does not replace this architecture. It implements a domain-specific memory provider:

```text
plugins/memory/incident_memory/
```

`IncidentMemory` is designed for operational memory, not generic chat memory.

It should remember stable incident-response knowledge such as:

* service profiles;
* service owners or team preferences;
* recurring incident summaries;
* previous root causes;
* approval requirements;
* generated runbook skills;
* remediation patterns that worked before.

It should avoid storing noisy raw data such as:

* full raw logs;
* entire trace payloads;
* every metric sample;
* temporary stack traces;
* unfiltered chat transcripts.

The idea is:

```text
Do not remember everything.
Remember the right operational facts at the right time.
```

For example:

```text
payment-service previously had HTTP 503 incidents after release.
A common evidence pattern is HTTP 503 increase + connection pool exhausted logs + mysql-payment trace latency.
Rollback requires approval and checkpoint.
```

This is useful operational memory. A thousand raw log lines are not.

---

## 8. Context Mapping: Hermes Context → EvidenceStack

Hermes Agent has context-management concepts for constructing the model input from relevant state.

RunbookHermes adds an incident-specific context engine:

```text
plugins/context_engine/evidence_stack/
```

`EvidenceStack` organizes incident context into evidence-centered layers:

```text
alert summary
evidence
hypotheses
actions
final answer
```

This matters because incident response produces large volumes of context:

* Prometheus time series;
* Loki log lines;
* trace spans;
* deploy records;
* approval states;
* action plans;
* checkpoint payloads;
* timeline events.

RunbookHermes should not push all raw data into the prompt. Instead, it compresses evidence into summaries with evidence IDs.

Example compressed evidence:

```text
ev_metric_http_503_rate:
  source: prometheus
  summary: payment-service HTTP 503 rate increased to 18%

ev_log_connection_pool:
  source: loki
  summary: connection pool exhausted appeared repeatedly after release

ev_trace_mysql_latency:
  source: jaeger
  summary: payment-service -> mysql-payment p95 latency increased

ev_deploy_v231:
  source: deploy
  summary: payment-service v2.3.1 was deployed recently
```

This gives the model a traceable evidence chain instead of a noisy blob of logs.

---

## 9. Do Hermes Memory and RunbookHermes Memory Conflict?

No.

Hermes provides memory and context extension mechanisms. RunbookHermes implements incident-specific memory and context modules on top of those mechanisms.

A useful way to think about it:

```text
Hermes memory/context = framework and extension points
RunbookHermes IncidentMemory/EvidenceStack = AIOps-specific implementations
```

They only conflict if the profile is configured to inject multiple unrelated memory systems into the same reasoning path without clear boundaries.

The intended configuration is:

```text
Normal Hermes profile:
  use general Hermes memory/context behavior

RunbookHermes profile:
  use IncidentMemory + EvidenceStack for incident response
```

So the relationship is specialization, not duplication.

---

## 10. Skills Mapping: Hermes Skills → Runbook Skills

Hermes Agent emphasizes reusable skills.

RunbookHermes maps this concept into runbook skills:

```text
skills/runbooks/
```

Runbook skills describe how to handle recurring operational scenarios.

Examples:

```text
payment-service HTTP 503 after release
coupon-service HTTP 504 timeout
order-service HTTP 429 rate limit
common incident triage
```

A runbook skill can describe:

* when to use the skill;
* what evidence to collect;
* what root-cause patterns to check;
* what actions are safe;
* what actions require approval;
* how to verify recovery;
* what to record after the incident.

This is how RunbookHermes turns incident handling into accumulated knowledge.

---

## 11. Gateway Mapping

Hermes Agent has a gateway architecture for external entry points.

RunbookHermes adapts this into incident-intake gateways:

```text
Alertmanager
Feishu
WeCom
Web/API
```

The purpose is to normalize different entry sources into a common incident command.

Example:

```text
Alertmanager alert
→ RunbookHermes gateway
→ IncidentCommand
→ incident created
→ evidence collected
→ hypothesis generated
→ action planned
→ approval requested
```

This makes the entry point flexible while keeping the incident workflow consistent.

---

## 12. Execution and Safety Mapping

Hermes Agent includes concepts around execution backends and safety boundaries.

RunbookHermes applies these ideas to operational remediation.

RunbookHermes uses this safety chain:

```text
action policy
→ approval
→ checkpoint
→ dry-run
→ controlled execution
→ recovery verification
→ audit timeline
```

This is especially important because AIOps agents may interact with production systems.

RunbookHermes should not directly execute dangerous actions just because a model suggests them.

Examples of risky actions:

* service rollback;
* service restart;
* scaling mutation;
* route change;
* configuration mutation;
* database-affecting operation;
* production deploy system operation.

These actions should require explicit policy checks and human approval.

---

## 13. Web/API Layer

RunbookHermes adds a Web/API layer:

```text
apps/runbook_api/
web/static/
```

This layer provides:

* incident list;
* incident detail;
* evidence cards;
* root-cause hypothesis;
* action plan;
* approval center;
* checkpoint display;
* event timeline;
* generated runbook skill view;
* digest and skill summary;
* realtime monitoring dashboard;
* settings and interface status;
* Swagger API.

This layer is not the Hermes runtime itself. It is the operator-facing control plane for the RunbookHermes incident workflow.

---

## 14. Local Reference Environment vs Production Integration

RunbookHermes includes a local payment reference environment:

```text
demo/payment_system/
```

This environment is used to validate how RunbookHermes connects to real-style systems:

* payment-service;
* order-service;
* coupon-service;
* MySQL;
* Redis;
* Prometheus;
* Loki;
* Jaeger;
* Grafana.

The local reference environment is not the final production target. It exists to prove and demonstrate the integration path.

Production integration should replace local reference components with real systems:

| Local reference     | Production replacement                     |
| ------------------- | ------------------------------------------ |
| local Prometheus    | company Prometheus                         |
| local Loki          | company Loki                               |
| local Jaeger        | company Jaeger / Tempo                     |
| demo deploy JSON    | real deploy platform / Argo / Kubernetes   |
| local rollback file | controlled executor backend                |
| local JSON store    | SQLite / MySQL / PostgreSQL                |
| local Web/API       | deployed service with auth, ingress, audit |

---

## 15. Deployment Relationship

RunbookHermes is a merged repository. You do not deploy official Hermes Agent first and then deploy RunbookHermes as an unrelated second system.

Correct model:

```text
Deploy the merged RunbookHermes codebase.
Run different entry points depending on the mode.
```

Typical entry points:

```text
Web/API:
  uvicorn apps.runbook_api.app.main:app

Hermes-native chat:
  hermes --profile runbook-hermes

Local payment reference system:
  cd demo/payment_system
  docker compose up --build

Alertmanager / Feishu / WeCom:
  configure webhook routes exposed by the RunbookHermes API/Gateway layer
```


---

## 16. Recommended Next Productization Steps

To make RunbookHermes closer to a production-grade system, the next important steps are:

1. replace local JSON store with SQLite / MySQL / PostgreSQL;
2. add authentication and RBAC to the Web/API layer;
3. complete Feishu / WeCom signature and encryption verification;
4. connect a real model provider through the production environment;
5. connect real Prometheus / Loki / Jaeger / Tempo;
6. implement production deploy history adapter;
7. implement controlled executor backend for Kubernetes / Argo / internal release platform;
8. add persistent audit logging;
9. add Memory Browser page;
10. add Skill Forge page;
11. add incident similarity search;
12. add production Docker Compose / Kubernetes manifests.

---

## 17. One-Sentence Explanation

RunbookHermes keeps Hermes Agent as the agent foundation and adds an AIOps incident-response layer that turns Hermes capabilities—runtime, providers, tools, memory, context, skills, gateway, and safety boundaries—into a payment-system troubleshooting and remediation workflow.
