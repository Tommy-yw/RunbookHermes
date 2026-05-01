from __future__ import annotations

from typing import Any, Dict, List


def build_hypothesis(evidence: List[Dict[str, Any]], service: str = "payment-service") -> Dict[str, Any]:
    ids = [e.get("evidence_id") for e in evidence if e.get("evidence_id")]
    text = " ".join(str(e).lower() for e in evidence)
    has_deploy = "deploy" in text and ("v2.3.1" in text or "recent" in text)
    has_503 = "503" in text or "http_503_rate" in text
    has_pool = "connection pool" in text or "mysql-payment" in text or "db_pool" in text
    has_coupon_timeout = "coupon-service" in text and ("504" in text or "timeout" in text)
    has_order_limit = "order-service" in text and ("429" in text or "rate limit" in text)
    if has_deploy and has_503 and has_pool:
        return {
            "hypothesis_id": "hyp_deploy_db_pool_regression",
            "category": "deploy_db_regression",
            "title": "Recent deployment likely introduced a database connection pool regression that returns HTTP 503",
            "confidence": 0.86,
            "evidence_ids": ids,
            "rationale": "Deployment timing, HTTP 503 spike, connection-pool log terms and MySQL trace latency point to a release regression.",
        }
    if has_coupon_timeout:
        return {
            "hypothesis_id": "hyp_coupon_timeout_504",
            "category": "coupon_timeout",
            "title": "coupon-service timeout is likely causing payment-service HTTP 504 responses",
            "confidence": 0.78,
            "evidence_ids": ids,
            "rationale": "Log and trace evidence points to coupon-service latency and payment-service HTTP 504 responses.",
        }
    if has_order_limit:
        return {
            "hypothesis_id": "hyp_order_rate_limit_429",
            "category": "order_rate_limit",
            "title": "order-service rate limiting is likely causing HTTP 429 responses",
            "confidence": 0.74,
            "evidence_ids": ids,
            "rationale": "Metric/log evidence points to order-service rate-limit behavior and HTTP 429 responses.",
        }
    return {
        "hypothesis_id": "hyp_inconclusive",
        "category": "inconclusive",
        "title": "Evidence is insufficient for a confident root cause",
        "confidence": 0.35,
        "evidence_ids": ids,
        "rationale": "The available evidence does not match a known runbook pattern. Continue collecting logs, traces and deploy data.",
    }


def guard_root_cause(args: Dict[str, Any]) -> Dict[str, Any]:
    evidence = args.get("evidence") or []
    service = args.get("service", "payment-service")
    hyp = build_hypothesis(evidence, service=service)
    return {"status": "ok", "service": service, "hypothesis": hyp}
