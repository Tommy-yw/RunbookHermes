from __future__ import annotations

import hashlib
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .config import load_settings
from .memory import safe_scan_text
from .resources import resource_root

ROOT = resource_root()
SLUG_RE = re.compile(r"[^a-z0-9._-]+")


def _slug(value: str, fallback: str = "runbookhermes-skill") -> str:
    value = (value or fallback).lower().strip()
    value = value.replace("_", "-")
    value = SLUG_RE.sub("-", value).strip("-.")
    value = re.sub(r"-+", "-", value)
    return (value or fallback)[:80]


def _yaml_escape(value: str) -> str:
    return str(value or "").replace("\\", "\\\\").replace('"', '\\"')


def _safe_category(category: str) -> Path:
    parts = []
    for part in (category or "runbooks/runbookhermes").split("/"):
        clean = _slug(part, "runbookhermes")
        if clean and clean not in {".", ".."}:
            parts.append(clean)
    return Path(*parts) if parts else Path("runbooks") / "runbookhermes"


@dataclass
class PublishResult:
    status: str
    path: str = ""
    relative_path: str = ""
    skill_name: str = ""
    reason: str = ""
    safety: Dict[str, Any] | None = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "path": self.path,
            "relative_path": self.relative_path,
            "skill_name": self.skill_name,
            "reason": self.reason,
            "safety": self.safety or {},
        }


class RunbookSkillPublisher:
    """Publish generated RunbookHermes runbooks into Hermes official Skills.

    RunbookHermes can keep an incident-local copy in JsonStore, but the durable
    procedural memory should be discoverable through Hermes' `skills_list` /
    `skill_view` tools. This publisher writes SKILL.md under HERMES_HOME/skills
    using a RunbookHermes category namespace.
    """

    def __init__(self, skills_dir: Optional[Path] = None, category: Optional[str] = None) -> None:
        self.settings = load_settings()
        self.category = category or self.settings.runbook_skill_publish_category or "runbooks/runbookhermes"
        self.skills_dir = skills_dir or self._resolve_skills_dir()

    def _resolve_skills_dir(self) -> Path:
        try:
            from tools.skills_tool import SKILLS_DIR

            return Path(SKILLS_DIR)
        except Exception:
            hermes_home = os.getenv("HERMES_HOME")
            if hermes_home:
                return Path(hermes_home) / "skills"
            return ROOT / "skills"

    def status(self) -> Dict[str, Any]:
        return {
            "status": "enabled" if self.settings.runbook_skill_publish_enabled else "disabled",
            "hermes_official_skill_system": True,
            "skills_dir": str(self.skills_dir),
            "category": self.category,
            "category_path": str(self.skills_dir / _safe_category(self.category)),
            "note": "Generated RunbookHermes skills are published as Hermes SKILL.md directories under this namespace.",
        }

    def render_skill_md(self, skill: Dict[str, Any], incident: Optional[Dict[str, Any]] = None) -> str:
        incident = incident or {}
        service = str(skill.get("service") or incident.get("service") or "service")
        title = str(skill.get("title") or f"{service} incident runbook")
        body = str(skill.get("body") or "")
        incident_id = str(skill.get("incident_id") or incident.get("incident_id") or "")
        skill_id = str(skill.get("skill_id") or "")
        root_cause = incident.get("hypothesis") or {}
        action = incident.get("action") or {}
        description = f"RunbookHermes generated runbook for {service} incident triage and recovery."
        frontmatter = (
            "---\n"
            f"name: \"{_yaml_escape(_slug(title, service + '-runbook'))}\"\n"
            f"description: \"{_yaml_escape(description)}\"\n"
            "version: \"1.0.0\"\n"
            "metadata:\n"
            "  runbookhermes:\n"
            f"    service: \"{_yaml_escape(service)}\"\n"
            f"    incident_id: \"{_yaml_escape(incident_id)}\"\n"
            f"    skill_id: \"{_yaml_escape(skill_id)}\"\n"
            f"    generated_at: \"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\"\n"
            "    source: \"RunbookHermes SkillPublisher\"\n"
            "---\n\n"
        )
        provenance = (
            "\n\n## RunbookHermes provenance\n\n"
            f"- Service: `{service}`\n"
            f"- Incident ID: `{incident_id or 'not recorded'}`\n"
            f"- Source skill ID: `{skill_id or 'not recorded'}`\n"
            f"- Root-cause category: `{root_cause.get('category', 'not recorded')}`\n"
            f"- Suggested action: `{action.get('action_type', action.get('title', 'not recorded'))}`\n"
            "\n## Safety boundaries\n\n"
            "- Treat this skill as procedural memory, not fresh evidence.\n"
            "- Re-check metrics, logs, traces and deployment history before RCA.\n"
            "- Production mutation still requires approval, checkpoint and recovery verification.\n"
            "- Do not paste raw logs, traces, credentials or secrets into this skill.\n"
        )
        if body.lstrip().startswith("---"):
            # Avoid nested frontmatter from generated/custom bodies.
            body = re.sub(r"^---[\s\S]*?---\s*", "", body, count=1).strip()
        if not body.strip().startswith("#"):
            body = f"# {title}\n\n{body.strip()}"
        return frontmatter + body.strip() + provenance

    def publish_generated_skill(self, skill: Dict[str, Any], incident: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.settings.runbook_skill_publish_enabled:
            return PublishResult(status="disabled", reason="RUNBOOK_SKILL_PUBLISH_ENABLED=false").to_dict()
        incident = incident or {}
        service = str(skill.get("service") or incident.get("service") or "service")
        title = str(skill.get("title") or f"{service} incident runbook")
        slug = _slug(f"{service}-{title}", fallback=f"{service}-runbook")
        incident_id = str(skill.get("incident_id") or incident.get("incident_id") or "")
        if incident_id:
            suffix = hashlib.sha256(incident_id.encode("utf-8", "ignore")).hexdigest()[:8]
            if suffix not in slug:
                slug = f"{slug[:70].strip('-')}-{suffix}"
        skill_md = self.render_skill_md({**skill, "service": service}, incident=incident)
        scan = safe_scan_text(skill_md)
        if not scan["safe"]:
            return PublishResult(status="rejected", reason="skill_safety_scan_failed", safety=scan).to_dict()
        target_dir = self.skills_dir / _safe_category(self.category) / slug
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / "SKILL.md"
        tmp = target.with_suffix(".md.tmp")
        tmp.write_text(skill_md, encoding="utf-8")
        os.replace(tmp, target)
        try:
            rel = str(target.relative_to(self.skills_dir))
        except Exception:
            rel = str(target)
        result = PublishResult(status="published", path=str(target), relative_path=rel, skill_name=slug, safety=scan).to_dict()
        try:
            from .memory import get_memory_manager

            get_memory_manager().upsert_memory(
                kind="skill_index",
                service=service,
                title=title,
                body=f"Hermes official Skill published: {rel}\nIncident: {incident_id}\nUse skill_view to load full instructions.",
                tags=["skill", "hermes_official", "runbookhermes", service],
                source="skill_publisher",
                incident_id=incident_id,
                memory_id=f"skillpub_{hashlib.sha256(rel.encode('utf-8')).hexdigest()[:16]}",
                trust_score=0.68,
            )
        except Exception as exc:
            result["memory_index_warning"] = str(exc)
        return result


_PUBLISHER: Optional[RunbookSkillPublisher] = None


def get_skill_publisher() -> RunbookSkillPublisher:
    global _PUBLISHER
    if _PUBLISHER is None:
        _PUBLISHER = RunbookSkillPublisher()
    return _PUBLISHER
