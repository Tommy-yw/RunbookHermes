from __future__ import annotations

from runbook_hermes.hermes_bridge import RunbookHermesMemoryProvider


class IncidentMemoryProvider(RunbookHermesMemoryProvider):
    """Backward-compatible alias for older RunbookHermes profiles.

    The original `incident_memory` provider is now an alias for the official
    Hermes bridge provider. New deployments should use `memory.provider:
    runbook_hermes`, but existing configs that still refer to `incident_memory`
    keep working and receive the same bridge behavior.
    """

    def __init__(self) -> None:
        super().__init__(provider_name="incident_memory")


def register(ctx) -> None:
    ctx.register_memory_provider(IncidentMemoryProvider())
