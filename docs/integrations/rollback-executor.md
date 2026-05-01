# Rollback Executor Integration

This document explains how RunbookHermes connects to controlled remediation systems such as custom HTTP executors, Kubernetes, Argo CD, Argo Rollouts, or an internal release platform.

Rollback and remediation are the most sensitive parts of RunbookHermes. The purpose of this integration is **not** to let an AI model freely mutate production. The purpose is to put dangerous actions behind policy, approval, checkpoint, dry-run, controlled execution, recovery verification, and audit.

---

## 1. Integration Goal

A production-ready executor integration should support this workflow:

```text
root-cause hypothesis
→ action proposal
→ risk classification
→ approval request
→ checkpoint creation
→ dry-run
→ controlled execution
→ recovery verification
→ audit timeline
```

For example:

```text
payment-service HTTP 503 increased after v2.3.1 release
→ evidence points to database connection pool regression
→ proposed action: rollback payment-service to v2.3.0
→ action is destructive
→ approval required
→ checkpoint created
→ dry-run validates rollback plan
→ executor performs rollback
→ Prometheus / Loki / Trace verify recovery
→ incident timeline records result
```

---

## 2. Files Involved

Rollback and controlled execution logic is mainly located in:

```text
runbook_hermes/tools.py
runbook_hermes/approval.py
runbook_hermes/execution.py
runbook_hermes/action_policy.py
runbook_hermes/backends.py
runbook_hermes/incident_service.py
integrations/observability/deploy_backend.py
plugins/runbook-hermes/__init__.py
plugins/runbook-hermes/plugin.yaml
```

Related Web/API files:

```text
apps/runbook_api/app/main.py
web/static/incident.html
web/static/approvals.html
```

Related data files for local reference execution:

```text
data/payment_demo/deployments.json
data/payment_demo/runtime/payment-service-version.txt
```

---

## 3. Executor Types

RunbookHermes supports the concept of multiple executor backends.

Recommended executor types:

```text
none
custom_http
kubernetes
argocd
argo_rollouts
internal_release_platform
```

### 3.1 `none`

Default safe mode.

No production mutation is performed.

Use this when:

* you are opening the Web Console;
* you are reviewing incidents;
* you are connecting observability read-only;
* production execution is not approved yet.

### 3.2 `demo_file`

Local reference execution mode.

This mode only mutates local reference files such as:

```text
data/payment_demo/runtime/payment-service-version.txt
```

Use this to validate the approval → checkpoint → execution → recovery flow locally.

### 3.3 `custom_http`

Recommended first production-style executor.

RunbookHermes sends a structured execution request to a controlled internal remediation service.

This service can then call Kubernetes, Argo, internal release systems, or other production systems according to company policy.

### 3.4 `kubernetes`

Direct Kubernetes execution adapter.

Use only when RBAC, namespace allowlist, service allowlist, and audit are ready.

### 3.5 `argocd` / `argo_rollouts`

GitOps / progressive delivery executor.

Recommended for teams that already use Argo CD or Argo Rollouts.

### 3.6 Internal Release Platform

Many companies already have a release platform.

In that case, RunbookHermes should integrate with that platform instead of bypassing it.

---

## 4. Environment Variables

### 4.1 Global Execution Control

```bash
RUNBOOK_CONTROLLED_EXECUTION_ENABLED=true
```

If this is not enabled, RunbookHermes should not perform controlled execution.

### 4.2 Executor Backend

```bash
ACTION_EXECUTION_BACKEND=custom_http
ACTION_EXECUTION_API_BASE_URL=https://executor.example.com
ACTION_EXECUTION_API_TOKEN=your_token
ACTION_EXECUTION_TIMEOUT_SECONDS=5
```

On Windows Anaconda Prompt:

```bat
set RUNBOOK_CONTROLLED_EXECUTION_ENABLED=true
set ACTION_EXECUTION_BACKEND=custom_http
set ACTION_EXECUTION_API_BASE_URL=https://executor.example.com
set ACTION_EXECUTION_API_TOKEN=your_token
set ACTION_EXECUTION_TIMEOUT_SECONDS=5
```

### 4.3 Local Reference Rollback

```bat
set ROLLBACK_BACKEND_KIND=demo_file
set DEMO_DEPLOY_STATE_FILE=data/payment_demo/deployments.json
set DEMO_VERSION_FILE=data/payment_demo/runtime/payment-service-version.txt
set RUNBOOK_CONTROLLED_EXECUTION_ENABLED=true
```

---

## 5. Safety Model

RunbookHermes should never treat model output as permission to execute.

The safety model is:

