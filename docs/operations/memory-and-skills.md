# Memory, EvidenceStack, and Runbook Skills

This document explains how RunbookHermes uses memory, context compression, and skills to turn incident response into reusable operational knowledge.

RunbookHermes is based on Hermes Agent. Hermes Agent provides the broader memory, context, and skill architecture. RunbookHermes adapts those ideas into an AIOps / incident-response domain:

```text
Hermes memory concept        → IncidentMemory
Hermes context management    → EvidenceStack
Hermes skills                → Runbook Skills
Hermes self-improvement loop → incident review and runbook learning
```

The goal is not to remember everything. The goal is to remember the right operational facts at the right time.

---

## 1. Why Memory Matters in Incident Response

Incident response is repetitive.

The same services often fail in similar ways:

```text
payment-service HTTP 503 after release
coupon-service HTTP 504 timeout
order-service HTTP 429 rate limit
mysql-payment latency spike
connection pool exhausted
bad rollout configuration
traffic shift failure
```

A useful incident agent should not start from zero every time.

It should remember:

* what happened before;
* what evidence was useful;
* what root cause was confirmed;
* what action worked;
* what action was rejected;
* who needed to approve;
* what verification proved recovery;
* what runbook skill was generated afterward.

But it should not put every historical log line, metric point, trace span, or chat message into the model prompt.

RunbookHermes uses memory and context compression to solve this.

---

## 2. Three Different Concepts

RunbookHermes separates three related but different concepts:

```text
Memory
Context
Skills
```

### 2.1 Memory

Memory stores useful knowledge across incidents.

Examples:

```text
payment-service often needs SRE approval for rollback.
payment-service had a previous HTTP 503 caused by database connection pool regression.
The payment team prefers rollback only after dry-run and checkpoint.
```

### 2.2 Context

Context is the current incident state that the model or operator needs right now.

Examples:

```text
current alert
current Prometheus evidence
current Loki evidence
current trace evidence
recent deploy record
current approval state
current action plan
```

### 2.3 Skills

Skills are reusable procedures.

Examples:

```text
How to triage payment-service HTTP 503 after release.
How to handle coupon-service HTTP 504 timeout.
How to investigate order-service HTTP 429 rate limit.
```

Memory stores facts. Context organizes the current case. Skills define reusable workflows.

---

## 3. Files Involved

Memory and skills are mainly implemented in:

```text
plugins/memory/incident_memory/
plugins/context_engine/evidence_stack/
skills/runbooks/
runbook_hermes/events.py
runbook_hermes/store.py
runbook_hermes/incident_service.py
runbook_hermes/rca_guard.py
runbook_hermes/model_client.py
```

Related UI pages:

```text
/web/incident.html?id={incident_id}
/web/digests.html
/web/settings.html
```

Potential future UI pages:

```text
/web/memory.html
/web/skills.html
```

---

## 4. IncidentMemory

`IncidentMemory` is RunbookHermes' incident-response memory provider.

It is designed to store operational knowledge, not raw noise.

It should remember stable information such as:

```text
service profile
service owner or team preference
common failure pattern
confirmed incident summary
root-cause history
approval requirement
successful remediation pattern
generated runbook skill index
```

It should avoid storing:

```text
full raw logs
full trace payloads
every Prometheus sample
large request bodies
secrets
tokens
PII
unredacted payment data
entire chat transcripts
```

The design rule is:

```text
Store durable operational lessons, not temporary data exhaust.
```

---

## 5. Example IncidentMemory Records

### 5.1 Service Profile

```json
{
  "type": "service_profile",
  "service": "payment-service",
  "owner": "payment-platform-team",
  "criticality": "high",
  "default_environment": "prod",
  "approval_required_for": ["rollback", "restart", "traffic_shift"],
  "primary_signals": ["http_503_rate", "p95_latency", "mysql-payment trace latency"]
}
```

### 5.2 Incident Summary

