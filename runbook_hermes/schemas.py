from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class EvidenceItem:
    evidence_id: str
    source: str
    service: str
    summary: str
    raw_ref: str
    confidence: float = 0.8
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class Hypothesis:
    hypothesis_id: str
    category: str
    title: str
    confidence: float
    evidence_ids: List[str]
    rationale: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class ActionPlan:
    action_id: str
    action_type: str
    title: str
    risk_level: str
    requires_approval: bool
    checkpoint_before_execution: bool
    dry_run_default: bool
    args: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class IncidentCommand:
    command_id: str
    source: str
    event_type: str
    service: str = "payment-service"
    severity: str = "p1"
    environment: str = "prod"
    alert_name: Optional[str] = None
    summary: str = ""
    starts_at: Optional[str] = None
    generator_url: Optional[str] = None
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    approval_id: Optional[str] = None
    decision: Optional[str] = None
    raw_payload_ref: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
