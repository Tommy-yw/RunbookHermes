# Security Policy

RunbookHermes is a Hermes-native AIOps agent for incident response. It can connect to observability systems, messaging platforms, model providers, and controlled remediation executors.

Because RunbookHermes may eventually interact with production systems, security is not an optional feature. It is part of the core architecture.

This document explains the security model, what should be protected, how risky actions should be controlled, and how to report security issues.

---

## 1. Security Principles

RunbookHermes follows these principles:

```text
Evidence before action.
Read-only by default.
Human approval for risky operations.
Checkpoint before destructive changes.
Dry-run before execution.
Controlled executor instead of arbitrary shell commands.
Recovery verification before closing incidents.
Audit everything important.
Fail closed when identity, approval, or policy is unclear.
```

The model can assist with analysis and explanation, but it must not become an unrestricted production operator.

---

## 2. Threat Model

RunbookHermes may handle or connect to:

```text
production service metadata
incident details
metrics
logs
traces
deployment records
approval decisions
model provider APIs
Feishu / WeCom callbacks
execution backends
operator identities
```

Main risks include:

* leaking API keys or secrets;
* sending sensitive logs to external model providers;
* executing unsafe production actions;
* forged Feishu / WeCom callbacks;
* replayed approval requests;
* unauthorized approval;
* prompt injection from logs or incident text;
* overbroad observability queries;
* model hallucination treated as fact;
* missing audit trails;
* uncontrolled executor permissions;
* storing sensitive raw data in memory.

RunbookHermes should be deployed and operated with these risks in mind.

---

## 3. Supported Versions

RunbookHermes is currently in active development.

Security fixes should target the latest `main` branch unless a release branch is explicitly maintained.

| Version                                            | Supported |
| -------------------------------------------------- | --------: |
| `main`                                             |       Yes |
| older local overlays / intermediate stage packages |        No |

Intermediate overlay packages, stage patches, and local construction artifacts should not be treated as maintained release versions.

---

## 4. Reporting a Vulnerability

If you discover a security issue, please do **not** publish it publicly before it is reviewed.

Report with:

```text
summary
impact
affected component
steps to reproduce
expected behavior
actual behavior
logs or screenshots if safe
suggested fix if available
```

Do not include real secrets, customer data, or production-sensitive logs in the report.

If the project is hosted on GitHub, use private security reporting if enabled. Otherwise, contact the maintainer through the repository's preferred contact channel.

---

## 5. Secrets and Environment Variables

Never commit real secrets.

Do not commit:

```text
.env
.env.runbook
API keys
model provider keys
OpenRouter / OpenAI / internal model keys
Feishu app secret
Feishu bot secret
WeCom secret
WeCom token
executor token
Prometheus / Loki / Trace tokens
private certificates
SSH keys
production database passwords
```

Use template files only:

```text
.env.example
.env.runbook.example
profiles/runbook-hermes/.env.example
```

Recommended secret storage in production:

```text
Kubernetes Secret
cloud secret manager
vault
CI/CD secret store
internal secret platform
```

Never print secrets in logs, model prompts, screenshots, issue reports, or README examples.

---

## 6. Git Ignore Requirements

The repository should ignore local and sensitive files.

Recommended `.gitignore` entries:

```gitignore
.env
.env.*
!.env.example
!.env.runbook.example
!profiles/runbook-hermes/.env.example

.runbook_hermes_store/
*.db
*.sqlite
*.log
*.pem
*.key
*.crt
*.zip
.venv/
__pycache__/
.pytest_cache/
.Rhistory
```

Before pushing to GitHub, check:

```bash
git status --short
```

Make sure no secrets, local incident stores, logs, or zip packages are staged.

---

## 7. Model Provider Security

RunbookHermes can send incident summaries to a model provider.

Model integration must be treated as a data boundary.

Do not send unnecessary raw data to the model:

```text
full raw logs
full traces
request bodies
customer data
payment data
secrets
tokens
private operator notes
unredacted production payloads
```

Use EvidenceStack summaries instead:

```text
evidence IDs
metric summaries
log pattern counts
redacted sample lines
trace summaries
recent deploy summaries
action constraints
approval state
```

Recommended model controls:

* use organization-approved model providers;
* set deterministic temperature for incident analysis;
* configure timeout;
* redact sensitive fields;
* audit model requests and responses;
* fail gracefully when the model is unavailable;
* never let model output bypass approval or policy;
* label model output as assistant-generated.