```json
{
  "type": "incident_summary",
  "service": "payment-service",
  "incident_id": "inc_510364",
  "root_cause": "v2.3.1 introduced database connection pool regression",
  "evidence_ids": [
    "ev_metric_http_503_rate",
    "ev_log_connection_pool",
    "ev_trace_mysql_latency",
    "ev_deploy_v231"
  ],
  "effective_action": "rollback to v2.3.0",
  "recovery_verified": true
}
```

### 5.3 Team Preference

```json
{
  "type": "team_preference",
  "service": "payment-service",
  "preference": "For production rollback, require SRE approval and dry-run before execution."
}
```

---

## 6. EvidenceStack

`EvidenceStack` is RunbookHermes' context engine for incident response.

Incident response produces too much raw context:

```text
metrics
logs
traces
deploy records
approval records
checkpoint records
action results
timeline events
operator comments
model summaries
```

If all of this is pushed into a prompt, the context becomes noisy and expensive.

`EvidenceStack` organizes the current incident into a compact structure:

```text
alert summary
evidence
hypotheses
actions
final answer
```

This makes the model and operator focus on what matters.

---

## 7. EvidenceStack Example

For a payment-service HTTP 503 incident:

```text
Alert:
  payment-service HTTP 503 increased after release

Evidence:
  ev_metric_http_503_rate:
    Prometheus shows HTTP 503 rate increased to 18%

  ev_log_connection_pool:
    Loki shows repeated connection pool exhausted messages

  ev_trace_mysql_latency:
    Jaeger shows payment-service → mysql-payment p95 latency increased

  ev_deploy_v231:
    deploy history shows payment-service v2.3.1 was released recently

Hypothesis:
  v2.3.1 introduced database connection pool regression

Action:
  rollback payment-service to v2.3.0

Safety:
  destructive action, approval and checkpoint required
```

This is much better than sending thousands of raw log lines to a model.

---

## 8. How Memory and EvidenceStack Work Together

Memory and EvidenceStack serve different purposes.

```text
IncidentMemory:
  What should the agent remember across incidents?

EvidenceStack:
  What does the agent need right now for this incident?
```

A typical flow:

```text
new incident created
→ service name is payment-service
→ IncidentMemory recalls relevant service profile and prior incident summaries
→ tools collect current evidence
→ EvidenceStack compresses current evidence
→ model receives memory summary + current evidence stack
→ root-cause explanation is generated
→ action plan is checked by policy
→ approval / checkpoint / recovery flow continues
```

The model should receive:

```text
relevant memory summary
current evidence summary
current action constraints
```

not:

```text
all historical incidents
all raw logs
all raw traces
all metric samples
```

---

## 9. Runbook Skills

Runbook skills are reusable operational procedures.

They live under:

```text
skills/runbooks/
```

A runbook skill should explain:

* when to use the skill;
* what symptoms indicate this scenario;
* what evidence to collect first;
* what root-cause patterns to check;
* what actions are safe;
* what actions require approval;
* how to verify recovery;
* what to record after the incident.

Runbook skills turn incident response from one-off troubleshooting into reusable operational knowledge.

---

## 10. Example Runbook Skill Structure

A skill for payment-service HTTP 503 might include:

```text
Name:
  payment-service HTTP 503 after release

When to use:
  payment-service HTTP 503 increases after recent deployment

Collect evidence:
  Prometheus HTTP 503 rate
  p95 latency
  Loki connection pool logs
  Jaeger payment-service → mysql-payment traces
  recent deploy records

Likely root causes:
  database connection pool regression
  bad config rollout
  downstream mysql latency
  dependency timeout

Recommended action:
  rollback only if deploy correlation and evidence support it

Safety:
  approval required
  checkpoint required
  dry-run required

Recovery verification:
  HTTP 503 decreases
  p95 latency normalizes
  connection pool logs decrease
```

---

## 11. Skill Generation After Incident

