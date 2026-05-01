# Feishu / WeCom Integration

This document explains how RunbookHermes integrates with Feishu and WeCom for incident intake, approval cards, and human-in-the-loop remediation.

RunbookHermes uses Feishu / WeCom as operator-facing messaging channels. The goal is not to let the model silently operate production systems. The goal is to bring incident evidence, root-cause analysis, action proposals, approval, checkpoint, and recovery verification into the tools that on-call engineers already use.

---

## 1. Integration Goal

Feishu / WeCom integration should support this workflow:

```text
Alert or user message
→ RunbookHermes incident created
→ evidence collected from observability systems
→ root-cause hypothesis generated
→ action plan proposed
→ approval card sent to on-call channel
→ operator approves or rejects
→ checkpoint + dry-run + controlled execution
→ recovery verification
→ incident timeline updated
```

The messaging platform is the human-facing control surface. The incident workflow still lives inside RunbookHermes.

---

## 2. Files Involved

Feishu / WeCom integration is mainly implemented in:

```text
runbook_hermes/gateway/feishu.py
runbook_hermes/gateway/feishu_cards.py
runbook_hermes/gateway/wecom.py
apps/runbook_api/app/main.py
runbook_hermes/commands.py
runbook_hermes/events.py
runbook_hermes/incident_service.py
runbook_hermes/approval.py
```

Related Web/API routes:

```text
POST /gateway/feishu/events
POST /gateway/feishu/card-callback
POST /gateway/feishu/webhook

POST /gateway/wecom/events
POST /gateway/wecom/card-callback
POST /gateway/wecom/webhook
```

Related Web pages:

```text
/web/incidents.html
/web/incident.html?id={incident_id}
/web/approvals.html
/web/settings.html
```

---

## 3. Feishu vs WeCom in RunbookHermes

RunbookHermes treats Feishu and WeCom as incident gateways.

| Capability             | Feishu                                          | WeCom                                           |
| ---------------------- | ----------------------------------------------- | ----------------------------------------------- |
| Incident intake        | Supported through event / webhook adapter shell | Supported through event / webhook adapter shell |
| Approval card callback | Supported through card-callback route           | Supported through card-callback route           |
| Bot notification       | Environment variables reserved                  | Environment variables reserved                  |
| Security token         | Verification token / encrypt key                | Token / EncodingAESKey                          |
| Production callback    | Requires public HTTPS callback URL              | Requires public HTTPS callback URL              |
| Current status         | Interface shell + local API route               | Interface shell + local API route               |

Production use requires completing platform-specific signature verification, encryption/decryption, permission setup, callback URL exposure, and identity mapping.

---

## 4. Feishu Environment Variables

Configure these variables for Feishu integration:

```bash
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_VERIFICATION_TOKEN=
FEISHU_ENCRYPT_KEY=
FEISHU_CALLBACK_BASE_URL=https://runbookhermes.example.com
FEISHU_BOT_WEBHOOK_URL=
FEISHU_BOT_SECRET=
```

On Windows Anaconda Prompt:

```bat
set FEISHU_APP_ID=
set FEISHU_APP_SECRET=
set FEISHU_VERIFICATION_TOKEN=
set FEISHU_ENCRYPT_KEY=
set FEISHU_CALLBACK_BASE_URL=https://runbookhermes.example.com
set FEISHU_BOT_WEBHOOK_URL=
set FEISHU_BOT_SECRET=
```

The callback base URL should be the public HTTPS address where Feishu can reach RunbookHermes.

---

## 5. WeCom Environment Variables

Configure these variables for WeCom integration:

```bash
WECOM_CORP_ID=
WECOM_AGENT_ID=
WECOM_SECRET=
WECOM_TOKEN=
WECOM_ENCODING_AES_KEY=
WECOM_CALLBACK_BASE_URL=https://runbookhermes.example.com
```

On Windows Anaconda Prompt:

```bat
set WECOM_CORP_ID=
set WECOM_AGENT_ID=
set WECOM_SECRET=
set WECOM_TOKEN=
set WECOM_ENCODING_AES_KEY=
set WECOM_CALLBACK_BASE_URL=https://runbookhermes.example.com
```

WeCom callback mode normally requires the gateway to be reachable before saving the callback URL because the platform verifies the callback immediately.

---

## 6. Feishu Event Flow

A typical Feishu incident flow:

```text
Feishu message / event
→ POST /gateway/feishu/events
→ normalize payload into IncidentCommand
→ create incident
→ collect evidence
→ build EvidenceStack
→ generate root-cause hypothesis
→ propose action
→ create approval if action is risky
→ send or render approval card
→ operator approves / rejects
→ POST /gateway/feishu/card-callback
→ update approval state
→ continue controlled execution if approved
```

The Feishu Open Platform event subscription model sends events to the developer server. If encryption is enabled, the server needs to decrypt the event before parsing and verifying it. Feishu also uses a verification token to help verify that pushed events belong to the app.

---

## 7. Feishu Card Callback Flow

