# RunbookHermes Roadmap

RunbookHermes is a Hermes-native AIOps agent for production-oriented incident response.

The roadmap is designed around one principle:

```text
Start with a local reference environment to prove the workflow.
Then harden each integration until RunbookHermes can safely connect to real production systems.
```

RunbookHermes is not intended to be a one-off dashboard. The long-term goal is an incident-response agent that can collect evidence, reason with memory and runbook skills, coordinate human approval, execute through controlled backends, verify recovery, and continuously improve operational knowledge.

---

## Current Status

RunbookHermes currently includes:

* Hermes Agent upstream foundation preserved;
* `runbook-hermes` profile and persona;
* RunbookHermes tool plugin;
* IncidentMemory provider;
* EvidenceStack context engine;
* runbook skills;
* Web Console;
* realtime monitoring page;
* incident detail page;
* approval center;
* digest and skill summary page;
* integration status page;
* local reference payment environment;
* Prometheus / Loki / Jaeger adapter layer;
* deploy-history adapter boundary;
* Feishu / WeCom gateway shells;
* OpenAI-compatible model-summary path;
* approval + checkpoint + dry-run + controlled execution design;
* local reference rollback flow;
* production executor interface design;
* validation and smoke scripts;
* deployment and integration documentation.

This is the foundation for the next stages.

---

## Roadmap Overview

```text
v0.1  Foundation and local reference environment
v0.2  Web Console, monitoring, and documentation hardening
v0.3  Real observability and model integration hardening
v0.4  Messaging workflow and approval productionization
v0.5  Controlled remediation executor integration
v0.6  Durable storage, memory browser, and skill forge
v0.7  Production deployment manifests and RBAC
v1.0  Production reference architecture
```

---

## v0.1 — Hermes-Native Incident Response Foundation

Goal:

```text
Make RunbookHermes a clear Hermes-native AIOps agent instead of a standalone script or dashboard.
```

Scope:

* preserve Hermes Agent upstream runtime and architecture;
* add `profiles/runbook-hermes/`;
* add RunbookHermes plugin and tool registry;
* add IncidentMemory provider;
* add EvidenceStack context engine;
* add initial runbook skills;
* add Web/API entry point;
* add incident store and event timeline;
* add approval and checkpoint concepts;
* add local reference payment system;
* add basic Prometheus / Loki / Jaeger adapter boundaries.

Status:

```text
Implemented as the current foundation.
```

---

## v0.2 — Web Console and Documentation Hardening

Goal:

```text
Make the project understandable, presentable, and easy to inspect through the Web Console and GitHub documentation.
```

Scope:

* rewrite root `README.md` for RunbookHermes;
* preserve upstream Hermes documentation under `docs/upstream/`;
* organize architecture, deployment, integration, and operations docs;
* add screenshots under `docs/assets/`;
* improve Web Console layout and information architecture;
* add monitoring dashboard;
* add settings / interface readiness page;
* make incident detail page show evidence, root cause, actions, approvals, checkpoints, timeline, and generated skills;
* add stronger validation scripts.

Status:

```text
In progress / mostly implemented.
```

Remaining work:

* add final screenshots to `docs/assets/`;
* verify all README image paths;
* remove or archive remaining construction-stage notes;
* update CONTRIBUTING and SECURITY docs for RunbookHermes.

---

## v0.3 — Real Observability and Model Integration Hardening

Goal:

```text
Make RunbookHermes reliable against real Prometheus, Loki, Jaeger / Tempo, deploy history, and model providers.
```

Scope:

### Observability

* harden Prometheus query adapter;
* add query templates for common incident patterns;
* support service / namespace / environment label mapping;
* add query timeout and range limits;
* improve Loki query result summarization;
* improve Jaeger / Tempo trace summary;
* add backend failure events to incident timeline;
* show backend health in Web Console.

### Model Provider

* connect a real OpenAI-compatible model provider;
* support internal model gateway deployment;
* add request timeout and retry policy;
* add sensitive-data redaction before model calls;
* ensure model output cites evidence IDs;
* record model summary in incident timeline;
* make model summary fail gracefully.

Deliverables:

* production-ready observability adapter configuration;
* real-model summary working in incident detail;
* documented query mapping examples;
* redaction and timeout behavior.

---

## v0.4 — Feishu / WeCom Workflow Productionization

Goal:

```text
Turn Feishu / WeCom from interface shells into a real on-call workflow layer.
```

Scope:

### Feishu

* implement complete event verification;
* implement encrypted event handling when enabled;
* implement card callback verification;
* implement approval card rendering;
* map Feishu user identity to internal approver identity;
* send incident summary cards;
* send approval cards;
* link cards back to Web Console.

### WeCom

* implement callback verification;
* implement encrypted callback handling;
* implement approval card callback flow;
* map WeCom user identity to internal approver identity;
* send incident summary and approval messages.

### Workflow

* add idempotency for duplicate callbacks;
* fail closed when identity cannot be verified;
* audit every approve / reject action;
* support notification-only mode;
* support approval-only mode before enabling execution.

Deliverables:

* Feishu production callback guide;
* WeCom production callback guide;
* working approval cards;
* identity mapping and audit record.

---

## v0.5 — Controlled Remediation Executor Integration

Goal:

```text
Safely connect RunbookHermes to real remediation systems through controlled executor backends.
```

Scope:

### Executor Contract

* finalize `custom_http` executor API;
* define `/dry-run`, `/execute`, `/status`, `/cancel` endpoints;
* add executor authentication;
* add action allowlist;
* add service allowlist;
* add environment allowlist;
* add idempotency key;
* add structured execution result.

