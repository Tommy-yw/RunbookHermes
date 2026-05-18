# RunbookHermes hardening, RAG, eval and multimodal evidence

This layer extends the Hermes-native RunbookHermes profile with four production-facing capabilities:

1. canonical memory kinds shared by the router, RCA guard and action policy;
2. optional API token authentication for the FastAPI surface;
3. local citation RAG over SRE documents and runbooks;
4. deterministic benchmark/eval and multimodal AIOps evidence ingestion.

## Canonical memory kinds

RunbookHermes now normalizes all memory writes through `runbook_hermes.memory_kinds`.

Canonical values:

- `incident_summary`
- `fault_pattern`
- `team_preference`
- `service_governance`
- `service_profile`
- `skill_index`
- `manual_note`
- `rag_document`
- `visual_observation`
- `topology_observation`

Legacy aliases from older patches are still accepted. For example, `governance_rule` is normalized to `service_governance`, and `team_habit` is normalized to `team_preference`. This keeps old memories useful while ensuring action policy and RCA priors read the same vocabulary.

The router environment parser also accepts top-level metadata, `event`, `command`, nested `payload.event` and related webhook shapes. A payload such as `{"environment":"staging"}` no longer falls back to `prod`.

## API authentication

API authentication is enabled by default. Set a write token before exposing the API; without `RUNBOOK_API_TOKEN`, non-public API routes fail closed with HTTP 503 instead of allowing unsafe writes. For isolated local demos only, set `RUNBOOK_API_AUTH_ENABLED=false` or `RUNBOOK_API_DEMO_INSECURE=true`.

```bash
RUNBOOK_API_AUTH_ENABLED=true
RUNBOOK_API_TOKEN='replace-with-write-token'
RUNBOOK_API_READ_ONLY_TOKEN='optional-read-token'
RUNBOOK_API_AUTH_HEADER=x-runbook-token
```

Protected endpoints accept either:

```http
Authorization: Bearer <token>
```

or:

```http
x-runbook-token: <token>
```

Public paths are intentionally small: `/`, `/health`, `/auth/status`, `/favicon.ico` and `/web/*`. API docs endpoints are disabled in the FastAPI app by default. Feishu/WeCom webhook paths bypass the Runbook API token only when their own platform verification/encryption secrets are configured; otherwise they require the same API token as any other write route. The read-only token can call safe GET/HEAD/OPTIONS routes only after `RUNBOOK_API_TOKEN` is configured.

## Citation RAG

RAG is local and offline by default. It stores documents and chunks in SQLite FTS5 under `RUNBOOK_RAG_DIR`.

Environment:

```bash
RUNBOOK_RAG_ENABLED=true
RUNBOOK_RAG_DIR=.runbook_hermes_store/rag
RUNBOOK_RAG_CHUNK_CHARS=1200
RUNBOOK_RAG_CHUNK_OVERLAP=160
RUNBOOK_RAG_CONTEXT_LIMIT=5
```

API:

```http
GET  /rag/status
GET  /rag/documents
POST /rag/ingest-text
POST /rag/ingest-path
GET  /rag/search?query=connection%20pool&service=payment-service
GET  /rag/context?query=rollback&service=payment-service
```

Tools exposed to Hermes:

- `runbook_rag_status`
- `runbook_rag_ingest_text`
- `runbook_rag_search`
- `runbook_rag_context`

Incident creation now recalls both `memory_context` and `rag_context`. RAG context is fenced as `<rag-context>` with explicit citations like `source#chunk-1`.

## Benchmark / eval

Benchmark cases live in `data/runbook_benchmark/eval_cases.json`.

Run locally:

```bash
python scripts/runbook_eval.py
python scripts/runbook_eval.py --list
python scripts/runbook_eval.py --case payment_503_spike
```

API:

```http
GET  /eval/benchmarks
POST /eval/run
GET  /eval/runs
```

Metrics include:

- `rca_accuracy`
- `action_accuracy`
- `evidence_min_rate`
- `safety_gate_rate`
- weighted `score`
- `pass_rate`

By default eval uses a temporary store so it does not pollute production incidents. Set `RUNBOOK_EVAL_PERSIST_DEFAULT=true` or pass `persist=true` to keep eval runs.

## Multimodal AIOps evidence

The pipeline converts visual or semi-visual incident artifacts into ordinary evidence records:

- Grafana screenshot -> visual anomaly summary
- Feishu alert card image/payload -> alert context evidence
- topology diagram OCR/text -> dependency nodes and edges
- log screenshot OCR/text -> log anomaly evidence
- monitoring dashboard snapshot -> deterministic dashboard anomaly summary

Environment:

```bash
RUNBOOK_MULTIMODAL_ENABLED=true
RUNBOOK_MULTIMODAL_COLLECT_DASHBOARDS=true
RUNBOOK_MULTIMODAL_USE_HERMES_VISION=false
```

When `RUNBOOK_MULTIMODAL_USE_HERMES_VISION=true`, RunbookHermes attempts to delegate image analysis to Hermes `vision_analyze`; otherwise it uses deterministic text hints, payloads, topology parsing and dashboard snapshots.

API:

```http
POST /multimodal/analyze
POST /incidents/{incident_id}/multimodal-evidence
```

Tools exposed to Hermes:

- `runbook_multimodal_analyze`
- `runbook_topology_parse`

Example request:

```json
{
  "service": "payment-service",
  "summary": "Grafana screenshot shows p95 latency and HTTP 503 spike",
  "visual_refs": [
    {
      "kind": "grafana_screenshot",
      "image_url": "https://grafana.example/d/abc",
      "text_hint": "HTTP 503 spike, p95 latency 2s, v2.3.1 deploy marker"
    },
    {
      "kind": "topology_diagram",
      "text_hint": "payment-service -> coupon-service -> redis"
    }
  ],
  "include_dashboard_snapshot": true
}
```

## Validation

Run the new validation suite:

```bash
python scripts/runbook_hardening_validate.py
```

It checks memory kind normalization, the environment bug fix, API auth, local RAG ingestion/search, multimodal evidence, incident integration and benchmark pass rate.