Feishu approval cards should support:

```text
View incident
Approve action
Reject action
Open Web Console
```

A typical callback flow:

```text
operator clicks Approve
→ Feishu sends card callback
→ RunbookHermes verifies request
→ approval decision is recorded
→ incident timeline updated
→ checkpoint / dry-run / execution flow continues
```

Feishu card interaction callbacks are sent to the callback request address registered in the developer backend when a user clicks a callback interaction component. Feishu expects the backend to respond promptly to the callback.

Recommended callback payload fields for RunbookHermes:

```json
{
  "incident_id": "inc_xxxxxx",
  "approval_id": "appr_xxxxxx",
  "decision": "approved",
  "operator_id": "feishu_user_id",
  "action": "rollback_canary",
  "service": "payment-service"
}
```

---

## 8. WeCom Event Flow

A typical WeCom incident flow:

```text
WeCom message / callback
→ POST /gateway/wecom/events
→ normalize payload into IncidentCommand
→ create incident
→ collect evidence
→ generate root-cause hypothesis
→ propose action
→ create approval
→ operator approves / rejects through WeCom callback
→ POST /gateway/wecom/card-callback
→ update approval state
```

WeCom self-built app callback mode commonly uses callback URL, Token, and EncodingAESKey. The platform may send a verification request when saving the callback URL, so the RunbookHermes gateway should be ready before the callback is configured in the admin console.

---

## 9. Local Testing Without Real Feishu / WeCom

You can test the RunbookHermes gateway routes locally without connecting the real platforms.

Start Web/API:

```bat
conda activate runbookhermes311
cd /d E:\agent\run\runbookhermes-work\hermes-agent-2026.4.23
set PYTHONPATH=.
python -m uvicorn apps.runbook_api.app.main:app --host 127.0.0.1 --port 8000
```

Create a Feishu-style incident:

```bat
curl -X POST http://127.0.0.1:8000/gateway/feishu/events ^
  -H "Content-Type: application/json" ^
  -d "{\"service\":\"payment-service\",\"summary\":\"payment-service HTTP 503 spike after release\",\"severity\":\"p1\",\"environment\":\"prod\"}"
```

Create a WeCom-style incident:

```bat
curl -X POST http://127.0.0.1:8000/gateway/wecom/events ^
  -H "Content-Type: application/json" ^
  -d "{\"service\":\"payment-service\",\"summary\":\"payment-service HTTP 503 spike after release\",\"severity\":\"p1\",\"environment\":\"prod\"}"
```

Then open:

```text
http://127.0.0.1:8000/web/incidents.html
```

---

## 10. Public Callback for Local Development

Feishu and WeCom cannot call `127.0.0.1` on your laptop.

For local platform testing, expose RunbookHermes through a temporary public HTTPS tunnel:

```text
ngrok
cloudflared tunnel
frp
localtunnel
```

Example conceptual flow:

```text
https://your-tunnel.example.com
→ http://127.0.0.1:8000
```

Then configure platform callbacks:

```text
Feishu event callback:
https://your-tunnel.example.com/gateway/feishu/events

Feishu card callback:
https://your-tunnel.example.com/gateway/feishu/card-callback

WeCom event callback:
https://your-tunnel.example.com/gateway/wecom/events

WeCom card callback:
https://your-tunnel.example.com/gateway/wecom/card-callback
```

Do not use temporary tunnels for production.

---

## 11. Production Callback Deployment

Production callback URLs should be served through HTTPS ingress or reverse proxy.

Example:

```text
https://runbookhermes.company.internal/gateway/feishu/events
https://runbookhermes.company.internal/gateway/feishu/card-callback
https://runbookhermes.company.internal/gateway/wecom/events
https://runbookhermes.company.internal/gateway/wecom/card-callback
```

Production requirements:

* HTTPS;
* stable domain;
* request signature verification;
* encryption/decryption handling;
* platform token validation;
* callback replay protection;
* request timeout control;
* access logging;
* audit logging;
* operator identity mapping;
* RBAC for approval actions.

---

## 12. Approval Card Design

A RunbookHermes approval card should show enough context for the operator to make a decision.

Recommended fields:

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
Checkpoint summary
Dry-run status
Buttons: Approve / Reject / Open Web Console
```

Example card content:

```text
P1 Incident: payment-service HTTP 503 spike

Likely root cause:
payment-service v2.3.1 introduced database connection pool regression.

Evidence:
- ev_metric_http_503_rate: HTTP 503 rate increased
- ev_log_connection_pool: connection pool exhausted repeated
- ev_trace_mysql_latency: mysql-payment latency increased
- ev_deploy_v231: v2.3.1 deployed recently

Recommended action:
Rollback payment-service from v2.3.1 to v2.3.0.

