from __future__ import annotations

from typing import Any, Dict


def plan_action(args: Dict[str, Any]) -> Dict[str, Any]:
    hypothesis = args.get("hypothesis") or {}
    service = args.get("service", "payment-service")
    category = hypothesis.get("category")
    if category == "deploy_db_regression":
        return {
            "status": "ok",
            "service": service,
            "actions": [
                {
                    "action_id": "act_rollback_canary",
                    "action_type": "rollback_canary",
                    "title": "Rollback payment-service canary from v2.3.1 to v2.3.0",
                    "risk_level": "destructive",
                    "requires_approval": True,
                    "checkpoint_before_execution": True,
                    "dry_run_default": True,
                    "args": {"service": service, "target_revision": "v2.3.0"},
                },
                {
                    "action_id": "act_observe_http_503",
                    "action_type": "observe",
                    "title": "Observe HTTP 503 rate and p95 latency for 10 minutes after rollback",
                    "risk_level": "read_only",
                    "requires_approval": False,
                    "checkpoint_before_execution": False,
                    "dry_run_default": True,
                    "args": {"service": service, "window": "10m"},
                },
            ],
        }
    if category == "coupon_timeout":
        return {"status": "ok", "service": service, "actions": [{"action_id": "act_scale_coupon", "action_type": "scale_or_disable_coupon_path", "title": "Route around or scale coupon-service before retrying payment requests", "risk_level": "write_safe", "requires_approval": True, "checkpoint_before_execution": True, "dry_run_default": True, "args": {"service": "coupon-service"}}]}
    if category == "order_rate_limit":
        return {"status": "ok", "service": service, "actions": [{"action_id": "act_relax_order_rate_limit", "action_type": "adjust_rate_limit", "title": "Review order-service rate-limit policy and temporarily raise the demo limit", "risk_level": "write_safe", "requires_approval": True, "checkpoint_before_execution": True, "dry_run_default": True, "args": {"service": "order-service"}}]}
    return {"status": "ok", "service": service, "actions": []}
