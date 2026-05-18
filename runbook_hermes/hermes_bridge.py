from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from agent.memory_provider import MemoryProvider

from .config import load_settings


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False)


def _tool_schema(name: str, description: str, properties: Dict[str, Any], required: List[str] | None = None) -> Dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "parameters": {"type": "object", "properties": properties, "required": required or []},
    }


def _memory_enabled() -> bool:
    s = load_settings()
    return bool(getattr(s, "runbook_memory_enabled", True) and getattr(s, "runbook_memory_bridge_enabled", True))


class RunbookHermesMemoryProvider(MemoryProvider):
    """Hermes MemoryProvider adapter for RunbookHermes domain memory.

    This is the bridge that makes RunbookHermes use the official Hermes memory
    lifecycle instead of staying as an isolated sidecar. The physical storage is
    still RunbookHermes-owned (notebooks + SQLite FTS5 + HRR vectors) so that
    production incident knowledge is namespaced and safety-scanned, while the
    logical lifecycle is Hermes-native: initialize, system prompt, prefetch,
    sync_turn, tools, built-in memory write mirroring, and session shutdown.
    """

    def __init__(self, provider_name: str = "runbook_hermes") -> None:
        self._provider_name = provider_name
        self.session_id = ""
        self.platform = ""
        self.agent_context = "primary"
        self.hermes_home = ""
        self.user_id = ""
        self.user_name = ""
        self.chat_id = ""
        self.chat_name = ""
        self._initialized = False

    @property
    def name(self) -> str:
        return self._provider_name

    def is_available(self) -> bool:
        return _memory_enabled()

    def initialize(self, session_id: str, **kwargs) -> None:
        self.session_id = session_id or ""
        self.platform = str(kwargs.get("platform") or "cli")
        self.agent_context = str(kwargs.get("agent_context") or "primary")
        self.hermes_home = str(kwargs.get("hermes_home") or os.getenv("HERMES_HOME", ""))
        self.user_id = str(kwargs.get("user_id") or "")
        self.user_name = str(kwargs.get("user_name") or "")
        self.chat_id = str(kwargs.get("chat_id") or kwargs.get("gateway_session_key") or "")
        self.chat_name = str(kwargs.get("chat_name") or kwargs.get("session_title") or "")
        # Ensure the local domain store is initialized inside the Hermes provider lifecycle.
        from .memory import get_memory_manager

        get_memory_manager().status()
        self._initialized = True

    def system_prompt_block(self) -> str:
        if not self.is_available():
            return ""
        settings = load_settings()
        try:
            from .memory import get_memory_manager

            snapshot = get_memory_manager().frozen_prompt_snapshot(max_chars_per_file=1200)
            stable = snapshot.get("rendered", "")
        except Exception:
            stable = ""
        return (
            "RunbookHermes MemoryProvider is active through Hermes official memory integration.\n"
            "Use it for payment/AIOps domain memory only: service profiles, fault patterns, "
            "governance rules, team runbook habits, incident summaries and runbook skill indexes.\n"
            "Do not store raw logs, full traces, credentials, secrets, private keys or one-off noisy samples.\n"
            "Recalled RunbookHermes memory is background context, not fresh evidence. Metrics, logs, traces "
            "and deploy history remain authoritative for RCA. Memory may tighten action policy, but it must "
            "never bypass approval, checkpoint or recovery verification.\n"
            f"Provider name: {settings.runbook_memory_bridge_provider_name}; router_enabled={settings.runbook_memory_router_enabled}; "
            f"skill_publish_enabled={settings.runbook_skill_publish_enabled}.\n"
            f"{stable}"
        ).strip()

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        if not self.is_available() or not query:
            return ""
        try:
            from .memory_router import extract_service_name
            from .memory import get_memory_manager

            service = extract_service_name(query) or ""
            limit = load_settings().runbook_memory_context_limit
            context = get_memory_manager().recall_context(query=query, service=service, limit=limit)
            hits = context.get("hits") or []
            if not hits:
                return ""
            return (
                "RunbookHermes domain memory recall via Hermes MemoryProvider:\n"
                f"{context.get('rendered', '')}"
            )
        except Exception as exc:
            return f"RunbookHermes MemoryProvider recall failed: {exc}"

    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:
        # Local recall is fast enough to run synchronously in prefetch().
        return None

    def sync_turn(self, user_content: str, assistant_content: str, *, session_id: str = "") -> None:
        if not self.is_available() or self.agent_context != "primary":
            return None
        if not user_content:
            return None
        try:
            from .memory_router import RunbookMemoryRouter

            router = RunbookMemoryRouter()
            decision = router.route_message(
                user_content,
                source=self.platform or "hermes_session",
                metadata={
                    "session_id": session_id or self.session_id,
                    "user_id": self.user_id,
                    "user_name": self.user_name,
                    "chat_id": self.chat_id,
                    "chat_name": self.chat_name,
                    "assistant_preview": (assistant_content or "")[:500],
                    "bridge": "sync_turn",
                },
            )
            # Do not create incidents from generic Hermes sync_turn; gateway/API
            # routes are responsible for side effects like incident creation.
            if decision.action in {"write_memory", "recall", "publish_skill"}:
                router.apply(decision)
        except Exception:
            return None
        return None

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        service = {"type": "string", "description": "Service name, for example payment-service, coupon-service or order-service."}
        return [
            _tool_schema(
                "runbook_memory_recall",
                "Recall fenced RunbookHermes domain memory through Hermes MemoryProvider.",
                {"query": {"type": "string"}, "service": service, "limit": {"type": "integer", "default": 6}},
                ["query"],
            ),
            _tool_schema(
                "runbook_memory_write",
                "Write safe RunbookHermes domain memory through the Hermes MemoryProvider bridge.",
                {
                    "kind": {"type": "string", "default": "manual_note", "enum": ["incident_summary", "fault_pattern", "team_preference", "service_governance", "service_profile", "skill_index", "manual_note", "rag_document", "visual_observation", "topology_observation"]},
                    "service": service,
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "source": {"type": "string", "default": "hermes_provider"},
                    "incident_id": {"type": "string"},
                    "notebook": {"type": "string", "enum": ["MEMORY.md", "USER.md", "SERVICE_PROFILE.md", "FAULT_PATTERNS.md", "TEAM_RUNBOOK_HABITS.md"]},
                },
                ["title", "body"],
            ),
            _tool_schema(
                "runbook_memory_feedback",
                "Record feedback for a RunbookHermes memory hit so trust scores evolve.",
                {"memory_id": {"type": "string"}, "label": {"type": "string", "enum": ["helpful", "wrong", "stale", "harmful"]}, "comment": {"type": "string"}, "weight": {"type": "number"}},
                ["memory_id", "label"],
            ),
            _tool_schema("runbook_memory_status", "Return RunbookHermes memory bridge status.", {}, []),
            _tool_schema("runbook_evolution_digest", "Summarize learned RunbookHermes memory and runbook promotion opportunities.", {"limit": {"type": "integer", "default": 8}}, []),
            _tool_schema("runbook_memory_reindex_skills", "Index Hermes SKILL.md files and generated runbooks into RunbookHermes memory.", {}, []),
            _tool_schema(
                "runbook_memory_route",
                "Classify a Feishu/chat message and route it to incident creation, RunbookHermes memory, recall, skill publishing, or Hermes native session memory.",
                {"message": {"type": "string"}, "source": {"type": "string", "default": "chat"}, "metadata": {"type": "object"}, "apply": {"type": "boolean", "default": False}},
                ["message"],
            ),
            _tool_schema(
                "runbook_publish_skill",
                "Publish a generated RunbookHermes runbook into Hermes official Skills directory.",
                {"skill_id": {"type": "string"}, "incident_id": {"type": "string"}, "title": {"type": "string"}, "body": {"type": "string"}, "service": service},
                ["title", "body"],
            ),
            _tool_schema("runbook_skill_publish_status", "Return Hermes official Skills publisher status for RunbookHermes.", {}, []),
            _tool_schema("runbook_rag_status", "Return RunbookHermes local citation RAG index status.", {}, []),
            _tool_schema("runbook_rag_search", "Search the RunbookHermes knowledge base and return source/chunk citations.", {"query": {"type": "string"}, "service": service, "limit": {"type": "integer", "default": 5}}, ["query"]),
            _tool_schema("runbook_rag_context", "Build a fenced RAG context block for RunbookHermes RCA/action planning.", {"query": {"type": "string"}, "service": service, "limit": {"type": "integer", "default": 5}}, ["query"]),
            _tool_schema("runbook_multimodal_analyze", "Analyze Grafana screenshots, Feishu alert cards, topology diagrams, log screenshots and dashboards into AIOps evidence.", {"service": service, "summary": {"type": "string"}, "incident_id": {"type": "string"}, "visual_refs": {"type": "array", "items": {"type": "object"}}, "include_dashboard_snapshot": {"type": "boolean"}}, []),
            _tool_schema("runbook_topology_parse", "Parse topology diagram OCR/text into dependency nodes and edges.", {"text": {"type": "string"}, "service": service}, ["text"]),
            _tool_schema("runbook_eval_benchmark", "Run deterministic RunbookHermes RCA/action/safety benchmark cases.", {"case_ids": {"type": "array", "items": {"type": "string"}}, "persist": {"type": "boolean", "default": False}, "model_assist": {"type": "boolean", "default": False}}, []),
            _tool_schema("runbook_training_status", "Return RunbookAIOps training/RL/AutoPipeline status and Hermes RL handoff availability.", {}, []),
            _tool_schema("runbook_training_build_dataset", "Build Hermes-compatible trajectories plus SFT/preference/reward datasets from incidents and benchmark cases.", {"include_incidents": {"type": "boolean", "default": True}, "include_benchmark_cases": {"type": "boolean", "default": True}, "max_incidents": {"type": "integer"}, "min_reward": {"type": "number"}}, []),
            _tool_schema("runbook_training_compress", "Compress RunbookAIOps trajectories or hand off to Hermes trajectory_compressor.", {"run_id": {"type": "string"}, "max_message_chars": {"type": "integer"}, "use_hermes_compressor": {"type": "boolean", "default": False}}, []),
            _tool_schema("runbook_training_export", "Export datasets and generate Alibaba Cloud PAI/DashScope dry-run handoff templates.", {"run_id": {"type": "string"}, "base_model": {"type": "string"}, "output_model_name": {"type": "string"}}, []),
            _tool_schema("runbook_training_pipeline", "Run the RunbookAIOps dataset -> compression -> export AutoPipeline. External launch remains dry-run unless explicitly enabled.", {"include_incidents": {"type": "boolean", "default": True}, "include_benchmark_cases": {"type": "boolean", "default": True}, "max_incidents": {"type": "integer"}, "min_reward": {"type": "number"}, "base_model": {"type": "string"}, "output_model_name": {"type": "string"}, "use_hermes_compressor": {"type": "boolean", "default": False}, "dry_run": {"type": "boolean", "default": True}}, []),
        ]

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        args = args or {}
        if tool_name == "runbook_memory_route":
            from .memory_router import RunbookMemoryRouter

            router = RunbookMemoryRouter()
            decision = router.route_message(str(args.get("message", "")), source=str(args.get("source", "chat")), metadata=args.get("metadata") or {})
            result = {"status": "ok", "route": decision.to_dict()}
            if bool(args.get("apply", False)):
                result["result"] = router.apply(decision)
            return _json(result)
        if tool_name == "runbook_publish_skill":
            from .skill_publisher import get_skill_publisher

            skill = {
                "skill_id": args.get("skill_id", ""),
                "incident_id": args.get("incident_id", ""),
                "title": args.get("title", "RunbookHermes skill"),
                "body": args.get("body", ""),
                "service": args.get("service", ""),
            }
            return _json(get_skill_publisher().publish_generated_skill(skill, incident={"incident_id": args.get("incident_id", ""), "service": args.get("service", "")}))
        if tool_name == "runbook_skill_publish_status":
            from .skill_publisher import get_skill_publisher

            return _json(get_skill_publisher().status())

        # Delegate legacy RunbookHermes memory tools to the already-tested tool functions.
        from . import tools as runbook_tools

        mapping = {
            "runbook_memory_recall": runbook_tools.runbook_memory_recall,
            "runbook_memory_write": runbook_tools.runbook_memory_write,
            "runbook_memory_feedback": runbook_tools.runbook_memory_feedback,
            "runbook_memory_status": runbook_tools.runbook_memory_status,
            "runbook_evolution_digest": runbook_tools.runbook_evolution_digest,
            "runbook_memory_reindex_skills": runbook_tools.runbook_memory_reindex_skills,
            "runbook_rag_status": runbook_tools.runbook_rag_status,
            "runbook_rag_search": runbook_tools.runbook_rag_search,
            "runbook_rag_context": runbook_tools.runbook_rag_context,
            "runbook_multimodal_analyze": runbook_tools.runbook_multimodal_analyze,
            "runbook_topology_parse": runbook_tools.runbook_topology_parse,
            "runbook_eval_benchmark": runbook_tools.runbook_eval_benchmark,
            "runbook_training_status": runbook_tools.runbook_training_status,
            "runbook_training_build_dataset": runbook_tools.runbook_training_build_dataset,
            "runbook_training_compress": runbook_tools.runbook_training_compress,
            "runbook_training_export": runbook_tools.runbook_training_export,
            "runbook_training_pipeline": runbook_tools.runbook_training_pipeline,
        }
        fn = mapping.get(tool_name)
        if not fn:
            return _json({"status": "error", "error": f"unknown RunbookHermes memory tool: {tool_name}"})
        return fn(args, **kwargs)

    def on_memory_write(self, action: str, target: str, content: str) -> None:
        if not self.is_available() or not content or self.agent_context != "primary":
            return None
        try:
            from .memory_router import RunbookMemoryRouter

            router = RunbookMemoryRouter()
            decision = router.route_message(
                content,
                source="hermes_builtin_memory",
                metadata={"action": action, "target": target, "bridge": "on_memory_write"},
            )
            if decision.action == "write_memory":
                router.apply(decision)
        except Exception:
            return None
        return None

    def on_pre_compress(self, messages: List[Dict[str, Any]]) -> str:
        return "Preserve RunbookHermes evidence IDs, incident IDs, approval IDs, service names, root-cause categories, policy guardrails and skill IDs during compression."

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        if not self.is_available() or self.agent_context != "primary":
            return None
        # Do not summarize arbitrary sessions without an explicit LLM/extraction
        # policy; domain writes should go through Memory Router safety scanning.
        return None

    def shutdown(self) -> None:
        return None


