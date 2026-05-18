# RunbookHermes Phase 1 and Phase 2 Delivery Notes

## Phase 1: cleanup and deliverability

- Runtime artifacts are excluded from release archives: `.git`, `__pycache__`, Python bytecode, `.runbook_hermes_store`, sqlite stores, validation output, build directories and egg-info metadata.
- `.dockerignore` now keeps RunbookHermes runtime resources in the Docker build context, including data fixtures, web assets, profiles, plugins, docs and runbook skill files.
- `MANIFEST.in` and `pyproject.toml` include RunbookHermes data, demo, docs, profiles, plugins, skills, web assets and scripts so source and wheel builds keep required resources.
- `scripts/runbook_bootstrap.py` provides one project-root bootstrap path for direct script execution. `scripts/_runbook_bootstrap.py` is kept as a compatibility wrapper.
- Timeline event allowlisting now covers memory, RAG, multimodal, gateway and skill publication events. Unknown event names are recorded as `event.unknown` instead of being misclassified as `incident.created`.

## Phase 2: production safety boundary

- API authentication is enabled by default. Health, auth status and static web assets remain public; protected APIs fail closed when no write token is configured.
- The Web UI can store a local API token and sends both `x-runbook-token` and `Authorization: Bearer` headers on API calls.
- RAG path ingestion is restricted to `RUNBOOK_RAG_ALLOWED_ROOTS`, and document safety scanning checks the full body in chunks before indexing.
- Feishu/Lark and WeCom gateway callbacks share a verification/decryption layer with timestamp replay checks. Unsigned local fixture callbacks are blocked by default and require explicit opt-in.
- Non-rollback actions require a configured executor backend, an operation allowlist, an approved approval record, a second confirmation token, and an audit record with `audit_id`.

## Local validation mode

For isolated local fixture tests, explicitly opt into insecure demo settings:

```bash
export RUNBOOK_API_AUTH_ENABLED=false
export RUNBOOK_GATEWAY_ALLOW_UNSIGNED_CALLBACKS=true
```

For production, keep the defaults and configure long random tokens plus platform webhook secrets.
