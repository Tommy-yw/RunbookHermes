from __future__ import annotations

import time

from runbook_hermes.rag import RunbookRAGIndex, chunk_text, clean_text


def test_rag_clean_chunk_hybrid_rerank_acl_eval(tmp_path):
    idx = RunbookRAGIndex(tmp_path / "rag", chunk_chars=420, chunk_overlap=64)
    cleaned = clean_text("""---\ntitle: x\n---\n<script>bad()</script><h1>Payment Runbook</h1>\nCookie preferences\nRollback payment-service when db_pool errors spike.""")
    assert "script" not in cleaned.lower()
    assert "cookie preferences" not in cleaned.lower()
    assert chunk_text(cleaned, chunk_chars=320)

    public = idx.ingest_text(
        title="Payment 503 DB pool rollback",
        body="""
# Payment 503 DB pool rollback
When payment-service emits HTTP 503 and db_pool_exhausted after a canary release,
collect Prometheus error rate, Loki mysql connection pool logs, traces, and rollback to v2.3.0 after approval.
Use the recovery verifier for error_rate and p95 latency.
""",
        source="docs/payment-runbook.md",
        service="payment-service",
        tags=["payment", "503", "rollback"],
        metadata={"owner": "sre"},
    )
    assert public["status"] == "ok"
    private = idx.ingest_text(
        title="Private payment credentials rotation",
        body="secret queue drain and privileged credential rotation steps for payment-service",
        source="docs/private.md",
        service="payment-service",
        tags=["secret"],
        acl_tags=["sre-prod"],
    )
    assert private["status"] == "ok"
    expired = idx.ingest_text(
        title="Expired payment mitigation",
        body="obsolete payment-service retry workaround should not be retrieved",
        source="docs/expired.md",
        service="payment-service",
        expires_at=time.time() - 60,
    )
    assert expired["status"] == "ok"

    result = idx.search("db_pool payment rollback v2.3.0", service="payment-service", limit=5)
    assert result["status"] == "ok"
    assert result["retrieval"]["mode"] == "hybrid_fts_vector_like_rrf_rerank"
    assert result["hits"], result
    top = result["hits"][0]
    assert top["citation"].endswith("#chunk-1")
    assert "score_breakdown" in top and "vector" in top["score_breakdown"]
    assert "permission_filter_active" in result["diagnostics"]
    assert all("expired" not in h["source"] for h in result["hits"])

    hidden = idx.search("secret queue credential", service="payment-service", limit=5)
    assert all("private" not in h["source"] for h in hidden["hits"])
    visible = idx.search("secret queue credential", service="payment-service", limit=5, permission_scope="sre-prod")
    assert any("private" in h["source"] for h in visible["hits"])
    assert visible["diagnostics"]["permission_filter_active"] is True

    ev = idx.evaluate_queries([
        {
            "query": "how to handle db_pool_exhausted payment 503",
            "service": "payment-service",
            "expected_terms": ["db_pool_exhausted", "rollback"],
        }
    ])
    assert ev["metrics"]["context_recall"] >= 0.5
    assert ev["metrics"]["mrr"] > 0


def test_rag_status_documents_include_enterprise_capabilities(tmp_path):
    idx = RunbookRAGIndex(tmp_path / "rag")
    idx.ingest_text(title="Ops note", body="payment-service 503 runbook with cited evidence", source="ops.md", service="payment-service")
    status = idx.status()
    assert "hybrid_rrf" in status["capabilities"]
    assert status["vector_enabled"] is True
    docs = idx.list_documents()
    assert docs["documents"][0]["content_hash"]
