# Approval, Checkpoint, and Recovery Verification

This document explains the safety operating model of RunbookHermes: how risky actions are reviewed, approved, checkpointed, executed, verified, and audited.

RunbookHermes is designed for production-oriented incident response. It should not behave like an uncontrolled automation bot. Even when the root cause is clear and an action looks correct, the system should preserve human control, operational traceability, and recovery verification.

---

## 1. Why This Layer Exists

Incident-response agents can be dangerous if they directly mutate production systems.

Examples of risky actions:

```text
rollback service
restart service
scale deployment
change traffic route
change feature flag
mutate config
trigger deploy
clear cache
fail over dependency
run database-affecting operation
```

RunbookHermes treats these actions as controlled operations.

The safety chain is:

```text
evidence
→ hypothesis
→ action proposal
→ risk classification
→ approval
→ checkpoint
→ dry-run
→ controlled execution
→ recovery verification
→ audit timeline
```

This chain is one of the key differences between RunbookHermes and a simple script-based incident bot.

---

## 2. Core Principle

The model can assist reasoning, but it cannot grant permission.

RunbookHermes follows this rule:

```text
The model may explain and recommend.
The policy layer classifies risk.
The approver grants permission.
The checkpoint records pre-action state.
The executor performs only approved actions.
The observability layer verifies recovery.
The timeline records everything.
```

A model-generated answer is not enough to execute production changes.

---

## 3. End-to-End Safety Flow

Typical flow for a payment-service HTTP 503 incident:

```text
1. Alert enters RunbookHermes.
2. RunbookHermes creates an incident.
3. Observability tools collect metrics, logs, traces, and deploy evidence.
4. EvidenceStack compresses evidence into a traceable context.
5. Root-cause hypothesis is generated.
6. Action plan is proposed.
7. Action policy classifies rollback as destructive.
8. Approval request is created.
9. Operator approves or rejects.
10. If approved, checkpoint is created.
11. Dry-run validates the action.
12. Controlled executor performs the action.
13. Recovery verification checks metrics, logs, traces, and deployment status.
14. Incident timeline records the full lifecycle.
15. Runbook skill may be generated or updated.
```

This gives operators a clear path from evidence to action, without hiding operational risk.

---

## 4. Action Risk Classification

Before approval, RunbookHermes should classify the action risk.

Recommended classes:

```text
read_only
write_safe
write_risky
destructive
```

### 4.1 Read-Only

Examples:

```text
Prometheus query
Loki query
Trace search
Deploy history lookup
Incident detail read
```

Approval usually not required.

### 4.2 Write-Safe

Examples:

```text
generate postmortem draft
create internal note
generate runbook skill draft
create non-production ticket
```

Approval may not be required, depending on company policy.

### 4.3 Write-Risky

Examples:

```text
restart canary instance
scale non-critical deployment
change staging route
trigger dry-run deploy action
```

Approval recommended.

### 4.4 Destructive

Examples:

```text
rollback production service
restart production service
change production traffic route
mutate production config
trigger production deployment
run database-affecting operation
```

Approval required.

Fail-closed rule:

```text
If RunbookHermes cannot classify an action safely, treat it as risky or destructive.
```

---

## 5. Approval Model

Approval is the human-in-the-loop control point.

Approval can be performed through:

```text
Web Console
Feishu card callback
WeCom card callback
internal approval API
```

Approval should never be a vague yes/no without context. Operators need enough information to make a safe decision.

Approval record should include:

```text
approval_id
incident_id
service
environment
action
risk_level
reason
recommended_by
payload
status
created_at
resolved_at
approved_by / rejected_by
```

Approval statuses:

```text
pending
approved
rejected
expired
cancelled
```

---

## 6. Approval Request Content

A good approval request should show:

```text
Incident ID
Service
Environment
Severity
Current status
Most likely root cause
Evidence IDs
Recommended action
Risk level
Why approval is required
Expected impact
Checkpoint summary
Dry-run requirement
Link to Web Console
```

