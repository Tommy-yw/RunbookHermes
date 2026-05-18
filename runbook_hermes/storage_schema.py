from __future__ import annotations

import time
from typing import Any, Dict, Mapping

# Bucket names that deserve first-class, queryable storage columns.  The JSON
# payload remains the source of truth so the rest of RunbookHermes can evolve
# without hard migrations, while these columns make the durable backends usable
# for concurrent APIs, audit queries and future analytics.
SCHEMA_VERSION = 1

BUCKET_KEY_FIELDS: Mapping[str, str] = {
    "incidents": "incident_id",
    "evidence": "evidence_id",
    "hypotheses": "hypothesis_id",
    "actions": "action_id",
    "approvals": "approval_id",
    "checkpoints": "checkpoint_id",
    "skills": "skill_id",
    "eval_runs": "run_id",
    "eval_postmortems": "postmortem_id",
    "training_runs": "run_id",
}

SCHEMA_BUCKETS = {
    "incidents",
    "evidence",
    "hypotheses",
    "actions",
    "approvals",
    "checkpoints",
    "skills",
    "events",
}


def bucket_key_field(bucket: str) -> str:
    return BUCKET_KEY_FIELDS.get(bucket, "id")


def canonical_record(bucket: str, key: str, value: Dict[str, Any]) -> Dict[str, Any]:
    item = dict(value or {})
    field = bucket_key_field(bucket)
    if field != "id" and key and not item.get(field):
        item[field] = key
    if bucket in SCHEMA_BUCKETS:
        item.setdefault("schema_version", SCHEMA_VERSION)
    now = time.time()
    if bucket in {"incidents", "approvals", "checkpoints", "skills"}:
        item.setdefault("created_at", now)
    if bucket in {"incidents"}:
        item.setdefault("updated_at", item.get("created_at", now))
    if bucket == "evidence":
        item.setdefault("source", "unknown")
        item.setdefault("confidence", 0.5)
    if bucket == "actions":
        item.setdefault("requires_approval", bool(item.get("risk_level") not in {"read_only", "none"}))
        item.setdefault("checkpoint_before_execution", bool(item.get("requires_approval")))
    if bucket == "approvals":
        item.setdefault("status", "pending")
    return item


SQLITE_DDL = {
    "incidents": """
        CREATE TABLE IF NOT EXISTS incidents (
            incident_id TEXT PRIMARY KEY,
            service TEXT,
            severity TEXT,
            environment TEXT,
            status TEXT,
            created_at REAL,
            updated_at REAL,
            payload TEXT NOT NULL
        )
    """,
    "evidence": """
        CREATE TABLE IF NOT EXISTS evidence (
            evidence_id TEXT PRIMARY KEY,
            incident_id TEXT,
            service TEXT,
            source TEXT,
            confidence REAL,
            created_at REAL,
            payload TEXT NOT NULL
        )
    """,
    "hypotheses": """
        CREATE TABLE IF NOT EXISTS hypotheses (
            hypothesis_id TEXT PRIMARY KEY,
            incident_id TEXT,
            category TEXT,
            confidence REAL,
            created_at REAL,
            payload TEXT NOT NULL
        )
    """,
    "actions": """
        CREATE TABLE IF NOT EXISTS actions (
            action_id TEXT PRIMARY KEY,
            incident_id TEXT,
            action_type TEXT,
            risk_level TEXT,
            requires_approval INTEGER,
            created_at REAL,
            payload TEXT NOT NULL
        )
    """,
    "approvals": """
        CREATE TABLE IF NOT EXISTS approvals (
            approval_id TEXT PRIMARY KEY,
            incident_id TEXT,
            service TEXT,
            action TEXT,
            status TEXT,
            checkpoint_id TEXT,
            created_at REAL,
            decided_at REAL,
            payload TEXT NOT NULL
        )
    """,
    "checkpoints": """
        CREATE TABLE IF NOT EXISTS checkpoints (
            checkpoint_id TEXT PRIMARY KEY,
            incident_id TEXT,
            service TEXT,
            action TEXT,
            created_at REAL,
            payload TEXT NOT NULL
        )
    """,
    "skills": """
        CREATE TABLE IF NOT EXISTS skills (
            skill_id TEXT PRIMARY KEY,
            incident_id TEXT,
            service TEXT,
            title TEXT,
            created_at REAL,
            payload TEXT NOT NULL
        )
    """,
    "events": """
        CREATE TABLE IF NOT EXISTS events (
            event_id TEXT PRIMARY KEY,
            incident_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            ts REAL NOT NULL,
            payload TEXT NOT NULL
        )
    """,
    "kv": """
        CREATE TABLE IF NOT EXISTS kv_store (
            bucket TEXT NOT NULL,
            key TEXT NOT NULL,
            payload TEXT NOT NULL,
            updated_at REAL NOT NULL,
            PRIMARY KEY (bucket, key)
        )
    """,
}