### Execution Backends

* implement custom HTTP executor integration;
* add Kubernetes executor reference shell;
* add Argo CD executor reference shell;
* add Argo Rollouts executor reference shell;
* support internal release platform integration.

### Safety

* require approval for risky actions;
* require checkpoint before destructive actions;
* require dry-run before execute;
* require recovery verification after execute;
* record all executor events in timeline;
* add emergency stop mechanism.

Deliverables:

* controlled executor integration spec;
* custom HTTP executor reference implementation;
* Kubernetes / Argo adapter skeletons;
* staging controlled execution example;
* production readiness checklist.

---

## v0.6 — Durable Storage, Memory Browser, and Skill Forge

Goal:

```text
Make RunbookHermes' memory and runbook learning visible, durable, and operator-reviewable.
```

Scope:

### Storage

* replace local JSON store for production deployments;
* add SQLite option for single-node deployment;
* add PostgreSQL / MySQL option for team deployment;
* persist incidents, evidence, approvals, checkpoints, executions, recovery results, and audit events;
* add migration scripts.

### Memory Browser

* add `/web/memory.html`;
* show service profiles;
* show incident summaries;
* show team preferences;
* show recurring root causes;
* show memory source incident IDs;
* allow editing or archiving incorrect memory.

### Skill Forge

* add `/web/skills.html` or `/web/skill-forge.html`;
* show runbook skills;
* show source incident;
* show usage count;
* show review state;
* support draft / reviewed / approved / deprecated states;
* allow manual review and update.

### Similar Incident Search

* add keyword search;
* add SQLite FTS or PostgreSQL full-text search;
* plan vector / hybrid search for similar incidents;
* use similar incident summaries in EvidenceStack.

Deliverables:

* durable store backend;
* memory browser;
* skill forge;
* incident similarity search;
* operator review workflow for generated skills.

---

## v0.7 — Production Deployment, RBAC, and Audit

Goal:

```text
Prepare RunbookHermes for production-oriented deployment with real security boundaries.
```

Scope:

### Deployment

* add Dockerfile or production image guidance for RunbookHermes;
* add Docker Compose production reference;
* add Kubernetes manifests or Helm chart;
* split API and Agent Runner processes;
* add health checks;
* add readiness checks;
* add environment-based configuration.

### Security

* add authentication to Web/API;
* add RBAC roles:

  * viewer;
  * operator;
  * approver;
  * admin;
  * auditor;
* restrict execution APIs;
* restrict raw evidence access;
* protect callback routes;
* add request logging;
* add audit persistence.

### Operations

* add backup guidance;
* add log retention guidance;
* add incident archive guidance;
* add production alerting for RunbookHermes itself;
* add operational runbook for RunbookHermes outages.

Deliverables:

* production deployment reference;
* RBAC design;
* audit log persistence;
* Kubernetes / Docker Compose production templates.

---

## v1.0 — Production Reference Architecture

Goal:

```text
Provide a complete production reference architecture for a Hermes-native AIOps incident-response agent.
```

Expected v1.0 capabilities:

* Hermes-native runtime with `runbook-hermes` profile;
* real Prometheus / Loki / Jaeger or Tempo integration;
* model-assisted evidence-aware root-cause explanation;
* IncidentMemory with durable storage;
* EvidenceStack with controlled context compression;
* runbook skills with review workflow;
* Feishu / WeCom production approval workflow;
* controlled executor backend integration;
* approval + checkpoint + dry-run + recovery verification;
* Web Console with incident, monitoring, approval, memory, and skill pages;
* production deployment reference;
* RBAC;
* audit logging;
* safe rollout documentation.

v1.0 should be suitable as:

```text
A production reference implementation,
not an uncontrolled production autopilot.
```

---

## Future Ideas

Potential future directions:

* multi-agent incident collaboration;
* service ownership graph;
* dependency graph from traces;
* automatic postmortem generation;
* incident cost estimation;
* SLO-aware prioritization;
* blast-radius estimation;
* playbook simulation;
* chaos testing integration;
* policy-as-code for remediation approval;
* MCP-based observability toolserver expansion;
* incident similarity vector search;
* Slack / DingTalk / email integrations;
* Terraform / cloud resource read-only evidence collection;
* Kubernetes event evidence collection;
* change-risk scoring from deploy metadata.

---

## Non-Goals

RunbookHermes should not become:

```text
an unrestricted shell execution bot;
a model-only RCA generator without evidence;
a production system that executes rollback without approval;
a dashboard that does not use Hermes Agent capabilities;
a memory system that stores every raw log line;
a replacement for existing deploy platforms;
a tool that hides operational risk from humans.
```

The project should stay focused on:

```text
evidence-driven reasoning
human-in-the-loop approval
controlled execution
recovery verification
memory and skill learning
production-oriented integration boundaries
```

---

## Contribution Priorities

High-value contributions:

1. production storage backend;
2. Feishu / WeCom callback hardening;
3. Prometheus / Loki / Jaeger adapter improvements;
4. Kubernetes / Argo executor reference;
5. Memory Browser UI;
6. Skill Forge UI;
7. incident similarity search;
8. authentication and RBAC;
9. deployment templates;
10. more runbook skills for real incident classes.

---

## One-Sentence Roadmap Summary

RunbookHermes is moving from a Hermes-native local reference implementation toward a production-ready AIOps incident-response agent: real observability, real messaging, durable memory, reviewed runbook skills, controlled remediation, RBAC, audit, and deployable production architecture.