Example:

```text
Incident: inc_510364
Service: payment-service
Environment: prod
Severity: p1

Root cause:
payment-service v2.3.1 likely introduced database connection pool regression.

Evidence:
- ev_metric_http_503_rate: HTTP 503 rate increased
- ev_log_connection_pool: connection pool exhausted repeated
- ev_trace_mysql_latency: mysql-payment latency increased
- ev_deploy_v231: v2.3.1 deployed recently

Recommended action:
Rollback payment-service from v2.3.1 to v2.3.0.

Risk:
Destructive production action.

Safety:
Approval + checkpoint + dry-run + recovery verification required.
```

---

## 7. Approval Decision Rules

### 7.1 Approved

If approved:

```text
approval.resolved recorded
checkpoint created
execution may proceed to dry-run
operator identity recorded
```

### 7.2 Rejected

If rejected:

```text
approval.resolved recorded
execution is blocked
incident remains open or action is marked rejected
operator may add reason
```

### 7.3 Expired

If approval expires:

```text
execution is blocked
new approval required
incident timeline records expiration
```

### 7.4 Unknown or Invalid Approval

If approval ID is unknown or invalid:

```text
execution is blocked
security event or malformed callback is recorded
operator is asked to use Web Console
```

### 7.5 Duplicate Approval Callback

If the same approval callback is received twice:

```text
return current state
avoid double execution
record duplicate only if useful
```

---

## 8. Checkpoint Model

A checkpoint records the pre-action state before a risky operation.

Checkpoint is not only a backup. It is an operational audit snapshot.

Checkpoint should include:

```text
checkpoint_id
incident_id
approval_id
service
environment
action
current_version
target_version
current_deploy_state
key_metric_snapshot
key_log_summary
key_trace_summary
evidence_ids
operator_identity
created_at
```

Example rollback checkpoint:

```json
{
  "checkpoint_id": "chk_123",
  "incident_id": "inc_510364",
  "approval_id": "appr_456",
  "service": "payment-service",
  "environment": "prod",
  "action": "rollback",
  "current_version": "v2.3.1",
  "target_version": "v2.3.0",
  "evidence_ids": [
    "ev_metric_http_503_rate",
    "ev_log_connection_pool",
    "ev_trace_mysql_latency",
    "ev_deploy_v231"
  ]
}
```

---

## 9. Why Checkpoints Matter

Checkpoints help answer:

```text
What was the service state before action?
What version was running?
What action was approved?
Who approved it?
What evidence justified the action?
What metrics looked bad before execution?
What should recovery verification compare against?
```

If execution fails or makes the incident worse, the checkpoint provides the context needed for manual investigation and rollback failure handling.

---

## 10. Dry-Run Model

Dry-run validates that an action can be performed before executing it.

Dry-run should check:

```text
service exists
environment is allowed
action is allowed
target version exists
current version matches expected state
executor can reach deploy system
no conflicting deployment is running
approval is valid
checkpoint exists
operator has permission
```

Dry-run should return structured output:

```json
{
  "ok": true,
  "service": "payment-service",
  "environment": "prod",
  "action": "rollback",
  "current_version": "v2.3.1",
  "target_version": "v2.3.0",
  "warnings": [],
  "estimated_impact": "payment-service will roll back to v2.3.0"
}
```

If dry-run fails, execution must stop.

---

## 11. Controlled Execution

Controlled execution means RunbookHermes does not run arbitrary model-generated commands.

Instead, it calls a structured executor backend:

```text
custom_http executor
Kubernetes executor
Argo CD executor
Argo Rollouts executor
internal release platform executor
```

Execution request should include:

```text
incident_id
approval_id
checkpoint_id
service
environment
action
target_version or target_state
evidence_ids
approved_by
reason
```

The executor should enforce:

```text
action allowlist
service allowlist
environment allowlist
RBAC
dry-run requirement
idempotency
timeout
audit
emergency stop
```

---

## 12. Recovery Verification

