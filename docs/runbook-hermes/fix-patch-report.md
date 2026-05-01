# RunbookHermes Final Overlay Fix Patch

This patch fixes the issues found during the post-merge audit of the Hermes-native RunbookHermes final overlay.

## Fixed issues

1. **Payment demo initial state**
   - Reset `data/payment_demo/runtime/payment-service-version.txt` to `v2.3.1`.
   - Reset `data/payment_demo/deployments.json` so the active version is `v2.3.1` and the previous version is `v2.3.0`.
   - Removed validation-generated rollback history from the release artifact.

2. **Prometheus HTTP status labels**
   - Fixed demo service `observe()` helpers so `HTTPException(status_code=503/504/429)` is recorded as `503/504/429`, not overwritten as `500`.

3. **Jaeger/OTLP request spans**
   - Added one request span per observed endpoint in the demo services.
   - Spans include service name, HTTP method, route and status code.

4. **ACTION_EXECUTION_* configuration**
   - `load_settings()` now reads `ACTION_EXECUTION_BACKEND`, `ACTION_EXECUTION_API_BASE_URL`, `ACTION_EXECUTION_API_TOKEN`, and `ACTION_EXECUTION_TIMEOUT_SECONDS`.

5. **Recovery event type**
   - Added `recovery.verified` to allowed event types.

6. **Gateway event timeline binding**
   - Gateway normalizers no longer record events under service names.
   - API routes record gateway events after a real `incident_id` is known.

7. **Approval/checkpoint association**
   - Approval and checkpoint records now carry `incident_id`.
   - Incident details and checkpoint listing now associate by `incident_id`, not by service name.

## Validation

Run this after applying the patch:

```bash
PYTHONPATH=. python -S scripts/runbook_fix_patch_validate.py
```

Expected result:

```json
{"ok": true}
```

Recommended full validation:

```bash
PYTHONPATH=. python -S scripts/runbook_validate.py
PYTHONPATH=. python -S scripts/runbook_gateway_smoke.py
PYTHONPATH=. python -S scripts/runbook_no_legacy_imports.py
PYTHONPATH=. python -S scripts/runbook_stage2_4_validate.py
PYTHONPATH=. python -S scripts/runbook_payment_demo_smoke.py
PYTHONPATH=. python -S scripts/runbook_stage5_7_validate.py
PYTHONPATH=. python -S scripts/runbook_stage8_validate.py
PYTHONPATH=. python -S scripts/runbook_fix_patch_validate.py
```

## Notes

This patch does not change the official Hermes agent core. It only patches RunbookHermes overlay files.