After an incident, RunbookHermes can generate or update a runbook skill.

Inputs:

```text
incident summary
evidence IDs
confirmed root cause
action taken
approval result
checkpoint summary
recovery verification result
operator notes
```

Output:

```text
new skill
updated skill
skill recommendation
skill index entry
```

Skill generation should be reviewed before being treated as final operational guidance.

Recommended process:

```text
incident resolved
→ summary generated
→ skill draft generated
→ operator reviews
→ skill accepted or edited
→ skill index updated
```

---

## 12. Where Memory and Skills Appear in the Web Console

Current Web Console surfaces memory and skill information through:

```text
Incident Detail page
Digest page
Settings page
```

### 12.1 Incident Detail

Shows:

```text
evidence
root cause
action plan
timeline
generated skill
model-assisted summary
raw incident JSON
```

### 12.2 Digest Page

Shows:

```text
recent incidents
high-frequency faults
generated runbook skills
```

### 12.3 Settings Page

Shows:

```text
memory / model / observability / execution interface readiness
```

Future recommended pages:

```text
Memory Browser
Skill Forge
Incident Similarity Search
```

---

## 13. Recommended Memory Browser

A future `/web/memory.html` page should show:

```text
service profiles
team preferences
incident summaries
root-cause history
approval rules
skill index
last updated time
source incident ID
```

Useful filters:

```text
service
environment
root cause
team
skill
severity
```

This would make Hermes-style memory visible to operators.

---

## 14. Recommended Skill Forge

A future `/web/skills.html` or `/web/skill-forge.html` page should show:

```text
existing runbook skills
skill usage count
last used incident
source incident
confidence
review status
owner
edit / approve / archive buttons
```

Suggested skill states:

```text
draft
reviewed
approved
deprecated
archived
```

This would make the self-improvement loop more explicit.

---

## 15. Incident Similarity Search

A production-grade memory system should support similar incident search.

Possible search methods:

```text
keyword search
SQLite FTS
PostgreSQL full-text search
vector search
hybrid search
```

Useful similarity signals:

```text
service name
error status
log pattern
trace downstream
recent deploy correlation
root-cause category
action taken
recovery result
```

Example:

```text
Current incident:
payment-service HTTP 503 after release

Similar historical incident:
inc_510364, v2.3.1 connection pool regression, rollback fixed it
```

This is how RunbookHermes can “remember the right thing at the right time.”

---

## 16. Storage Evolution

Current local reference storage may use local JSON files.

For production, memory and skills should move to durable storage.

Recommended evolution:

```text
Local reference:
  JSON store

Single-node internal deployment:
  SQLite

Production deployment:
  PostgreSQL / MySQL

Advanced memory retrieval:
  PostgreSQL full-text search / pgvector / external vector database
```

What should be durable:

```text
incidents
evidence summaries
root-cause hypotheses
action plans
approvals
checkpoints
recovery verification results
timeline events
incident summaries
service profiles
skills
skill index
operator notes
```

---

## 17. What Should Not Be Stored Long-Term

Avoid long-term storage of unnecessary sensitive or noisy data:

```text
raw secrets
API tokens
full raw logs
unredacted payment data
full request bodies
large trace payloads
PII
irrelevant chat transcripts
temporary debug output
```

Instead store:

```text
evidence ID
summary
count
sample redacted lines
trace ID reference
metric value summary
link to source system
```

This keeps memory useful, small, and safer.

---

## 18. Memory and Model Input Safety

Before sending memory to a model, apply filtering.

Recommended model input:

```text
service profile summary
relevant historical incident summary
current evidence stack
current action plan
approval constraints
recovery status
```

Avoid model input:

```text
all memory records
all historical incidents
full raw logs
unredacted sensitive data
full trace payloads
operator private notes not needed for incident response
```

Model prompts should instruct:

```text
Use only provided evidence.
Cite evidence IDs.
Separate facts from hypotheses.
State uncertainty when evidence is incomplete.
Do not invent missing data.
Do not bypass approval.
```

