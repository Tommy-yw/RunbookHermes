# RunbookHermes Phase 3/4 Delivery Notes

Date: 2026-05-12

## Phase 3: storage and concurrency

- Added `runbook_hermes.store.Store`, a backend-neutral store interface used by incident, approval, event, eval and training flows.
- Kept `JsonStore` as the local/default backend, but wrapped read-modify-write operations in a process/thread lock and atomic temp-file replace.
- Added `SQLiteStore` with schema tables for incidents, evidence, hypotheses, actions, approvals, checkpoints, skills and events, while retaining JSON payloads for forward-compatible fields.
- Added optional `PostgresStore` using `psycopg`/`psycopg2` when installed; it creates typed JSONB-backed tables for incidents, evidence, hypotheses, actions, approvals, checkpoints, skills and events, plus a generic key/value table for extension buckets.
- Added `runbook_hermes/storage_schema.py` for canonical bucket key fields, schema versioning, SQLite DDL/indexes and Postgres DDL/indexes.

Configuration:

```env
RUNBOOK_STORE_BACKEND=json       # json | sqlite | postgres
RUNBOOK_STORE_DIR=.runbook_hermes_store
RUNBOOK_STORE_SQLITE_PATH=.runbook_hermes_store/runbook_store.sqlite3
RUNBOOK_STORE_POSTGRES_DSN=
# install optional driver with: pip install "hermes-agent[runbook-postgres]"
```

## Phase 4: real AIOps adapters

- Standardized Prometheus, Loki, Jaeger and Tempo adapters around a shared evidence shape with `adapter_version=observability.v2`.
- Implemented Tempo search instead of a placeholder shell.
- Added Kubernetes and Argo CD rollback command construction and controlled execution gates.
- Added service profiles in `data/runbook_profiles/services.json` and wired them into RCA and action planning.
- Upgraded RCA from keyword-only matching to an evidence graph plus service-profile policy rules, with optional model-assisted summary when `RUNBOOK_MODEL_ENABLED=true`.

Rollback adapter configuration:

```env
ROLLBACK_BACKEND_KIND=mock       # mock | demo_file | kubernetes | argocd
RUNBOOK_CONTROLLED_EXECUTION_ENABLED=false
RUNBOOK_K8S_NAMESPACE=default
RUNBOOK_K8S_ROLLBACK_MODE=deployment_image
RUNBOOK_K8S_IMAGE_REPOSITORY=
RUNBOOK_ARGOCD_SERVER=
RUNBOOK_ARGOCD_AUTH_TOKEN=
RUNBOOK_ARGOCD_APP=
```

Real rollback adapters are dry-run by default. Non-dry-run execution still requires the existing approval/checkpoint path and `RUNBOOK_CONTROLLED_EXECUTION_ENABLED=true`.
