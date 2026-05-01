# Payment Service HTTP 503 Spike After Release

Use this skill when `payment-service` starts returning HTTP 503 shortly after a release, especially after version `v2.3.1`.

## Goal
Find whether the new release caused a database connection pool regression, then propose a safe rollback path.

## Evidence to collect
1. `prom_top_anomalies(service="payment-service")`
   - Look for `http_503_rate`, p95 latency, and request volume changes.
2. `loki_query(service="payment-service", query="connection pool exhausted")`
   - Look for database pool exhaustion or timeout messages.
3. `trace_search(service="payment-service", error_only=true)`
   - Look for slow or failed spans to `mysql-payment`.
4. `recent_deploys(service="payment-service")`
   - Check whether `v2.3.1` was deployed shortly before the HTTP 503 increase.
5. `incident_rca_guard(...)`
   - Confirm the evidence is consistent before producing the final RCA.
6. `action_policy_guard(...)`
   - Generate policy-checked actions.

## Decision logic
A release regression is likely when all of these are true:

- `payment-service` has a recent deployment such as `v2.3.1`.
- HTTP 503 rate increases after the deployment.
- Logs include `connection pool exhausted` or similar DB pool messages.
- Trace evidence points to `mysql-payment` latency or failed spans.

## Recommended action
If the above evidence is present, propose:

- `rollback_canary(service="payment-service", target_revision="v2.3.0", dry_run=true)` first.
- If the operator approves, call `rollback_canary(..., dry_run=false, approval_id="...")`.
- Then call `verify_recovery(service="payment-service")`.

## Safety rules

- Never execute rollback without approval.
- Always create a checkpoint before destructive execution.
- Keep raw logs and full traces out of stable memory.
- Final answer must cite evidence IDs.

## Final answer template

- Root cause: ...
- Evidence: `ev_metric_http_503_rate`, `ev_log_pool_exhausted`, `ev_trace_mysql_latency`, `ev_deploy_v231`
- Recommended action: rollback from `v2.3.1` to `v2.3.0` after approval.
- Verification: check HTTP 503 rate and p95 latency for 10 minutes.
