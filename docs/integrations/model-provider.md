# Model Provider Integration

This document explains how RunbookHermes connects to model providers, how that relates to the upstream Hermes Agent provider system, and how to configure models for local reference usage and production-oriented deployments.

RunbookHermes is built on top of Hermes Agent. Hermes provides the agent runtime and provider architecture. RunbookHermes adds incident-response specific model usage, especially model-assisted summaries, root-cause explanations, operator-facing reports, and postmortem drafts.

---

## 1. What the Model Is Used For

RunbookHermes should not rely on the model to guess blindly.

The correct flow is:

```text
observability tools collect evidence
→ EvidenceStack compresses evidence
→ RCA guard checks evidence consistency
→ model assists explanation and summary
→ action policy checks risk
→ approval / checkpoint / execution boundary controls action
```

The model is mainly used for:

* explaining the incident in readable language;
* summarizing evidence from metrics, logs, traces, and deploy records;
* ranking possible root causes;
* generating operator-facing summaries;
* generating Feishu / WeCom card text;
* drafting postmortem content;
* explaining why an action needs approval;
* turning incident experience into runbook skill material.

The model should **not** be used as an unrestricted production operator.

It should not directly bypass:

* evidence collection;
* policy guard;
* approval;
* checkpoint;
* dry-run;
* controlled execution;
* recovery verification;
* audit logging.

---

## 2. Two Model Paths in RunbookHermes

RunbookHermes currently has two related model paths.

### 2.1 Hermes-Native Agent Path

This is the upstream Hermes Agent path.

Expected command:

```bash
hermes --profile runbook-hermes
```

This path uses Hermes Agent's provider / runtime / tool / memory / context / skill architecture.

Use this path when you want a Hermes-native conversation loop, for example:

```text
payment-service HTTP 503 is rising after release. Please collect evidence first, explain the most likely root cause, and propose a safe action plan with approval requirements.
```

### 2.2 RunbookHermes Web/API Model Summary Path

This is the Web/API path used by the Incident Detail page.

Relevant endpoint:

```text
GET /incidents/{incident_id}/model-summary
```

This path uses RunbookHermes model configuration variables such as:

```text
RUNBOOK_MODEL_ENABLED
RUNBOOK_MODEL_BASE_URL
RUNBOOK_MODEL_API_KEY
RUNBOOK_MODEL_NAME
RUNBOOK_MODEL_TEMPERATURE
```

This path is designed to generate a readable summary from an existing incident record.

It does not replace the Hermes-native agent loop. It is a Web/API integration point for model-assisted incident summaries.

---

## 3. Recommended Production Model Design

For production-oriented deployment, use the model as an assistant to the incident workflow, not as an unchecked controller.

Recommended design:

```text
RunbookHermes tools produce structured evidence.
EvidenceStack compresses context.
Model reads evidence summaries.
Model writes explanation and recommendation.
Action policy classifies risk.
Approval system gates risky action.
Executor performs only approved actions.
Recovery verification checks result.
```

This keeps the model useful while keeping production operations safe.

---

## 4. OpenAI-Compatible Configuration

RunbookHermes supports OpenAI-compatible model endpoints for Web/API model-assisted summaries.

Environment variables:

```bash
RUNBOOK_MODEL_ENABLED=true
RUNBOOK_MODEL_PROVIDER=openai-compatible
RUNBOOK_MODEL_BASE_URL=https://your-openai-compatible-endpoint/v1
RUNBOOK_MODEL_API_KEY=your_api_key
RUNBOOK_MODEL_NAME=your_model_name
RUNBOOK_MODEL_TEMPERATURE=0
RUNBOOK_MAX_TURNS=12
```

On Windows Anaconda Prompt:

```bat
set RUNBOOK_MODEL_ENABLED=true
set RUNBOOK_MODEL_PROVIDER=openai-compatible
set RUNBOOK_MODEL_BASE_URL=https://your-openai-compatible-endpoint/v1
set RUNBOOK_MODEL_API_KEY=your_api_key
set RUNBOOK_MODEL_NAME=your_model_name
set RUNBOOK_MODEL_TEMPERATURE=0
set RUNBOOK_MAX_TURNS=12
```

Then restart the Web/API service:

```bat
set PYTHONPATH=.
python -m uvicorn apps.runbook_api.app.main:app --host 127.0.0.1 --port 8000
```

Open an incident detail page and use the model summary function.

---

## 5. Example: OpenRouter