---

## 19. Memory Update Policy

Not every event should update long-term memory.

Recommended memory update triggers:

```text
incident resolved
recovery verified
operator confirms root cause
runbook skill generated
operator edits service profile
approval rule changed
postmortem completed
```

Avoid memory updates when:

```text
incident is still unresolved
root cause is uncertain
recovery is not verified
evidence is incomplete
action failed and cause is unknown
```

This prevents the system from learning incorrect operational facts.

---

## 20. Skill Quality Checklist

A good runbook skill should include:

* clear trigger conditions;
* affected services;
* symptoms;
* required evidence;
* safe read-only tools;
* root-cause patterns;
* action recommendations;
* approval requirements;
* checkpoint requirements;
* recovery verification steps;
* escalation rules;
* examples;
* last reviewed date;
* source incident references.

A bad runbook skill:

* says “rollback” without evidence;
* does not define recovery verification;
* ignores approval;
* is too service-specific without saying so;
* is too generic to be useful;
* contains raw logs instead of summarized evidence;
* contains secrets or sensitive data.

---

## 21. Example Full Learning Loop

Example incident:

```text
payment-service HTTP 503 increased after v2.3.1 release
```

RunbookHermes flow:

```text
1. Alert enters RunbookHermes.
2. Evidence is collected from Prometheus, Loki, Jaeger, and deploy records.
3. EvidenceStack summarizes the evidence.
4. IncidentMemory recalls previous payment-service incident patterns.
5. Root-cause hypothesis points to connection pool regression.
6. Rollback action is proposed.
7. Approval and checkpoint are required.
8. Controlled rollback is executed after approval.
9. Recovery is verified.
10. Incident summary is written.
11. Runbook skill is generated or updated.
12. IncidentMemory records the stable lesson.
```

Stable lesson:

```text
For payment-service HTTP 503 after release, check deploy correlation, connection pool logs, and mysql-payment trace latency before proposing rollback.
```

---

## 22. Relationship to Hermes Agent

Hermes Agent provides the general architecture for memory, context, and skills.

RunbookHermes adapts that architecture into the incident-response domain.

Relationship:

```text
Hermes Agent:
  general memory/context/skills architecture

RunbookHermes:
  IncidentMemory + EvidenceStack + Runbook Skills
```

This is specialization, not conflict.

The goal is to preserve Hermes Agent's strength:

```text
an agent that improves from experience
```

and apply it to AIOps:

```text
an incident-response agent that learns from previous incidents and reuses operational knowledge safely
```

---

## 23. Production Readiness Checklist

Before relying on RunbookHermes memory and skills in production:

* [ ] Durable storage is configured.
* [ ] Sensitive data redaction is implemented.
* [ ] Memory update policy is defined.
* [ ] Operator review exists for generated skills.
* [ ] Similar incident search is available or planned.
* [ ] Service profiles are maintained.
* [ ] Skill ownership is defined.
* [ ] Deprecated skills can be archived.
* [ ] Memory records include source incident IDs.
* [ ] Model input uses summaries, not raw data dumps.
* [ ] Memory output is auditable.
* [ ] Incorrect memory can be edited or removed.

---

## 24. Common Anti-Patterns

Avoid these:

```text
storing every log line as memory
sending all historical incidents to the model
learning from unresolved incidents
turning uncertain hypotheses into permanent facts
generating skills without review
using memory to bypass evidence collection
using skill recommendations to bypass approval
storing secrets in memory
keeping outdated skills active forever
```

These anti-patterns make the agent less reliable and less safe.

---

## 25. One-Sentence Summary

RunbookHermes uses IncidentMemory, EvidenceStack, and Runbook Skills to carry Hermes Agent's memory and learning ideas into incident response: remember durable operational lessons, compress current evidence into a traceable context, and turn resolved incidents into reusable runbook knowledge.
