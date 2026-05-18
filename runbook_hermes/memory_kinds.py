from __future__ import annotations

from typing import Final

# Canonical RunbookHermes memory vocabulary. Keep this list small and stable:
# these values are consumed by router, RCA priors, action policy and UI filters.
INCIDENT_SUMMARY: Final[str] = "incident_summary"
FAULT_PATTERN: Final[str] = "fault_pattern"
TEAM_PREFERENCE: Final[str] = "team_preference"
SERVICE_GOVERNANCE: Final[str] = "service_governance"
SERVICE_PROFILE: Final[str] = "service_profile"
SKILL_INDEX: Final[str] = "skill_index"
MANUAL_NOTE: Final[str] = "manual_note"
RAG_DOCUMENT: Final[str] = "rag_document"
VISUAL_OBSERVATION: Final[str] = "visual_observation"
TOPOLOGY_OBSERVATION: Final[str] = "topology_observation"

CANONICAL_MEMORY_KINDS: Final[set[str]] = {
    INCIDENT_SUMMARY,
    FAULT_PATTERN,
    TEAM_PREFERENCE,
    SERVICE_GOVERNANCE,
    SERVICE_PROFILE,
    SKILL_INDEX,
    MANUAL_NOTE,
    RAG_DOCUMENT,
    VISUAL_OBSERVATION,
    TOPOLOGY_OBSERVATION,
}

# Backward-compatible aliases from earlier bridge drafts and chat phrasing.
MEMORY_KIND_ALIASES: Final[dict[str, str]] = {
    "governance_rule": SERVICE_GOVERNANCE,
    "governance": SERVICE_GOVERNANCE,
    "policy": SERVICE_GOVERNANCE,
    "service_policy": SERVICE_GOVERNANCE,
    "service_rule": SERVICE_GOVERNANCE,
    "team_habit": TEAM_PREFERENCE,
    "team_runbook_habit": TEAM_PREFERENCE,
    "team_rule": TEAM_PREFERENCE,
    "user_preference": TEAM_PREFERENCE,
    "runbook_habit": TEAM_PREFERENCE,
    "service_info": SERVICE_PROFILE,
    "service_fact": SERVICE_PROFILE,
    "service_profile_memory": SERVICE_PROFILE,
    "fault": FAULT_PATTERN,
    "fault_mode": FAULT_PATTERN,
    "incident": INCIDENT_SUMMARY,
    "incident_memory": INCIDENT_SUMMARY,
    "skill": SKILL_INDEX,
    "runbook_skill": SKILL_INDEX,
    "document": RAG_DOCUMENT,
    "document_chunk": RAG_DOCUMENT,
    "knowledge_doc": RAG_DOCUMENT,
    "visual": VISUAL_OBSERVATION,
    "image": VISUAL_OBSERVATION,
    "screenshot": VISUAL_OBSERVATION,
    "topology": TOPOLOGY_OBSERVATION,
    "topology_map": TOPOLOGY_OBSERVATION,
    "note": MANUAL_NOTE,
    "manual": MANUAL_NOTE,
}

NOTEBOOK_FOR_KIND: Final[dict[str, str]] = {
    INCIDENT_SUMMARY: "MEMORY.md",
    FAULT_PATTERN: "FAULT_PATTERNS.md",
    TEAM_PREFERENCE: "TEAM_RUNBOOK_HABITS.md",
    SERVICE_GOVERNANCE: "SERVICE_PROFILE.md",
    SERVICE_PROFILE: "SERVICE_PROFILE.md",
    SKILL_INDEX: "MEMORY.md",
    RAG_DOCUMENT: "MEMORY.md",
    VISUAL_OBSERVATION: "MEMORY.md",
    TOPOLOGY_OBSERVATION: "SERVICE_PROFILE.md",
    MANUAL_NOTE: "MEMORY.md",
}

RCA_PRIOR_KINDS: Final[set[str]] = {
    INCIDENT_SUMMARY,
    FAULT_PATTERN,
    TEAM_PREFERENCE,
    SERVICE_GOVERNANCE,
    SERVICE_PROFILE,
    SKILL_INDEX,
    RAG_DOCUMENT,
    VISUAL_OBSERVATION,
    TOPOLOGY_OBSERVATION,
}

ACTION_GUARDRAIL_KINDS: Final[set[str]] = {
    TEAM_PREFERENCE,
    SERVICE_GOVERNANCE,
    SERVICE_PROFILE,
    FAULT_PATTERN,
    SKILL_INDEX,
}


def normalize_memory_kind(kind: str | None, default: str = MANUAL_NOTE) -> str:
    """Return the canonical RunbookHermes memory kind.

    Earlier drafts wrote aliases such as governance_rule/team_habit. Normalizing
    at every boundary lets old records remain searchable while new writes feed
    RCA/action guardrails consistently.
    """
    raw = str(kind or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not raw:
        return default
    if raw in CANONICAL_MEMORY_KINDS:
        return raw
    return MEMORY_KIND_ALIASES.get(raw, default)


def notebook_for_kind(kind: str | None) -> str:
    return NOTEBOOK_FOR_KIND.get(normalize_memory_kind(kind), "MEMORY.md")


def is_rca_prior_kind(kind: str | None) -> bool:
    return normalize_memory_kind(kind) in RCA_PRIOR_KINDS


def is_action_guardrail_kind(kind: str | None) -> bool:
    return normalize_memory_kind(kind) in ACTION_GUARDRAIL_KINDS
