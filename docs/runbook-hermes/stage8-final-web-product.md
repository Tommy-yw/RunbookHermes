# Stage 8: Final Web Product

This stage turns the lightweight recovered web console into a more complete RunbookHermes product surface.

## What is included

- Incident command center with KPI cards, filters, scenario launch buttons and root-cause preview.
- Incident detail page with evidence cards, root-cause hypothesis, action plan, approvals, checkpoints, generated skills, timeline and raw JSON.
- Approval center with risk labels, approval reason, payload inspection, approve/reject actions.
- Digest page with recent incidents, high-frequency fault categories and generated runbook skills.
- Settings page that shows runtime readiness without leaking secrets.
- API endpoints for dashboard summary, runtime status, skills list and demo scenarios.
- Non-rollback controlled action executor shell.

## What is intentionally not included

- Full production Feishu/Lark encryption implementation.
- Full WeCom online callback encryption implementation.
- Production Kubernetes or Argo CD mutation.
- Production dashboards in Grafana.
- A paid model key. The OpenAI-compatible model interface is wired, but you must provide credentials.

## Safety boundary

RunbookHermes keeps these rules:

1. Evidence first, root cause second.
2. Root cause must reference evidence IDs.
3. Destructive actions must have approval and checkpoint.
4. Production mutation is disabled unless a specific executor backend is configured.
5. Demo rollback only changes local payment demo state files.