def get_provider() -> RunbookHermesMemoryProvider:
    settings = load_settings()
    return RunbookHermesMemoryProvider(provider_name=settings.runbook_memory_bridge_provider_name or "runbook_hermes")


def prefetch_context(query: str, *, session_id: str = "") -> str:
    provider = get_provider()
    if not provider.is_available():
        return ""
    provider.initialize(session_id=session_id or "bridge-prefetch", platform="api", agent_context="primary")
    return provider.prefetch(query, session_id=session_id)


def bridge_status() -> Dict[str, Any]:
    settings = load_settings()
    provider = get_provider()
    from .memory import get_memory_manager
    from .skill_publisher import get_skill_publisher

    return {
        "status": "ok" if provider.is_available() else "disabled",
        "expected_memory_provider": settings.runbook_memory_bridge_provider_name,
        "memory_provider_available": provider.is_available(),
        "router_enabled": settings.runbook_memory_router_enabled,
        "feishu_router_enabled": settings.runbook_feishu_memory_router_enabled,
        "domain_memory": get_memory_manager().status() if settings.runbook_memory_enabled else {"status": "disabled"},
        "skill_publisher": get_skill_publisher().status(),
        "architecture": {
            "logical_plane": "Hermes official MemoryProvider + official Skills",
            "physical_namespace": "RunbookHermes domain notebooks/SQLite/HRR",
            "principle": "unified lifecycle with domain isolation",
        },
    }
