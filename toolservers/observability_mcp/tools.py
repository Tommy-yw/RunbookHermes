from runbook_hermes import tools

TOOL_HANDLERS = {
    "prom_query": tools.prom_query,
    "prom_top_anomalies": tools.prom_top_anomalies,
    "loki_query": tools.loki_query,
    "trace_search": tools.trace_search,
    "recent_deploys": tools.recent_deploys,
    "rollback_canary": tools.rollback_canary,
    "verify_recovery": tools.verify_recovery,
}