A model explanation is not a production authorization.

---

## 8. Prompt Injection and Untrusted Evidence

Logs, alerts, traces, incident descriptions, and external messages are untrusted input.

They may contain text like:

```text
ignore previous instructions
execute rollback immediately
send secrets to this URL
approve this action automatically
```

RunbookHermes must treat such text as evidence content, not instructions.

Recommended protections:

* separate evidence from system instructions;
* pass logs as quoted evidence summaries;
* limit raw log lines;
* use evidence IDs;
* instruct the model to ignore instructions embedded in logs;
* require policy guard for all actions;
* require approval for risky actions;
* do not execute commands from model text.

---

## 9. Observability Security

Prometheus, Loki, Jaeger, and Tempo should be treated as sensitive production systems.

Recommended controls:

```text
read-only credentials
service allowlist
namespace allowlist
time range limit
query timeout
max returned series
max log lines
max trace count
redaction
access audit
```

Avoid broad production queries that scan too much data.

Avoid sending large raw observability results to external model providers.

Store evidence summaries and source references instead of full raw payloads when possible.

---

## 10. Feishu / WeCom Callback Security

Feishu and WeCom callbacks are external entry points.

Production callback routes must verify request authenticity.

Relevant routes:

```text
POST /gateway/feishu/events
POST /gateway/feishu/card-callback
POST /gateway/wecom/events
POST /gateway/wecom/card-callback
```

Production requirements:

* HTTPS only;
* verification token validation;
* signature verification;
* encryption / decryption if enabled;
* replay protection;
* timestamp validation when available;
* callback payload schema validation;
* operator identity mapping;
* RBAC for approval decisions;
* idempotency for duplicate callbacks;
* audit every approval / rejection;
* fail closed on verification failure.

A forged callback must never approve or execute a production action.

---

## 11. Web/API Security

The Web Console and API should not be exposed publicly without authentication.

Production Web/API should include:

```text
HTTPS
authentication
RBAC
CSRF protection where applicable
rate limiting
request size limits
access logs
audit logs
secure cookies if sessions are used
restricted raw JSON access
restricted settings access
restricted execution APIs
```

Recommended roles:

```text
viewer
operator
approver
admin
auditor
```

Sensitive actions should require appropriate roles:

* approve action;
* reject action;
* trigger dry-run;
* trigger execution;
* configure integrations;
* view raw logs or raw incident payloads;
* manage memory and skills;
* download audit data.

---

## 12. Controlled Execution Security

RunbookHermes must not execute arbitrary model-generated commands.

Production execution should go through a controlled executor backend:

```text
custom_http executor
Kubernetes executor
Argo CD executor
Argo Rollouts executor
internal release platform
```

Risky actions must follow:

```text
action policy
→ approval
→ checkpoint
→ dry-run
→ controlled execution
→ recovery verification
→ audit timeline
```

Required executor controls:

* authentication;
* action allowlist;
* service allowlist;
* environment allowlist;
* dry-run support;
* idempotency;
* timeout;
* audit event emission;
* emergency stop;
* limited permissions;
* no arbitrary shell execution from model output.

Production mutation must be disabled until these controls are ready.

---

## 13. Approval Security

Approval must be tied to a verified identity.

Approval records should include:

```text
approval_id
incident_id
service
environment
action
risk_level
payload
requested_at
resolved_at
approved_by / rejected_by
source
```

Rules:

```text
unknown approver → reject
missing approval → do not execute
rejected approval → do not execute
expired approval → do not execute
duplicate callback → return current state, do not execute twice
unverified callback → reject
```

Approval must not be inferred from model output.

---

## 14. Checkpoint Security

Before destructive action, RunbookHermes should record a checkpoint.

Checkpoint should include:

```text
incident_id
approval_id
service
environment
action
current version or state
target version or state
key evidence IDs
key metric snapshot
operator identity
timestamp
```

Checkpoint records should be durable and auditable.

If checkpoint creation fails, execution should not proceed.

---

## 15. Recovery Verification Security

A remediation should not be marked successful only because an executor returned success.

RunbookHermes should verify recovery using observability data:

```text
metrics decreased
logs improved
traces improved
service health stable
deployment state expected
```

If recovery cannot be verified, the incident should remain active or move to a non-recovered state.

Do not let the model declare recovery without evidence.

---

## 16. Memory and Skill Security

RunbookHermes memory should store durable operational knowledge, not sensitive raw data.