Execution is not complete until recovery is verified.

RunbookHermes should check the same observability systems used for evidence collection:

```text
Prometheus
Loki
Jaeger / Tempo
Deploy history
service health endpoint
```

Recovery checks may include:

```text
HTTP 503 rate decreased
HTTP 504 rate decreased
HTTP 429 rate decreased
p95 latency normalized
QPS stable
error log pattern decreased
trace errors decreased
new version active
service health stable
```

Example:

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

If recovery is not verified, the incident should remain active.

---

## 13. Recovery States

Recommended recovery states:

```text
not_started
checking
verified
not_verified
failed
unknown
```

### 13.1 Verified

Meaning:

```text
metrics, logs, traces, or deploy state indicate that the incident recovered.
```

### 13.2 Not Verified

Meaning:

```text
action completed, but recovery evidence is insufficient or negative.
```

### 13.3 Failed

Meaning:

```text
recovery check failed due to backend error or execution failure.
```

### 13.4 Unknown

Meaning:

```text
not enough evidence to decide.
```

Do not mark an incident as recovered when the state is unknown.

---

## 14. Timeline and Audit Events

RunbookHermes should record all important state transitions.

Recommended timeline events:

```text
incident.created
gateway.alertmanager.received
gateway.feishu.received
gateway.wecom.received
evidence.collected
hypothesis.generated
action.planned
action.classified
approval.requested
approval.resolved
checkpoint.created
dry_run.started
dry_run.completed
dry_run.failed
action.execution_requested
action.executed
action.failed
recovery.verification_started
recovery.verified
recovery.failed
skill.generated
```

Each event should include:

```text
incident_id
service
environment
actor
source
action
risk_level
approval_id
checkpoint_id
execution_id
evidence_ids
result
error
timestamp
```

---

## 15. Web Console Mapping

The Web Console should expose the safety chain clearly.

### Incident Detail

Should show:

```text
summary
evidence cards
root cause
action plan
approval status
checkpoint details
timeline
recovery verification
raw JSON
```

### Approval Center

Should show:

```text
pending approvals
risk level
reason
payload
checkpoint
approve / reject buttons
```

### Monitoring Page

Should show:

```text
service health
HTTP status signals
QPS
p95 latency
log signals
trace signals
deploy state
```

### Settings Page

Should show integration readiness:

```text
model provider
Prometheus
Loki
Trace
Feishu
WeCom
execution backend
controlled execution
```

---

## 16. Feishu / WeCom Mapping

Feishu / WeCom approval cards should expose the same safety information as Web Console.

Recommended card sections:

```text
Incident summary
Root cause
Evidence IDs
Recommended action
Risk level
Why approval is required
Checkpoint summary
Buttons: Approve / Reject / Open Console
```

After an operator clicks approve or reject:

```text
callback is verified
approval decision is recorded
incident timeline is updated
execution proceeds only if approved
```

---

## 17. Failure Handling

### 17.1 Approval Missing

```text
do not execute
return approval_required
record event
```

### 17.2 Approval Rejected

```text
do not execute
record rejected state
optionally ask for operator comment
```

### 17.3 Checkpoint Creation Fails

```text
do not execute
record checkpoint failure
ask operator to retry or escalate
```

### 17.4 Dry-Run Fails

```text
do not execute
show dry-run error
record event
suggest manual escalation
```

### 17.5 Execution Fails

```text
record action.failed
show executor error
run verification if partial execution happened
escalate to owner
```

### 17.6 Recovery Verification Fails

```text
keep incident active
record recovery.failed
suggest next investigation steps
```

### 17.7 Observability Backend Unavailable

```text
record backend failure
continue with available evidence
lower confidence
avoid declaring recovery
```

---

## 18. Idempotency

Approval callbacks and execution requests can be duplicated.

RunbookHermes should be idempotent for:

```text
approval decision
checkpoint creation
execution request
recovery verification
```

Recommended idempotency key:

```text
incident_id + approval_id + action + target_state
```