```text
model can explain
model can recommend
policy classifies risk
human approves
checkpoint records pre-action state
executor performs only approved action
evidence verifies recovery
audit records everything
```

Dangerous actions include:

* rollback;
* restart;
* scaling mutation;
* traffic route change;
* configuration mutation;
* deployment mutation;
* database-affecting operation;
* cache flush;
* feature flag change;
* dependency failover.

These should require explicit approval and checkpoint.

---

## 6. Action Risk Classification

RunbookHermes should classify actions before execution.

Recommended risk classes:

```text
read_only
write_safe
write_risky
destructive
```

Examples:

| Action                    | Risk class  | Approval required |
| ------------------------- | ----------- | ----------------- |
| Prometheus query          | read_only   | No                |
| Loki query                | read_only   | No                |
| Trace search              | read_only   | No                |
| Generate postmortem draft | write_safe  | Usually no        |
| Create ticket             | write_safe  | Usually no        |
| Restart canary pod        | write_risky | Yes               |
| Change traffic route      | write_risky | Yes               |
| Rollback payment-service  | destructive | Yes               |
| Mutate database           | destructive | Yes               |

The action policy should fail closed when it cannot classify the risk.

---

## 7. Approval Flow

A risky action should create an approval request.

Approval record should include:

```text
approval_id
incident_id
service
environment
action
risk_level
reason
payload
checkpoint_id if available
created_at
status
requested_by
approved_by / rejected_by
```

Approval can be resolved through:

* Web Console;
* Feishu card callback;
* WeCom card callback;
* internal approval API.

Approval states:

```text
pending
approved
rejected
expired
cancelled
```

Fail-closed rule:

```text
If approval is missing, expired, rejected, or cannot be verified, do not execute.
```

---

## 8. Checkpoint Flow

Before executing a risky action, RunbookHermes should create a checkpoint.

Checkpoint should include:

```text
checkpoint_id
incident_id
service
environment
action
current_version
target_version
current_deploy_state
key_metrics_snapshot
key_log_summary
key_trace_summary
operator_identity
approval_id
created_at
```

Purpose:

```text
If the action fails or worsens the incident, operators can inspect what the system looked like before execution.
```

For rollback:

```text
current_version: v2.3.1
target_version: v2.3.0
```

For scaling:

```text
current_replicas: 3
target_replicas: 6
```

For route mutation:

```text
current_weight: stable 90 / canary 10
target_weight: stable 100 / canary 0
```

---

## 9. Dry-Run Flow

Dry-run should happen before execution.

A dry-run should validate:

```text
service exists
environment is allowed
action is allowed
target version exists
current version matches expectation
executor can reach deploy system
no conflicting deployment is running
operator has approval
rollback path exists
```

Dry-run result example:

```json
{
  "ok": true,
  "service": "payment-service",
  "environment": "prod",
  "action": "rollback",
  "current_version": "v2.3.1",
  "target_version": "v2.3.0",
  "warnings": [],
  "estimated_impact": "payment-service pods will roll back to v2.3.0"
}
```

If dry-run fails, execution should stop.

---

## 10. Controlled Execution Flow

Execution request should be structured.

Recommended request shape:

```json
{
  "incident_id": "inc_xxxxxx",
  "approval_id": "appr_xxxxxx",
  "checkpoint_id": "chk_xxxxxx",
  "service": "payment-service",
  "environment": "prod",
  "action": "rollback",
  "target_version": "v2.3.0",
  "requested_by": "runbookhermes",
  "approved_by": "operator@example.com",
  "reason": "HTTP 503 spike after v2.3.1 deployment with DB connection pool evidence",
  "evidence_ids": [
    "ev_metric_http_503_rate",
    "ev_log_connection_pool",
    "ev_trace_mysql_latency",
    "ev_deploy_v231"
  ],
  "dry_run": false
}
```

The executor response should be structured:

```json
{
  "ok": true,
  "execution_id": "exec_xxxxxx",
  "status": "started",
  "service": "payment-service",
  "environment": "prod",
  "action": "rollback",
  "target_version": "v2.3.0",
  "message": "Rollback started"
}
```

---

## 11. Custom HTTP Executor

The recommended first production-style executor is `custom_http`.

RunbookHermes sends execution requests to an internal service controlled by your platform team.

Suggested endpoints:

```text
POST /dry-run
POST /execute
GET  /executions/{execution_id}
POST /cancel
```

### 11.1 Dry-Run Request

```http
POST /dry-run
Authorization: Bearer <token>
Content-Type: application/json
```

Payload:

```json
{
  "incident_id": "inc_xxxxxx",
  "approval_id": "appr_xxxxxx",
  "service": "payment-service",
  "environment": "prod",
  "action": "rollback",
  "target_version": "v2.3.0",
  "evidence_ids": ["ev_metric_http_503_rate"]
}
```

### 11.2 Execute Request

```http
POST /execute
Authorization: Bearer <token>
Content-Type: application/json
```

Payload:

```json
{
  "incident_id": "inc_xxxxxx",
  "approval_id": "appr_xxxxxx",
  "checkpoint_id": "chk_xxxxxx",
  "service": "payment-service",
  "environment": "prod",
  "action": "rollback",
  "target_version": "v2.3.0"
}
```

### 11.3 Executor Responsibilities

The executor should enforce:

* action allowlist;
* service allowlist;
* environment allowlist;
* approval verification;
* dry-run requirement;
* idempotency;
* timeout;
* audit;
* rollback failure handling;
* emergency stop.

RunbookHermes proposes and coordinates. The executor owns production mutation safety.

---

## 12. Kubernetes Executor

A Kubernetes executor may support actions such as:

```text
rollout undo
scale deployment
restart deployment
patch config reference
shift traffic if service mesh is used
```

Recommended controls:

```text
namespace allowlist
service allowlist
verb allowlist
resource allowlist
server-side dry-run
RBAC-limited service account
audit logging
change ticket / approval binding
```

Example conceptual action:

```text
kubectl rollout undo deployment/payment-service -n payments --to-revision=12
```

RunbookHermes should not run arbitrary `kubectl` commands generated by a model.

It should call a structured executor API that maps approved actions to safe Kubernetes operations.

---

## 13. Argo CD / Argo Rollouts Executor

If your release system uses Argo, executor actions may include:

```text
sync application to previous revision
rollback application
promote rollout
abort rollout
set canary weight
pause rollout
resume rollout
```

Recommended controls:

```text
application allowlist
project allowlist
environment allowlist
revision validation
approval binding
dry-run or diff before sync
audit event
post-action health check
```

Argo-based remediation should still be treated as controlled execution.

---

## 14. Internal Release Platform Executor

Many companies already have an internal release platform.

This is often the safest production target.

RunbookHermes should call the internal platform instead of bypassing it.

Recommended API shape:

```text
POST /releases/dry-run
POST /releases/rollback
GET  /releases/{execution_id}
POST /releases/{execution_id}/cancel
```

The internal platform should own:

* deployment permission;
* release policy;
* service ownership;
* rollout strategy;
* deployment audit;
* rollback implementation;
* notification;
* production guardrails.

RunbookHermes owns:

* evidence collection;
* root-cause hypothesis;
* recommendation;
* approval coordination;
* checkpoint summary;
* recovery verification;
* incident timeline.

---

## 15. Local Reference Rollback

The local reference rollback is intentionally simple.

It may update:

```text
data/payment_demo/runtime/payment-service-version.txt
```

from:

```text
v2.3.1
```

to:

```text
v2.3.0
```

and update:

```text
data/payment_demo/deployments.json
```

This proves the control flow:

```text
approval
→ checkpoint
→ controlled execution boundary
→ recovery verification
```

It is not the final production executor.

---

## 16. Recovery Verification

Execution is not complete until RunbookHermes verifies recovery.

Verification should query observability backends.

Possible checks:

```text
HTTP 503 rate decreased
HTTP 504 rate decreased
HTTP 429 rate decreased
p95 latency normalized
error logs decreased
trace error rate decreased
new version is active
service health is stable
```

Example recovery result:

```json
{
  "ok": true,
  "service": "payment-service",
  "checks": {
    "http_503_rate": "decreased",
    "p95_latency": "normalized",
    "connection_pool_errors": "reduced"
  },
  "status": "recovered"
}
```

If recovery is not verified, RunbookHermes should not mark the incident as recovered.

---

## 17. Idempotency and Duplicate Calls

Messaging platforms may send duplicate callbacks. Operators may click buttons twice. Network retries may duplicate requests.

Executor integration should be idempotent.

Recommended idempotency key:

```text
incident_id + approval_id + action + target_version
```

Duplicate requests should return the existing execution state instead of executing twice.

---

## 18. Failure Handling

### 18.1 Approval Missing

Behavior:

```text
do not execute
return approval_required
record approval.requested or approval.missing
```

### 18.2 Approval Rejected

Behavior:

```text
do not execute
record approval.resolved rejected
keep incident open or mark action rejected
```

### 18.3 Dry-Run Fails

Behavior:

```text
do not execute
record dry_run.failed
show reason to operator
suggest manual escalation
```