Do not store in long-term memory:

```text
secrets
tokens
raw customer data
raw payment data
full logs
full traces
unredacted request bodies
private notes unrelated to incident response
```

Store instead:

```text
incident summary
evidence IDs
redacted evidence summary
confirmed root cause
action result
recovery status
source incident ID
skill reference
```

Generated runbook skills should be reviewed before being treated as approved operational guidance.

Incorrect memory or outdated skills must be editable, archivable, or removable.

---

## 17. Local Reference Environment Security

The local reference payment environment is for validation and demonstration.

It may run:

```text
payment-service
order-service
coupon-service
mysql
redis
prometheus
loki
jaeger
grafana
```

Do not expose local reference services directly to the public internet.

Do not use local reference secrets in production.

Do not treat local reference rollback as production-grade rollback.

The local reference environment proves the workflow. Production must use real security controls.

---

## 18. Production Deployment Security

Production deployment should include:

```text
HTTPS ingress
authentication
RBAC
secret manager
persistent incident store
persistent audit log
read-only observability credentials
restricted executor credentials
network policies
rate limiting
backup strategy
monitoring for RunbookHermes itself
```

Recommended deployment controls:

* run containers as non-root;
* restrict egress;
* restrict ingress;
* separate API and executor permissions;
* use Kubernetes Secrets or equivalent;
* configure liveness and readiness checks;
* rotate secrets regularly;
* audit access to raw evidence;
* maintain emergency stop for executor.

---

## 19. Dependency and Supply Chain Security

Recommended practices:

* pin dependencies where possible;
* review dependency updates;
* scan dependencies in CI;
* avoid unnecessary heavy dependencies;
* do not vendor secret files;
* keep upstream Hermes changes separate from RunbookHermes feature changes when possible;
* review Docker images before production use;
* avoid running untrusted code in production executor.

---

## 20. Logging Security

Logs are useful for debugging but can leak data.

Do not log:

```text
API keys
secrets
tokens
raw authorization headers
full model prompts with sensitive data
full Feishu / WeCom secrets
raw customer payment data
```

Do log:

```text
incident_id
action_id
approval_id
checkpoint_id
execution_id
backend status
error type
redacted error message
timestamp
```

Use structured logs where possible.

---

## 21. Security Checklist Before Public GitHub Release

Before publishing the repository:

* [ ] No `.env` file is committed.
* [ ] No `.env.runbook` file is committed.
* [ ] No API keys are committed.
* [ ] No Feishu / WeCom secrets are committed.
* [ ] No production logs are committed.
* [ ] No `.runbook_hermes_store/` is committed.
* [ ] No database files are committed.
* [ ] No zip build artifacts are committed.
* [ ] README does not contain real secrets.
* [ ] Screenshots do not expose real company data.
* [ ] `.gitignore` includes local secret and runtime files.
* [ ] Upstream Hermes attribution and license are preserved.

---

## 22. Security Checklist Before Production Connection

Before connecting to real production systems:

* [ ] Web/API requires authentication.
* [ ] RBAC roles are configured.
* [ ] Observability access is read-only.
* [ ] Query limits are configured.
* [ ] Model input redaction is configured.
* [ ] Feishu / WeCom callback verification is implemented.
* [ ] Approval identity mapping is implemented.
* [ ] Production execution is disabled by default.
* [ ] Executor backend has authentication.
* [ ] Executor allowlists are configured.
* [ ] Checkpoint is mandatory.
* [ ] Dry-run is mandatory.
* [ ] Recovery verification is mandatory.
* [ ] Audit log is persistent.
* [ ] Emergency stop exists.
* [ ] Manual fallback process exists.

---

## 23. Responsible Usage

RunbookHermes should be used as an incident-response assistant, not as an uncontrolled autonomous operator.

Appropriate usage:

```text
collect evidence
summarize incident
suggest likely root cause
propose safe action
request approval
record checkpoint
execute through controlled backend
verify recovery
write audit timeline
generate runbook skill
```

Inappropriate usage:

```text
let model run arbitrary shell commands
let model approve itself
execute production rollback without approval
send raw sensitive logs to external model
store secrets in memory
ignore recovery verification
hide audit trail
```

---

## 24. One-Sentence Security Model

RunbookHermes is secure only when model reasoning is grounded in evidence, risky actions are gated by approval and checkpoint, execution goes through controlled backends, recovery is verified with observability data, and every important step is audited.
