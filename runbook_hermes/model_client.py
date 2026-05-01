from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, List

from .config import Settings, load_settings


class RunbookModelClient:
    """Small OpenAI-compatible model client for the Runbook API layer.

    Hermes owns the main inference provider. This helper is intentionally thin:
    it lets the Runbook web/API layer summarize an incident or generate a card
    without inventing a second agent runtime.

    If no key is configured, calls return a deterministic disabled payload.
    """

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or load_settings()

    def enabled(self) -> bool:
        return bool(self.settings.runbook_model_enabled and self.settings.runbook_model_api_key)

    def chat(self, messages: List[Dict[str, str]], model: str | None = None) -> Dict[str, Any]:
        if not self.enabled():
            return {
                "enabled": False,
                "status": "disabled",
                "content": "LLM is disabled. Set RUNBOOK_MODEL_ENABLED=true and RUNBOOK_MODEL_API_KEY to enable model-assisted summaries.",
            }

        base = self.settings.runbook_model_base_url.rstrip("/")
        url = f"{base}/chat/completions"
        payload = {
            "model": model or self.settings.runbook_model_name,
            "temperature": self.settings.runbook_model_temperature,
            "messages": messages,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.settings.runbook_model_api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return {"enabled": True, "status": "http_error", "code": exc.code, "content": exc.read().decode("utf-8", "ignore")[:1000]}
        except Exception as exc:  # pragma: no cover - network dependent
            return {"enabled": True, "status": "error", "content": str(exc)}

        content = ""
        try:
            content = body["choices"][0]["message"]["content"]
        except Exception:
            content = json.dumps(body, ensure_ascii=False)[:2000]
        return {"enabled": True, "status": "ok", "content": content, "raw": body}

    def summarize_incident(self, incident: Dict[str, Any]) -> Dict[str, Any]:
        system = (
            "你是 RunbookHermes 的值班排障助手。"
            "只能基于给定 evidence、hypothesis、action、approval 信息总结，不能编造证据。"
            "如果 action 风险高，必须强调需要审批、checkpoint 和 dry-run。"
        )
        user = "请把下面 incident 总结成适合飞书卡片和网页展示的中文摘要：\n" + json.dumps(incident, ensure_ascii=False, indent=2)
        return self.chat([{"role": "system", "content": system}, {"role": "user", "content": user}])
