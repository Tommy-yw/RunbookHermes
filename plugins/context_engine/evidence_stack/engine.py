from __future__ import annotations

import json
from typing import Any, Dict, List
from agent.context_engine import ContextEngine

class EvidenceStackEngine(ContextEngine):
    name = "evidence_stack"

    def __init__(self):
        self.last_prompt_tokens = 0
        self.last_completion_tokens = 0
        self.last_total_tokens = 0
        self.context_length = 128000
        self.threshold_tokens = int(self.context_length * self.threshold_percent)
        self.compression_count = 0
        self.session_id = ""

    def update_from_response(self, usage: Dict[str, Any]) -> None:
        self.last_prompt_tokens = int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0)
        self.last_completion_tokens = int(usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0)
        self.last_total_tokens = int(usage.get("total_tokens", self.last_prompt_tokens + self.last_completion_tokens) or 0)

    def should_compress(self, prompt_tokens: int = None) -> bool:
        tokens = prompt_tokens if prompt_tokens is not None else self.last_prompt_tokens
        return bool(tokens and tokens >= self.threshold_tokens)

    def should_compress_preflight(self, messages: List[Dict[str, Any]]) -> bool:
        approx = sum(len(str(m.get("content", ""))) for m in messages) // 4
        return approx >= self.threshold_tokens

    def compress(self, messages: List[Dict[str, Any]], current_tokens: int = None) -> List[Dict[str, Any]]:
        protected = messages[:self.protect_first_n] + messages[-self.protect_last_n:]
        evidence_markers = []
        for m in messages:
            content = str(m.get("content", ""))
            if any(marker in content for marker in ["evidence_id", "approval_id", "checkpoint_id", "hypothesis_id", "action_id"]):
                evidence_markers.append(content[:1200])
        summary = {
            "role": "system",
            "content": "EvidenceStack compressed context. Preserve these incident references: " + json.dumps(evidence_markers[-20:], ensure_ascii=False),
        }
        self.compression_count += 1
        return protected[: self.protect_first_n] + [summary] + protected[self.protect_first_n :]

    def on_session_start(self, session_id: str, **kwargs) -> None:
        self.session_id = session_id

    def on_session_end(self, session_id: str, messages: List[Dict[str, Any]]) -> None:
        self.session_id = ""

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [{"name": "evidence_stack_status", "description": "Return EvidenceStack compression status.", "parameters": {"type": "object", "properties": {}}}]

    def handle_tool_call(self, name: str, args: Dict[str, Any], **kwargs) -> str:
        return json.dumps({"status": self.get_status(), "session_id": self.session_id}, ensure_ascii=False)