Duplicate requests should return existing state instead of repeating execution.

---

## 19. Local Reference Behavior

In the local reference environment, RunbookHermes may perform controlled file-based rollback.

Example:

```text
data/payment_demo/runtime/payment-service-version.txt
v2.3.1 → v2.3.0
```

This local reference flow proves:

```text
approval works
checkpoint works
execution boundary works
recovery verification works
timeline works
```

It is not the same as production mutation.

Production mutation should go through a controlled executor backend.

---

## 20. Production Behavior

In production, RunbookHermes should not directly edit files or run arbitrary shell commands.

It should call:

```text
custom_http executor
Kubernetes executor
Argo CD executor
Argo Rollouts executor
internal release platform
```

Production execution requires:

```text
identity verification
RBAC
approval
checkpoint
dry-run
allowlist
audit
recovery verification
emergency stop
```

---

## 21. Operating Procedures

### 21.1 Operator Procedure for Risky Action

1. Open incident detail.
2. Review evidence.
3. Review root-cause hypothesis.
4. Review recommended action.
5. Confirm risk level.
6. Check checkpoint summary.
7. Approve or reject.
8. Monitor dry-run result.
9. Monitor execution result.
10. Verify recovery.
11. Add manual notes if needed.

### 21.2 Approver Procedure

Approver should ask:

```text
Is the root cause supported by evidence?
Is the recommended action appropriate?
Is the target version / target state correct?
Is the blast radius acceptable?
Is there a checkpoint?
Is dry-run available?
Is recovery verification defined?
```

### 21.3 SRE / Platform Owner Procedure

SRE / platform owner should review:

```text
executor failures
approval latency
false positive root causes
missing evidence
failed recovery checks
repeated incident categories
generated runbook skills
```

---

## 22. Production Readiness Checklist

Before enabling controlled production execution:

* [ ] Destructive actions require approval.
* [ ] Approval identity is verified.
* [ ] Approval decision is audited.
* [ ] Checkpoint creation is mandatory.
* [ ] Dry-run is mandatory.
* [ ] Executor backend is controlled and authenticated.
* [ ] Service allowlist is configured.
* [ ] Environment allowlist is configured.
* [ ] Executor is idempotent.
* [ ] Recovery verification is implemented.
* [ ] Audit timeline is persistent.
* [ ] Emergency stop exists.
* [ ] Manual fallback runbook exists.
* [ ] Model output cannot bypass controls.
* [ ] Sensitive evidence is redacted.
* [ ] Operators are trained on approval flow.

---

## 23. Common Anti-Patterns

Avoid these patterns:

```text
Model directly executes rollback.
Approval without evidence.
Approval without checkpoint.
Checkpoint without useful pre-action state.
Execution without dry-run.
Marking incident recovered without verification.
Sending raw logs to model unnecessarily.
Using broad production credentials.
Running arbitrary shell commands from model output.
No audit trail.
No duplicate callback handling.
```

These patterns make an incident-response agent unsafe.

---

## 24. Example: payment-service HTTP 503

Incident:

```text
payment-service HTTP 503 rate increased after v2.3.1 release
```

Evidence:

```text
Prometheus: HTTP 503 rate increased
Loki: connection pool exhausted repeated
Jaeger: payment-service → mysql-payment latency increased
Deploy: v2.3.1 released recently
```

Hypothesis:

```text
v2.3.1 introduced database connection pool regression
```

Action:

```text
rollback payment-service to v2.3.0
```

Risk:

```text
destructive
```

Safety flow:

```text
approval requested
→ approval granted
→ checkpoint created
→ dry-run passed
→ rollback executed
→ HTTP 503 decreased
→ recovery verified
→ skill generated
```

---

## 25. One-Sentence Summary

Approval, checkpoint, dry-run, controlled execution, recovery verification, and audit are the safety chain that allows RunbookHermes to move from evidence-based recommendation toward production-oriented remediation without becoming an uncontrolled automation bot.