SQLITE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_evidence_incident ON evidence(incident_id)",
    "CREATE INDEX IF NOT EXISTS idx_hypotheses_incident ON hypotheses(incident_id)",
    "CREATE INDEX IF NOT EXISTS idx_actions_incident ON actions(incident_id)",
    "CREATE INDEX IF NOT EXISTS idx_approvals_incident ON approvals(incident_id)",
    "CREATE INDEX IF NOT EXISTS idx_events_incident_ts ON events(incident_id, ts)",
    "CREATE INDEX IF NOT EXISTS idx_incidents_created ON incidents(created_at)",
]


POSTGRES_DDL = {
    "incidents": """
        CREATE TABLE IF NOT EXISTS runbook_incidents (
            incident_id TEXT PRIMARY KEY,
            service TEXT,
            severity TEXT,
            environment TEXT,
            status TEXT,
            created_at DOUBLE PRECISION,
            updated_at DOUBLE PRECISION,
            payload JSONB NOT NULL
        )
    """,
    "evidence": """
        CREATE TABLE IF NOT EXISTS runbook_evidence (
            evidence_id TEXT PRIMARY KEY,
            incident_id TEXT,
            service TEXT,
            source TEXT,
            confidence DOUBLE PRECISION,
            created_at DOUBLE PRECISION,
            payload JSONB NOT NULL
        )
    """,
    "hypotheses": """
        CREATE TABLE IF NOT EXISTS runbook_hypotheses (
            hypothesis_id TEXT PRIMARY KEY,
            incident_id TEXT,
            category TEXT,
            confidence DOUBLE PRECISION,
            created_at DOUBLE PRECISION,
            payload JSONB NOT NULL
        )
    """,
    "actions": """
        CREATE TABLE IF NOT EXISTS runbook_actions (
            action_id TEXT PRIMARY KEY,
            incident_id TEXT,
            action_type TEXT,
            risk_level TEXT,
            requires_approval BOOLEAN,
            created_at DOUBLE PRECISION,
            payload JSONB NOT NULL
        )
    """,
    "approvals": """
        CREATE TABLE IF NOT EXISTS runbook_approvals (
            approval_id TEXT PRIMARY KEY,
            incident_id TEXT,
            service TEXT,
            action TEXT,
            status TEXT,
            checkpoint_id TEXT,
            created_at DOUBLE PRECISION,
            decided_at DOUBLE PRECISION,
            payload JSONB NOT NULL
        )
    """,
    "checkpoints": """
        CREATE TABLE IF NOT EXISTS runbook_checkpoints (
            checkpoint_id TEXT PRIMARY KEY,
            incident_id TEXT,
            service TEXT,
            action TEXT,
            created_at DOUBLE PRECISION,
            payload JSONB NOT NULL
        )
    """,
    "skills": """
        CREATE TABLE IF NOT EXISTS runbook_skills (
            skill_id TEXT PRIMARY KEY,
            incident_id TEXT,
            service TEXT,
            title TEXT,
            created_at DOUBLE PRECISION,
            payload JSONB NOT NULL
        )
    """,
    "events": """
        CREATE TABLE IF NOT EXISTS runbook_events (
            event_id TEXT PRIMARY KEY,
            incident_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            ts DOUBLE PRECISION NOT NULL,
            payload JSONB NOT NULL
        )
    """,
    "kv": """
        CREATE TABLE IF NOT EXISTS runbook_store (
            bucket TEXT NOT NULL,
            key TEXT NOT NULL,
            payload JSONB NOT NULL,
            updated_at DOUBLE PRECISION NOT NULL,
            PRIMARY KEY(bucket, key)
        )
    """,
}

POSTGRES_TABLES = {
    "incidents": ("runbook_incidents", "incident_id"),
    "evidence": ("runbook_evidence", "evidence_id"),
    "hypotheses": ("runbook_hypotheses", "hypothesis_id"),
    "actions": ("runbook_actions", "action_id"),
    "approvals": ("runbook_approvals", "approval_id"),
    "checkpoints": ("runbook_checkpoints", "checkpoint_id"),
    "skills": ("runbook_skills", "skill_id"),
}

POSTGRES_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_runbook_evidence_incident ON runbook_evidence(incident_id)",
    "CREATE INDEX IF NOT EXISTS idx_runbook_hypotheses_incident ON runbook_hypotheses(incident_id)",
    "CREATE INDEX IF NOT EXISTS idx_runbook_actions_incident ON runbook_actions(incident_id)",
    "CREATE INDEX IF NOT EXISTS idx_runbook_approvals_incident ON runbook_approvals(incident_id)",
    "CREATE INDEX IF NOT EXISTS idx_runbook_events_incident_ts ON runbook_events(incident_id, ts)",
    "CREATE INDEX IF NOT EXISTS idx_runbook_incidents_created ON runbook_incidents(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_runbook_store_bucket ON runbook_store(bucket)",
]