Example environment variables:

```bat
set RUNBOOK_MODEL_ENABLED=true
set RUNBOOK_MODEL_PROVIDER=openai-compatible
set RUNBOOK_MODEL_BASE_URL=https://openrouter.ai/api/v1
set RUNBOOK_MODEL_API_KEY=your_openrouter_api_key
set RUNBOOK_MODEL_NAME=your_selected_model
set RUNBOOK_MODEL_TEMPERATURE=0
```

Then start RunbookHermes Web/API:

```bat
set PYTHONPATH=.
python -m uvicorn apps.runbook_api.app.main:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/web/incidents.html
```

Click an incident and generate the model-assisted summary.

---

## 6. Example: Local OpenAI-Compatible Model

If you run a local model service that exposes an OpenAI-compatible API, configure it like this:

```bat
set RUNBOOK_MODEL_ENABLED=true
set RUNBOOK_MODEL_PROVIDER=openai-compatible
set RUNBOOK_MODEL_BASE_URL=http://127.0.0.1:11434/v1
set RUNBOOK_MODEL_API_KEY=local
set RUNBOOK_MODEL_NAME=your_local_model
set RUNBOOK_MODEL_TEMPERATURE=0
```

The exact `RUNBOOK_MODEL_NAME` depends on your local model server.

Common local choices may include:

```text
qwen
llama
mistral
deepseek-compatible local model
```

The key requirement is that the server exposes a `/chat/completions` style OpenAI-compatible interface.

---

## 7. Example: Internal Company Model Gateway

In a company environment, the model may be exposed through an internal model gateway.

Example:

```bash
RUNBOOK_MODEL_ENABLED=true
RUNBOOK_MODEL_PROVIDER=openai-compatible
RUNBOOK_MODEL_BASE_URL=https://llm-gateway.internal.example.com/v1
RUNBOOK_MODEL_API_KEY=${SECRET_MODEL_API_KEY}
RUNBOOK_MODEL_NAME=company-approved-incident-model
RUNBOOK_MODEL_TEMPERATURE=0
```

Recommended company model gateway requirements:

* authentication;
* request logging;
* timeout;
* tenant control;
* sensitive-data filtering;
* model allowlist;
* cost limits;
* audit trail;
* incident ID propagation;
* trace ID propagation.

---

## 8. Where Model Output Appears in the Web Console

Model-assisted output appears on the Incident Detail page.

Typical page:

```text
/web/incident.html?id=inc_xxxxxx
```

The model summary section may show:

* incident summary;
* likely root cause explanation;
* supporting evidence explanation;
* recommended action summary;
* approval reason;
* recovery verification summary;
* postmortem draft text.

If the model is not configured, the page should still work. It may show a message such as:

```text
LLM is disabled. Set RUNBOOK_MODEL_ENABLED=true and RUNBOOK_MODEL_API_KEY to enable model-assisted summaries.
```

This is intentional. RunbookHermes should remain usable without a model provider for basic evidence, incident, approval, and monitoring views.

---

## 9. How Model Input Should Be Constructed

Model input should be based on structured incident evidence, not raw unbounded logs.

Recommended input fields:

```text
incident_id
service
environment
severity
alert summary
key metrics evidence
key log evidence
key trace evidence
recent deployment evidence
root-cause candidates
action plan
approval status
checkpoint summary
recovery verification result
related runbook skill
related incident memory summary
```

Avoid sending:

* full raw logs;
* full trace payloads;
* all metric samples;
* secrets;
* credentials;
* personal data;
* unrestricted production payloads;
* unrelated incident history.

Use `EvidenceStack` to keep the model input focused.

---

## 10. Recommended Model Prompt Behavior

The model should be instructed to:

* cite evidence IDs when explaining a root cause;
* distinguish confirmed facts from hypotheses;
* avoid inventing missing data;
* state uncertainty when evidence is incomplete;
* recommend safe next actions;
* explain why risky actions require approval;
* avoid claiming a recovery before verification;
* write operator-friendly summaries.

The model should not:

* claim a root cause without evidence;
* execute rollback by itself;
* override approval state;
* bypass action policy;
* expose secrets;
* turn incomplete observations into certainty.

---

## 11. Temperature and Determinism

Incident analysis should be stable and predictable.

Recommended setting:

```text
RUNBOOK_MODEL_TEMPERATURE=0
```

Use higher temperature only for non-critical text generation such as:

* postmortem writing style;
* documentation drafting;
* human-readable notification wording.

