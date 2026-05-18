#!/usr/bin/env python3
from __future__ import annotations

from runbook_bootstrap import PROJECT_ROOT, bootstrap
bootstrap()
ROOT = PROJECT_ROOT

import json
import os
import sys
import tempfile
from pathlib import Path



def main() -> int:
    with tempfile.TemporaryDirectory(prefix="runbook-hermes-bridge-") as tmp:
        root = Path(tmp)
        os.environ["RUNBOOK_STORE_DIR"] = str(root / "store")
        os.environ["RUNBOOK_MEMORY_DIR"] = str(root / "memory")
        os.environ["HERMES_HOME"] = str(root / "hermes-home")
        os.environ["RUNBOOK_MEMORY_ENABLED"] = "true"
        os.environ["RUNBOOK_MEMORY_BRIDGE_ENABLED"] = "true"
        os.environ["RUNBOOK_MEMORY_ROUTER_ENABLED"] = "true"
        os.environ["RUNBOOK_FEISHU_MEMORY_ROUTER_ENABLED"] = "true"
        os.environ["RUNBOOK_SKILL_PUBLISH_ENABLED"] = "true"
        os.environ["RUNBOOK_SKILL_PUBLISH_CATEGORY"] = "runbooks/runbookhermes"

        from plugins.memory import discover_memory_providers, load_memory_provider
        from runbook_hermes.hermes_bridge import bridge_status, prefetch_context
        from runbook_hermes.memory import get_memory_manager
        from runbook_hermes.memory_router import RunbookMemoryRouter
        from runbook_hermes.skill_publisher import get_skill_publisher

        providers = {name for name, _desc, _available in discover_memory_providers()}
        assert "runbook_hermes" in providers, f"runbook_hermes provider not discovered: {providers}"
        assert "incident_memory" in providers, "compatibility alias incident_memory not discovered"

        provider = load_memory_provider("runbook_hermes")
        assert provider is not None, "runbook_hermes provider failed to load"
        assert provider.is_available(), "runbook_hermes provider is not available"
        provider.initialize(session_id="test-session", platform="feishu", agent_context="primary", hermes_home=str(root / "hermes-home"))
        prompt = provider.system_prompt_block()
        assert "MemoryProvider" in prompt and "RunbookHermes" in prompt, prompt[:300]

        router = RunbookMemoryRouter()
        incident = router.route_message("payment-service P1 503 告警，帮我排障", source="feishu", metadata={"event_type": "chat_message"})
        assert incident.action == "create_incident", incident.to_dict()
        governance = router.route_message("记住 coupon-service 高峰期必须先降级并通知营销值班，不要直接 rollback", source="feishu")
        assert governance.action == "write_memory", governance.to_dict()
        applied = router.apply(governance)
        assert applied["status"] == "ok", applied
        assert applied.get("indexed_memory", {}).get("status") == "ok", applied
        session_only = router.route_message("我喜欢中文回答", source="feishu")
        assert session_only.target_plane.startswith("hermes_native"), session_only.to_dict()

        manager = get_memory_manager()
        recall = manager.search("coupon 高峰期 rollback", service="coupon-service")
        assert recall["hits"], recall
        provider_context = provider.prefetch("coupon-service 高峰期 rollback 规则")
        assert "RunbookHermes domain memory recall" in provider_context, provider_context
        assert prefetch_context("coupon-service 高峰期 rollback 规则")

        published = get_skill_publisher().publish_generated_skill(
            {
                "skill_id": "skill_test",
                "incident_id": "inc_test",
                "service": "coupon-service",
                "title": "coupon-service timeout runbook",
                "body": "Collect metrics, verify 504 timeout, prefer graceful degradation, then verify recovery.",
            },
            incident={"incident_id": "inc_test", "service": "coupon-service", "summary": "coupon-service 504 timeout"},
        )
        assert published["status"] == "published", published
        assert Path(published["path"]).exists(), published
        assert "runbooks/runbookhermes" in published["relative_path"], published
        reindexed = manager.reindex_skills()
        assert reindexed["indexed_count"] >= 1, reindexed

        status = bridge_status()
        assert status["expected_memory_provider"] == "runbook_hermes", status
        assert status["skill_publisher"]["hermes_official_skill_system"] is True, status

        tools = {schema["name"] for schema in provider.get_tool_schemas()}
        for name in {"runbook_memory_route", "runbook_publish_skill", "runbook_memory_recall", "runbook_skill_publish_status"}:
            assert name in tools, tools

        print(
            json.dumps(
                {"status": "ok", "provider": provider.name, "published": published["relative_path"], "reindexed": reindexed["indexed_count"]},
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
