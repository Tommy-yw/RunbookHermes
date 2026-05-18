from __future__ import annotations

# Compatibility import surface for gateway-native webhook verification helpers.
# The implementation lives at runbook_hermes.webhook_security so the API layer
# and gateway normalizers can share the same code path.

from runbook_hermes.webhook_security import (  # noqa: F401
    WebhookSecurityError,
    prepare_feishu_payload,
    prepare_wecom_payload,
)
