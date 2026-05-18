# RunbookHermes 自进化记忆补丁说明

这个补丁把 RunbookHermes 从“固定 runbook demo”升级为“越用越懂系统、故障模式、服务治理规则和团队排障习惯”的自进化 Agent。设计目标是复刻 Hermes Agent 记忆架构的核心思想，但落到 AIOps / 支付系统线上故障处理场景。

## 六层记忆架构

### 1. Prompt notebooks：稳定提示词记忆

位置：`RUNBOOK_MEMORY_DIR/notebooks/`

默认创建：

- `MEMORY.md`：全局稳定事实和安全原则。
- `USER.md`：团队画像、沟通风格和排障偏好。
- `SERVICE_PROFILE.md`：服务画像、依赖关系和治理规则。
- `FAULT_PATTERNS.md`：反复出现的故障模式。
- `TEAM_RUNBOOK_HABITS.md`：从审批、拒绝、复盘中学到的团队习惯。

写入经过安全扫描，并使用文件锁 + `os.replace()` 原子替换，避免并发写破坏文件。

### 2. SQLite FTS5 历史档案

位置：`RUNBOOK_MEMORY_DIR/runbook_memory.sqlite3`

表：

- `memories`：稳定记忆、事故摘要、故障模式、团队偏好、技能索引。
- `memories_fts`：FTS5 全文索引。
- `memory_vectors`：HRR 本地向量 BLOB。
- `memory_feedback`：人工反馈和信任分演化。

每次 incident 创建和审批决策后，RunbookHermes 会自动沉淀：

- `incident_summary`
- `fault_pattern`
- `team_preference`

### 3. Skills 程序性记忆

接口：

- API：`POST /memory/reindex-skills`
- Tool：`runbook_memory_reindex_skills`

它会扫描：

- `skills/**/SKILL.md`
- `.runbook_hermes_store/skills.json` 中生成的 runbook skill

并把技能名称、路径和摘要写入记忆索引。Agent 后续先看到轻量 skill index，需要时再加载完整技能。

### 4. HRR 本地语义检索

实现：`runbook_hermes/memory.py`

不依赖 embedding API，不需要网络。每个 token 通过 SHA-256 确定性生成向量，多个 token 聚合为定长 HRR 向量。检索时融合：

- FTS5 文本分数
- HRR 语义分数
- trust score

容量提示：`SNR = sqrt(dim / memory_items)`。当 SNR < 2.0 时，`/memory/status` 和 evolution digest 会提示扩容或清理低信任记忆。

### 5. 可选外部记忆 Provider

配置项：

```env
RUNBOOK_MEMORY_EXTERNAL_PROVIDER=none
RUNBOOK_MEMORY_EXTERNAL_MODE=tools
```

当前补丁先提供配置和安全边界，不默认连外部服务。后续可接：

- Honcho
- mem0
- holographic
- retaindb

外部 Provider 记忆必须使用 `<memory-context>` context fencing，防止模型把历史记忆误当成当前用户指令。

### 6. Trust / Feedback 自进化

接口：

- API：`POST /memory/{memory_id}/feedback`
- Tool：`runbook_memory_feedback`

反馈标签：

- `helpful`：提升 trust score。
- `wrong` / `stale` / `harmful`：降低 trust score。

低信任记忆在检索排序中会逐渐下沉，并在 evolution digest 中提示清理。

## 事故流程如何变化

原流程：

```text
create incident -> collect evidence -> RCA -> action policy -> approval -> execution -> verification -> skill
```

新流程：

```text
create incident
-> recall memory context
-> collect evidence
-> RCA using evidence + weak memory prior
-> action policy using governance memory, without bypassing approval
-> approval/checkpoint/execution
-> verification
-> generate skill
-> learn incident summary/fault pattern/team preference
-> feedback adjusts trust score
```

关键原则：

- 记忆只能作为 weak prior。
- 新鲜 evidence 永远优先。
- 记忆可以收紧安全策略，但不能绕过 approval/checkpoint/dry-run。

## 新增 API

```text
GET  /memory/status
GET  /memory/search?query=...&service=...&limit=8&include_body=false
POST /memory
GET  /memory/notebooks
POST /memory/reindex-skills
GET  /memory/evolution/digest
POST /memory/{memory_id}/feedback
GET  /incidents/{incident_id}/memory-context
```

## 新增 Agent tools

```text
runbook_memory_recall
runbook_memory_write
runbook_memory_feedback
runbook_memory_status
runbook_evolution_digest
runbook_memory_reindex_skills
```

## 新增 Web 页面

```text
/web/memory.html
```

页面能力：

- 查看记忆层状态、FTS5、HRR、SNR。
- 搜索服务记忆。
- 写入稳定记忆。
- 查看 notebooks。
- 查看自进化摘要。
- 索引 Skills。

## 配置

```env
RUNBOOK_MEMORY_ENABLED=true
RUNBOOK_MEMORY_DIR=.runbook_hermes_store/memory
RUNBOOK_MEMORY_CONTEXT_LIMIT=6
RUNBOOK_MEMORY_HRR_DIM=1024
RUNBOOK_MEMORY_EXTERNAL_PROVIDER=none
RUNBOOK_MEMORY_EXTERNAL_MODE=tools
RUNBOOK_MEMORY_CONTEXT_CADENCE=1
RUNBOOK_MEMORY_INJECTION_FREQUENCY=first-turn
```

## 验证

```bash
python -m compileall runbook_hermes apps/runbook_api plugins/runbook-hermes scripts/runbook_memory_validate.py
python scripts/runbook_memory_validate.py
python scripts/runbook_validate.py
python scripts/runbook_web_api_smoke.py
```

## Hermes official integration update

The domain memory layer is now exposed through the Hermes official MemoryProvider and Skills systems. Use `memory.provider: runbook_hermes` in the RunbookHermes profile. The physical RunbookHermes notebooks/SQLite/HRR store remains namespaced for production safety, while the logical lifecycle is managed by Hermes MemoryManager. Generated runbooks are published to Hermes Skills under `runbooks/runbookhermes`. See `docs/runbook_hermes_memory_bridge.md`.