### 18.4 Execution Fails

Behavior:

```text
record action.failed
show executor error
run recovery verification if partial action occurred
suggest rollback failure handling
notify on-call channel
```

### 18.5 Recovery Verification Fails

Behavior:

```text
record recovery.failed
keep incident active
suggest next investigation steps
escalate to owner
```

### 18.6 Executor Unavailable

Behavior:

```text
do not execute
record executor.unavailable
allow retry
fallback to manual runbook
```

---

## 19. Audit Events

Controlled execution should emit audit events.

Recommended events:

```text
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
```

Each audit event should include:

```text
incident_id
service
environment
action
risk_level
operator
approval_id
checkpoint_id
execution_id
evidence_ids
result
timestamp
error if any
```

---

## 20. Production Security Checklist

Before enabling production execution:

* [ ] Execution is disabled by default.
* [ ] Executor backend is explicitly configured.
* [ ] Model output cannot directly execute actions.
* [ ] Risk classifier is enabled.
* [ ] Approval is required for risky actions.
* [ ] Approver identity is verified.
* [ ] Checkpoint is required.
* [ ] Dry-run is required.
* [ ] Service allowlist is configured.
* [ ] Environment allowlist is configured.
* [ ] Executor has limited permissions.
* [ ] Executor API requires authentication.
* [ ] Idempotency is implemented.
* [ ] Audit logging is persistent.
* [ ] Recovery verification is required.
* [ ] Emergency stop is available.
* [ ] Manual override procedure exists.

---

## 21. Recommended Rollout Plan

### Stage 1: Read-Only Recommendation

RunbookHermes proposes actions but cannot execute.

Goal:

```text
Validate RCA and action recommendations.
```

### Stage 2: Approval Record Only

RunbookHermes creates approval records and card callbacks, but execution is disabled.

Goal:

```text
Validate human-in-the-loop process.
```

### Stage 3: Dry-Run Executor

RunbookHermes calls executor dry-run only.

Goal:

```text
Validate executor contract and policy checks.
```

### Stage 4: Staging Controlled Execution

RunbookHermes executes only in staging.

Goal:

```text
Validate checkpoint, execution, recovery verification, and audit.
```

### Stage 5: Limited Production Controlled Execution

Enable production execution for a small allowlist of services and actions.

Goal:

```text
Prove safe production remediation with guardrails.
```

### Stage 6: Broader Production Coverage

Expand only after incident review and safety validation.

---

## 22. Local Test Commands

Start Web/API:

```bat
conda activate runbookhermes311
cd /d E:\agent\run\runbookhermes-work\hermes-agent-2026.4.23
set PYTHONPATH=.

set ROLLBACK_BACKEND_KIND=demo_file
set DEMO_DEPLOY_STATE_FILE=data/payment_demo/deployments.json
set DEMO_VERSION_FILE=data/payment_demo/runtime/payment-service-version.txt
set RUNBOOK_CONTROLLED_EXECUTION_ENABLED=true

python -m uvicorn apps.runbook_api.app.main:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/web/incidents.html
http://127.0.0.1:8000/web/approvals.html
```

Create a payment incident:

```bat
curl -X POST http://127.0.0.1:8000/demo/scenarios/payment_503_spike/incident
```

Open the approval page and approve the pending action.

Then open the incident detail page and verify recovery.

---

## 23. Troubleshooting

### Approval exists but action does not execute

Check:

```text
approval status
checkpoint exists
RUNBOOK_CONTROLLED_EXECUTION_ENABLED
ACTION_EXECUTION_BACKEND
ROLLBACK_BACKEND_KIND
service allowlist
environment allowlist
executor response
```

### Executor says action is not configured

Check:

```text
ACTION_EXECUTION_BACKEND
ACTION_EXECUTION_API_BASE_URL
ACTION_EXECUTION_API_TOKEN
```

### Demo rollback does not change version

Check:

```text
DEMO_VERSION_FILE
DEMO_DEPLOY_STATE_FILE
file write permission
current working directory
```

### Production executor times out

Check:

```text
network access
executor URL
executor auth token
ACTION_EXECUTION_TIMEOUT_SECONDS
executor logs
```

### Recovery verification fails

Check:

```text
Prometheus / Loki / Trace connectivity
query time range
whether enough traffic exists after action
whether action actually changed service state
```

---

## 24. One-Sentence Summary

The rollback executor integration turns RunbookHermes from an evidence and recommendation system into a controlled remediation system, but only through a strict chain of policy, approval, checkpoint, dry-run, execution, recovery verification, and audit.
