from __future__ import annotations

from runbook_hermes.hermes_bridge import RunbookHermesMemoryProvider, get_provider


def register(ctx) -> None:
    ctx.register_memory_provider(get_provider())


__all__ = ["RunbookHermesMemoryProvider", "get_provider", "register"]
