from __future__ import annotations

from typing import Any, Dict
from runbook_hermes.commands import from_alertmanager


def normalize(payload: Dict[str, Any]):
    """Normalize Alertmanager payload to IncidentCommand.

    Event recording is done after an incident_id exists, in the API/service
    layer, so gateway events appear on the real incident timeline.
    """
    return from_alertmanager(payload)
