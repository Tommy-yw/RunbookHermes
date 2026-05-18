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



def assert_ok(name: str, condition: bool, payload: object | None = None) -> None:
    if not condition:
        raise AssertionError(f"{name} failed: {payload!r}")
    print(f"[OK] {name}")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="runbook-hardening-") as tmp:
        root = Path(tmp)
        os.environ["RUNBOOK_STORE_DIR"] = str(root / "store")
        os.environ["RUNBOOK_MEMORY_DIR"] = str(root / "memory")
        os.environ["RUNBOOK_RAG_DIR"] = str(root / "rag")
        os.environ["RUNBOOK_MEMORY_HRR_DIM"] = "128"
        os.environ["RUNBOOK_MEMORY_ENABLED"] = "true"
        os.environ["RUNBOOK_RAG_ENABLED"] = "true"
        os.environ["RUNBOOK_MULTIMODAL_ENABLED"] = "true"
        os.environ["RUNBOOK_MULTIMODAL_COLLECT_DASHBOARDS"] = "true"
        os.environ["RUNBOOK_SKILL_PUBLISH_ENABLED"] = "false"
        os.environ["RUNBOOK_API_AUTH_ENABLED"] = "true"
        os.environ["RUNBOOK_API_TOKEN"] = "test-write-token"
        os.environ["RUNBOOK_API_READ_ONLY_TOKEN"] = "test-read-token"

        from fastapi.testclient import TestClient

        from apps.runbook_api.app.main import app
        from runbook_hermes import incident_service as svc
        from runbook_hermes.action_policy import plan_action
        from runbook_hermes.eval import run_eval
        from runbook_hermes.memory_router import RunbookMemoryRouter
        from runbook_hermes.multimodal import parse_topology
        from runbook_hermes.rag import get_rag_index

        router = RunbookMemoryRouter()
        decision = router.route_message(
            "记住 coupon-service 高峰期必须先降级并通知营销值班，不要直接 rollback",
            source="feishu",
            metadata={"environment": "staging"},
        )
        assert_ok("environment parsed from top-level metadata", decision.environment == "staging", decision.to_dict())
        assert_ok("memory kind normalized", decision.memory_kind == "service_governance", decision.to_dict())
        assert_ok("notebook maps governance", decision.notebook == "SERVICE_PROFILE.md", decision.to_dict())
        applied = router.apply(decision)
        assert_ok("router applies canonical memory", (applied.get("indexed_memory", {}).get("memory") or {}).get("kind") == "service_governance", applied)

        policy = plan_action(
            {
                "service": "payment-service",
                "hypothesis": {"category": "coupon_timeout"},
                "memory_context": {"hits": [{"kind": "governance_rule", "memory_id": "old_alias", "title": "must degrade first"}]},
            }
        )
        assert_ok("action policy accepts legacy alias through canonical vocabulary", bool(policy.get("memory_policy", {}).get("memory_ids")), policy)

        rag = get_rag_index()
        ingest = rag.ingest_text(
            title="payment service runbook",
            body="payment-service must check database connection pool saturation before rollback. Cite owner DBA-oncall.",
            source="kb://payment-runbook",
            service="payment-service",
            tags=["payment-service", "db"],
        )
        assert_ok("rag ingest", ingest.get("status") == "ok" and ingest.get("chunk_count", 0) >= 1, ingest)
        search = rag.search("database connection pool rollback", service="payment-service")
        assert_ok("rag search citations", bool(search.get("hits") and search["hits"][0].get("citation")), search)
        context = rag.context("connection pool", service="payment-service")
        assert_ok("rag fenced context", "<rag-context>" in context.get("rendered", ""), context.get("rendered"))

        topology = parse_topology("payment-service -> coupon-service -> redis", service="payment-service")
        assert_ok("topology parser", topology.get("edge_count", 0) >= 2, topology)
        visual = svc.multimodal_analyze(
            service="payment-service",
            summary="Grafana screenshot shows p95 latency and 503 spike",
            visual_refs=[{"kind": "grafana_screenshot", "text_hint": "HTTP 503 spike, p95 latency 2s, v2.3.1 deploy"}],
            include_dashboard_snapshot=True,
        )
        assert_ok("multimodal evidence", visual.get("evidence_count", 0) >= 2, visual)

        incident = svc.create_incident(
            "payment-service HTTP 503 spike after v2.3.1 release",
            service="payment-service",
            severity="p1",
            environment="prod",
            source="hardening-validate",
            alert_name="payment_503_spike",
            visual_refs=[{"kind": "log_screenshot", "text_hint": "connection pool exhausted HTTP 503 mysql-payment"}],
        )
        assert_ok("incident has rag context", "rag_context" in incident, incident)
        assert_ok("incident has multimodal evidence", any(str(e.get("source", "")).startswith("multimodal") for e in incident.get("evidence", [])), incident.get("evidence"))

        result = run_eval(persist=False)
        assert_ok("benchmark pass rate", result.get("metrics", {}).get("pass_rate") == 1.0, result)

        client = TestClient(app)
        health = client.get("/health")
        assert_ok("health public", health.status_code == 200, health.text)
        blocked = client.post("/memory", json={"kind": "manual_note", "title": "x", "body": "y"})
        assert_ok("write blocked without token", blocked.status_code == 401, blocked.text)
        read_ok = client.get("/runtime/status", headers={"x-runbook-token": "test-read-token"})
        assert_ok("read token allows GET", read_ok.status_code == 200, read_ok.text)
        write_ok = client.post("/rag/ingest-text", headers={"x-runbook-token": "test-write-token"}, json={"title": "api doc", "body": "coupon-service timeout runbook", "service": "coupon-service"})
        assert_ok("write token allows POST", write_ok.status_code == 200 and write_ok.json().get("status") == "ok", write_ok.text)

    print("[OK] RunbookHermes hardening/RAG/eval/multimodal validation completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
