# Backend contracts

Stable tool outputs are JSON objects/lists with `evidence_id`, `source`, `service`, `summary`, `raw_ref` and typed fields. Real Prometheus, Loki, Trace and Deploy adapters should preserve these fields so RCA and policy guards do not change.
