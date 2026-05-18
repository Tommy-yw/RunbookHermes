# RunbookHermes Hermes Memory Bridge

This patch turns RunbookHermes domain memory into a Hermes-native memory and skill extension.

## Why this bridge exists

RunbookHermes started as a vertical overlay on top of Hermes Agent. Hermes already has a general memory plane for user preferences, session recall, MemoryProvider plugins and Skills. The first RunbookHermes memory evolution patch added a dedicated AIOps domain memory store, but that store could become a sidecar if Hermes native chat, Feishu gateway, API and generated Skills did not share the same lifecycle.

The bridge keeps the domain store physically isolated while connecting it logically to Hermes official mechanisms:

```text
Hermes MemoryManager
  -> memory.provider: runbook_hermes
      -> RunbookHermes MemoryProvider bridge
          -> Memory Router
          -> RunbookHermes domain notebooks + SQLite FTS5 + HRR
          -> Skill Publisher
              -> HERMES_HOME/skills/runbooks/runbookhermes/**/SKILL.md
```

## Components

### `plugins/memory/runbook_hermes`

A bundled Hermes MemoryProvider plugin. Enable it in the profile:

```yaml
memory:
  provider: runbook_hermes
```

The provider implements the official Hermes lifecycle:

- `initialize()` initializes RunbookHermes domain memory inside the Hermes session.
- `system_prompt_block()` contributes safety and usage guidance.
- `prefetch()` recalls relevant service/fault/governance/team memory before the model responds.
- `sync_turn()` routes domain-specific chat messages into RunbookHermes memory.
- `on_memory_write()` mirrors relevant Hermes built-in memory writes into domain memory.
- `get_tool_schemas()` exposes RunbookHermes memory and skill tools through the MemoryProvider tool surface.

The older `incident_memory` provider remains as a compatibility alias.

### `runbook_hermes.memory_router.RunbookMemoryRouter`

The router decides which memory plane owns a message:

| Message type | Route |
| --- | --- |
| `payment-service P1 503 告警，帮我排障` | RunbookHermes incident workflow |
| `记住 coupon-service 高峰期必须先降级...` | RunbookHermes domain memory |
| `查一下 coupon-service 以前 504 怎么处理` | RunbookHermes recall |
| `我喜欢中文回答` | Hermes native user/session memory |
| `保存成 runbook skill` | Hermes official Skills publisher |

The router is intentionally conservative. Generic user preferences stay in Hermes native memory. Production incident knowledge goes into RunbookHermes' namespaced domain store after safety scanning.

### `runbook_hermes.skill_publisher.RunbookSkillPublisher`

Publishes generated RunbookHermes runbooks into Hermes official Skills:

```text
$HERMES_HOME/skills/runbooks/runbookhermes/<slug>/SKILL.md
```

Published skills include YAML frontmatter, provenance metadata, service/incident IDs and safety boundaries. They are discoverable by Hermes `skills_list` and loadable with `skill_view`.

### Feishu routing

Feishu messages now go through the Memory Router before falling back to incident creation:

```text
Feishu event
  -> normalize_event()
  -> route_memory_message()
      -> create_incident / write_memory / recall / publish_skill / session_only
```

This prevents ordinary Feishu chat such as “记住这个治理规则” or “查一下历史处理方式” from being treated as a new incident every time.

## New API

```text
GET  /memory/bridge/status
POST /memory/route
GET  /skills/publisher/status
POST /skills/publish
```

Existing memory endpoints continue to work:

```text
GET  /memory/status
GET  /memory/search
POST /memory
GET  /memory/notebooks
POST /memory/reindex-skills
GET  /memory/evolution/digest
POST /memory/{memory_id}/feedback
```

## New tools

```text
runbook_memory_route
runbook_publish_skill
runbook_skill_publish_status
```

The bridge also exposes the previous memory tools through the MemoryProvider interface:

```text
runbook_memory_recall
runbook_memory_write
runbook_memory_feedback
runbook_memory_status
runbook_evolution_digest
runbook_memory_reindex_skills
```

## Safety model

The bridge does not collapse all memory into one flat store. It uses unified Hermes lifecycle with domain isolation:

- Generic user preferences remain in Hermes native USER/session memory.
- Service facts, fault patterns, governance rules, team habits and incident summaries stay in RunbookHermes memory.
- Generated runbooks are published as official Hermes Skills, under a RunbookHermes namespace.
- Raw logs, full traces, secrets, credentials and prompt-injection text are rejected by safety scanning.
- Recalled memory is weak prior/context only; fresh evidence remains authoritative.
- Memory can tighten action policy but cannot bypass approval, checkpoint or recovery verification.

## Validation

Run:

```bash
PYTHONPATH=. python scripts/runbook_hermes_bridge_validate.py
PYTHONPATH=. python scripts/runbook_memory_validate.py
PYTHONPATH=. python scripts/runbook_validate.py
PYTHONPATH=. python scripts/runbook_web_api_smoke.py
PYTHONPATH=. python scripts/runbook_stage8_validate.py
PYTHONPATH=. python scripts/runbook_no_legacy_imports.py
PYTHONPATH=. python scripts/runbook_monitoring_validate.py
```
