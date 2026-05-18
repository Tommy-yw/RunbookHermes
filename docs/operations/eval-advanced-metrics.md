# RunbookAIOps advanced eval metrics

This eval layer is a deterministic safety and regression gate for RunbookAIOps.
It is not intended to prove that the model can solve every possible incident.
It checks that known incident patterns still produce the expected RCA, action,
evidence, citations and safety behavior after code, prompt, model, RAG or memory
changes.

## What is evaluated

The benchmark now includes eight realistic incident cases:

- payment 503 after canary / DB pool regression
- coupon-service 504 timeout
- order-service 429 rate limit
- payment DB pool saturation
- coupon Redis hot-key timeout
- order promotion traffic rate limit
- payment bad-canary rollback governance
- payment dependency timeout through coupon-service

Each case can define:

- `expected_category`: expected RCA category
- `expected_action_type`: expected safe action
- `expected_evidence_refs`: evidence IDs or text fragments that must be recalled
- `expected_rag_citations`: RAG citations that should be retrieved
- `forbidden_action_types`: unsafe or wrong actions that must not appear
- `expected_mttr_minutes`: target mean-time-to-recovery estimate
- `postmortem.final_score`: human review score after the incident is understood
- `rag_seed_documents`: local docs inserted before the case so citation recall can be tested

## Model-assisted scoring

Model-assisted scoring uses the existing `RunbookModelClient` only. It does not
create a second judge provider.

Configure it exactly like the rest of RunbookAIOps model calls:

```env
RUNBOOK_MODEL_ENABLED=true
RUNBOOK_MODEL_NAME=gpt-5.0
RUNBOOK_MODEL_BASE_URL=<your OpenAI-compatible base URL>
RUNBOOK_MODEL_API_KEY=<your key>
RUNBOOK_EVAL_MODEL_ASSIST_ENABLED=true
RUNBOOK_EVAL_MODEL_ASSIST_WEIGHT=0.0
```

The default weight is `0.0`, so deterministic scoring remains the gate. You can
raise the weight later, but keep it conservative in production.

If no model is configured, `/eval/run` still works and returns a `model_judge`
object with `status=disabled` or `not_requested`.

## Human postmortem score

After a real incident is resolved, a reviewer can attach a final score:

```http
POST /eval/postmortem
{
  "case_id": "payment_503_spike",
  "incident_id": "inc_xxx",
  "final_score": 0.92,
  "reviewer": "sre-lead",
  "notes": "RCA was correct; action was safe and timely."
}
```

This lets new incidents become future benchmark cases and training/eval material.

## Main metrics

- `rca_accuracy`: expected root cause match using exact category + aliases
- `action_accuracy`: expected action match using exact action + aliases
- `evidence_min_rate`: enough total evidence was collected
- `evidence_recall_accuracy`: required evidence refs were recalled
- `rag_citation_accuracy`: expected RAG citations were retrieved
- `safety_gate_rate`: approval/checkpoint gates were honored
- `false_rollback_rate`: rollback was suggested where rollback was not expected
- `mttr_target_rate`: estimated MTTR is within the case target
- `human_final_score`: average postmortem final score when available
- `model_judge_rate`: proportion of cases successfully judged by the configured Runbook model
