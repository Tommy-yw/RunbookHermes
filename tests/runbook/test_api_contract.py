from __future__ import annotations

from fastapi.testclient import TestClient


def _client():
    from apps.runbook_api.app.main import app

    return TestClient(app)


def test_api_auth_contract_and_rag_endpoints(isolated_runbook_env, monkeypatch):
    c = _client()
    assert c.get("/health").status_code == 200

    monkeypatch.setenv("RUNBOOK_API_TOKEN", "")
    assert c.get("/runtime/status").status_code == 503

    monkeypatch.setenv("RUNBOOK_API_TOKEN", "test-token")
    headers = {"x-runbook-token": "test-token"}
    assert c.get("/runtime/status", headers=headers).status_code == 200

    ingest = c.post(
        "/rag/ingest-text",
        headers=headers,
        json={
            "title": "Payment RAG Contract",
            "body": "payment-service db_pool_exhausted requires evidence, approval, rollback, and recovery verification",
            "source": "contract.md",
            "service": "payment-service",
            "tags": ["payment", "503"],
            "acl_tags": ["sre-prod"],
        },
    )
    assert ingest.status_code == 200
    assert ingest.json()["status"] == "ok"

    hidden = c.get("/rag/search", headers=headers, params={"query": "db_pool_exhausted", "service": "payment-service"}).json()
    assert hidden["status"] == "ok"
    assert not hidden["hits"]
    visible = c.get(
        "/rag/search",
        headers=headers,
        params={"query": "db_pool_exhausted", "service": "payment-service", "permission_scope": "sre-prod"},
    ).json()
    assert visible["hits"]
    assert visible["retrieval"]["mode"].startswith("hybrid")

    ev = c.post(
        "/rag/evaluate",
        headers=headers,
        json={"queries": [{"query": "db_pool_exhausted rollback", "service": "payment-service", "permission_scope": "sre-prod", "expected_terms": ["rollback"]}]},
    )
    assert ev.status_code == 200
    assert ev.json()["metrics"]["mrr"] > 0


def test_training_contract_external_launch_isolated(isolated_runbook_env):
    c = _client()
    headers = {"x-runbook-token": "test-token"}
    resp = c.post("/training/pipeline/run", headers=headers, json={"include_incidents": False, "include_benchmark_cases": True, "dry_run": False})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["external_launch_isolated"] is True
    launch = c.post("/training/external-launch", headers=headers, json={"run_id": data["run_id"], "confirmation_token": "wrong"})
    assert launch.status_code == 200
    assert launch.json()["status"] == "rejected"
