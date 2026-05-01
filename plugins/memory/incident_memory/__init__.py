from __future__ import annotations

import json
from typing import Any, Dict, List
from agent.memory_provider import MemoryProvider
from runbook_hermes.config import load_settings
from runbook_hermes.store import JsonStore

class IncidentMemoryProvider(MemoryProvider):
    @property
    def name(self) -> str:
        return "incident_memory"

    def is_available(self) -> bool:
        return True

    def initialize(self, session_id: str, **kwargs) -> None:
        self.session_id = session_id
        self.store = JsonStore(load_settings().store_dir)
        self.agent_context = kwargs.get("agent_context", "primary")

    def system_prompt_block(self) -> str:
        return "RunbookHermes stable memory stores only service profiles, team preferences, incident summaries and skill indexes. Raw logs and traces must not be stored."

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        data = getattr(self, "store", JsonStore(load_settings().store_dir)).read("incident_summaries")
        if not data:
            return ""
        latest = list(data.values())[-3:]
        return "Relevant incident memory:\n" + json.dumps(latest, ensure_ascii=False)

    def sync_turn(self, user_content: str, assistant_content: str, *, session_id: str = "") -> None:
        return None

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [{"name": "runbook_memory_search", "description": "Search stable incident memory.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}]

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        if tool_name != "runbook_memory_search":
            return json.dumps({"error": "unknown memory tool"})
        return json.dumps({"status": "ok", "memory": self.prefetch(args.get("query", ""))}, ensure_ascii=False)

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        if getattr(self, "agent_context", "primary") != "primary":
            return
        store = getattr(self, "store", JsonStore(load_settings().store_dir))
        key = f"incident_summary_{len(store.read('incident_summaries')) + 1}"
        store.put("incident_summaries", key, {"summary_id": key, "message_count": len(messages), "note": "Session ended; summarize resolved incident if evidence was present."})

    def on_pre_compress(self, messages: List[Dict[str, Any]]) -> str:
        return "Preserve evidence IDs, approval IDs, checkpoint IDs and action IDs when compressing RunbookHermes context."

    def on_delegation(self, task: str, result: str, *, child_session_id: str = "", **kwargs) -> None:
        return None

    def shutdown(self) -> None:
        return None


def register(ctx):
    ctx.register_memory_provider(IncidentMemoryProvider())