For root-cause explanation and action summary, keep temperature low.

---

## 12. Timeout and Failure Handling

A model outage should not break the incident workflow.

If the model provider fails:

```text
incident creation should still work;
evidence collection should still work;
approval should still work;
monitoring should still work;
manual operator workflow should still work;
model summary should fail gracefully.
```

Recommended behavior:

* show model error in UI;
* record error in incident timeline;
* do not mark incident failed only because model summary failed;
* fall back to deterministic RCA / evidence summary;
* allow retry.

---

## 13. Privacy and Data Safety

Before sending data to an external model provider, review what is included.

Do not send:

* credentials;
* tokens;
* customer personal information;
* raw payment data;
* internal secrets;
* full production logs;
* sensitive trace payloads;
* unredacted request bodies.

Recommended protections:

* evidence summarization;
* redaction;
* service allowlist;
* log sampling;
* query result limits;
* internal model gateway for sensitive environments;
* audit model requests and responses.

---

## 14. Production Checklist

Before enabling model-assisted analysis in production:

* [ ] Model provider is approved by the organization.
* [ ] API key is stored in a secret manager.
* [ ] Model timeout is configured.
* [ ] Temperature is set to a deterministic value.
* [ ] EvidenceStack summary is used instead of raw logs.
* [ ] Sensitive fields are redacted.
* [ ] Model output is labeled as assistant-generated.
* [ ] Model output cannot bypass approval.
* [ ] Model output cannot directly execute actions.
* [ ] Errors fail gracefully.
* [ ] Requests and responses are audited according to company policy.

---

## 15. Relationship to Hermes Agent Provider System

Hermes Agent has its own provider system for the agent runtime.

RunbookHermes keeps this design.

The `runbook-hermes` profile should be able to use Hermes provider configuration for Hermes-native chat and agent execution.

The Web/API `RUNBOOK_MODEL_*` configuration is an additional practical path for model-assisted summaries in the Web Console.

In a mature production deployment, you may choose to unify these paths behind the same internal model gateway.

Recommended mature architecture:

```text
Hermes Agent provider
RunbookHermes Web/API model summary
Feishu / WeCom card summary
postmortem draft generation
```

all point to:

```text
company-approved model gateway
```

---

## 16. Minimal Local Test

1. Start RunbookHermes Web/API with model variables:

```bat
set RUNBOOK_MODEL_ENABLED=true
set RUNBOOK_MODEL_PROVIDER=openai-compatible
set RUNBOOK_MODEL_BASE_URL=https://your-openai-compatible-endpoint/v1
set RUNBOOK_MODEL_API_KEY=your_api_key
set RUNBOOK_MODEL_NAME=your_model_name
set RUNBOOK_MODEL_TEMPERATURE=0

set PYTHONPATH=.
python -m uvicorn apps.runbook_api.app.main:app --host 127.0.0.1 --port 8000
```

2. Create an incident:

```bat
curl -X POST http://127.0.0.1:8000/demo/scenarios/payment_503_spike/incident
```

3. Open the incident list:

```text
http://127.0.0.1:8000/web/incidents.html
```

4. Click the incident ID.

5. Generate model summary from the incident detail page.

---

## 17. Troubleshooting

### Model summary says model is disabled

Check:

```bat
set RUNBOOK_MODEL_ENABLED
set RUNBOOK_MODEL_API_KEY
set RUNBOOK_MODEL_BASE_URL
set RUNBOOK_MODEL_NAME
```

Restart the Web/API service after setting environment variables.

### Model request returns unauthorized

Check:

* API key;
* provider base URL;
* model name;
* organization / account permission;
* whether the provider expects `Bearer` token authentication.

### Model request times out

Check:

* network access;
* provider status;
* model availability;
* request payload size;
* timeout setting;
* whether raw logs are too large.

### Model output is too verbose

Reduce the prompt input and ask for a structured summary:

```text
Summary
Evidence
Most likely root cause
Recommended action
Approval requirement
Recovery check
```

### Model invents facts

Tighten the prompt:

```text
Only use the provided evidence.
If evidence is missing, say it is missing.
Cite evidence IDs.
Separate facts from hypotheses.
```

---

## 18. One-Sentence Summary

RunbookHermes uses models as evidence-aware incident reasoning assistants, while Hermes tools, EvidenceStack, IncidentMemory, approval, checkpoint, controlled execution, and recovery verification keep the workflow grounded, safe, and auditable.