Risk:
Destructive action. Approval and checkpoint required.
```

---

## 13. Identity and RBAC

A production approval is only meaningful if the approver identity is trusted.

RunbookHermes should map platform identities to internal identities:

```text
Feishu user ID → company identity → approver role
WeCom user ID  → company identity → approver role
```

Recommended roles:

```text
viewer
operator
approver
admin
auditor
```

Only approvers should be allowed to approve destructive actions.

If identity cannot be verified, fail closed:

```text
Do not execute the action.
Record the failed approval attempt.
Ask an authorized approver to retry.
```

---

## 14. Security Verification

### 14.1 Feishu

Feishu integration should verify:

* verification token;
* encrypted event payload if encryption is enabled;
* card callback request source;
* callback payload structure;
* action ID;
* approval ID;
* operator identity.

Feishu event subscription can send events to a developer server, and encrypted events need to be decrypted before parsing. Feishu verification token is used to verify that pushed events belong to the app.

### 14.2 WeCom

WeCom integration should verify:

* callback signature;
* Token;
* EncodingAESKey;
* encrypted callback payload;
* operator identity;
* approval ID;
* action ID.

For WeCom callback mode, the gateway should be ready before saving the callback URL because the platform may verify the callback immediately.

---

## 15. Failure Handling

Messaging integration should fail safely.

### Callback verification fails

Behavior:

```text
reject request
record security event
no approval decision applied
no execution triggered
```

### Approval payload is missing incident ID

Behavior:

```text
reject decision
show error response
record malformed callback
```

### Unknown approval ID

Behavior:

```text
reject decision
record event
ask operator to open Web Console
```

### Duplicate callback

Behavior:

```text
idempotently return current approval state
avoid double execution
record duplicate callback if needed
```

### Messaging platform unavailable

Behavior:

```text
incident workflow still works through Web/API
approval can be performed through Web Console
record notification failure
retry notification if configured
```

---

## 16. Relationship to Web Console

Feishu / WeCom are not replacements for the Web Console.

Recommended division:

```text
Feishu / WeCom:
  alert notification
  summary card
  approve / reject
  quick status update

Web Console:
  full evidence
  full timeline
  raw incident JSON
  monitoring dashboard
  checkpoint details
  generated skills
  settings and integration status
```

Cards should link back to:

```text
/web/incident.html?id={incident_id}
```

---

## 17. Production Rollout Plan

### Stage 1: Notification Only

Send incident summaries to Feishu / WeCom.

Do not allow approval from cards yet.

Goal:

```text
Validate notification format and routing.
```

### Stage 2: Approval Record Only

Allow approve / reject from cards, but do not execute production actions.

Goal:

```text
Validate identity mapping and approval audit.
```

### Stage 3: Dry-Run Only

After approval, trigger executor dry-run only.

Goal:

```text
Validate action safety and platform callbacks.
```

### Stage 4: Controlled Execution for Staging

Allow execution only in staging or canary environment.

Goal:

```text
Validate full approve → checkpoint → execute → verify flow.
```

### Stage 5: Controlled Production Execution

Enable production execution only with:

```text
RBAC
approval
checkpoint
dry-run
service allowlist
audit
recovery verification
emergency stop
```

---

## 18. Production Checklist

Before enabling production Feishu / WeCom integration:

* [ ] Public HTTPS callback URL is configured.
* [ ] Verification token is configured.
* [ ] Encrypt key / EncodingAESKey is configured if required.
* [ ] Signature verification is implemented.
* [ ] Callback replay protection is implemented.
* [ ] Operator identity mapping is implemented.
* [ ] Approver RBAC is implemented.
* [ ] Approval decisions are audited.
* [ ] Duplicate callbacks are idempotent.
* [ ] Unknown approval IDs fail closed.
* [ ] Card links point to Web Console incident detail.
* [ ] Messaging failure does not break Web/API workflow.
* [ ] Production execution remains disabled until executor is approved.

---

## 19. Troubleshooting

### Feishu callback is not received

Check:

* public callback URL;
* HTTPS certificate;
* route path;
* firewall / ingress;
* app event subscription settings;
* verification token;
* encryption configuration.

### Feishu card button does nothing

Check:

* card callback URL;
* callback component action value;
* approval ID in payload;
* incident ID in payload;
* backend response format;
* callback timeout.

### WeCom callback verification fails

Check:

* Token;
* EncodingAESKey;
* CorpID;
* AgentID;
* callback URL;
* whether the gateway was running before saving callback configuration.

### Approval is recorded but execution does not run

Check:

* action risk classification;
* approval state;
* checkpoint creation;
* executor backend configuration;
* `RUNBOOK_CONTROLLED_EXECUTION_ENABLED`;
* service allowlist;
* environment allowlist.

### Operator cannot approve

Check:

* identity mapping;
* RBAC role;
* approval ID;
* whether approval has already been resolved;
* whether incident is still active.

---

## 20. One-Sentence Summary

Feishu and WeCom integration turns RunbookHermes from a Web-only incident console into an on-call workflow agent: incidents enter from messaging or alerts, evidence and recommendations are summarized into cards, risky actions require human approval, and every decision is tied back to the incident timeline and Web Console.
