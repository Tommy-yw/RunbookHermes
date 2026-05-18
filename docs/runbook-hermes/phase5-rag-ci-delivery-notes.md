# RunbookHermes Phase 5: CI, Evaluation Gates and Enterprise RAG

This phase turns the prior validation scripts into a CI-friendly pytest suite and upgrades the local RAG subsystem into an enterprise-shaped retrieval pipeline that can run offline by default and later swap in managed embedding/vector backends.

## Test and CI loop

- `tests/runbook/` contains pytest coverage for migrated validation scripts, API contracts, eval regression gates, Docker smoke, training isolation and enterprise RAG behavior.
- `scripts/runbook_eval_regression_gate.py` runs the deterministic RunbookHermes benchmark and enforces pass-rate, score, citation, evidence-recall and false-rollback thresholds.
- `scripts/runbook_docker_smoke.sh` verifies the Docker build context keeps required RunbookHermes data, skills and Web assets. `RUNBOOK_DOCKER_SMOKE_MODE=build` enables a real image build on runners with Docker.
- `.github/workflows/runbook-hermes-ci.yml` runs compile checks, pytest, the eval gate and Docker static smoke on PRs/pushes.

## Training isolation

`/training/pipeline/run` and `runbook_hermes.training.run_auto_pipeline()` now only prepare datasets, compressed trajectories and handoff manifests. They never launch cloud jobs, even when `dry_run=false` is passed.

Real external launch is isolated behind `/training/external-launch` and `external_launch_training()`. It requires all of the following:

```env
RUNBOOK_TRAINING_EXTERNAL_LAUNCH_ENABLED=true
RUNBOOK_TRAINING_EXTERNAL_LAUNCH_TOKEN=<strong-token>
RUNBOOK_ALICLOUD_AUTOPIPELINE_ENABLED=true
RUNBOOK_ALICLOUD_AUTOPIPELINE_EXECUTE=true
```

## Enterprise RAG capabilities

The local RAG implementation now supports:

- data cleaning and boilerplate removal
- heading-aware chunking with overlap and content hash dedupe
- deterministic local hash embeddings for offline operation
- SQLite FTS5 lexical retrieval
- vector cosine retrieval
- LIKE fallback retrieval
- Reciprocal Rank Fusion style candidate fusion
- local feature reranking
- citation IDs and score breakdowns
- ACL / tenant-style permission filtering
- document freshness and `expires_at` filtering
- diagnostics for low recall, noise, staleness and permission filters
- query-set evaluation with context precision, context recall, MRR, noise rate and pass rate

The default embedding provider is intentionally offline and deterministic (`local-hash-embedding-v1`). Production deployments can replace that provider with OpenAI-compatible embeddings, bge/e5/Cohere, Qdrant, Milvus, pgvector, OpenSearch vector, or an internal enterprise retrieval service without changing the RunbookHermes API contract.
