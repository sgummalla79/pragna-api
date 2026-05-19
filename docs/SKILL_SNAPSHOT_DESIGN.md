# Skill Snapshot Design

## Concepts

**OOB Skill** — a skill definition shipped with the platform (`skills` + `skill_agents`).
Contains default agent prompts. Read-only from user perspective.

**Skill Snapshot** — a user's point-in-time copy of a skill's agent prompts.
Stored in `skill_snapshots` + `skill_snapshot_agents`. Three types:

| Type | Description | Deletable? |
|---|---|---|
| `draft` | Work in progress, not yet published | Yes |
| `published` | A named version the user has saved | Yes (via uninstall only) |
| `execution` | Frozen copy locked to a conversation | No — permanent audit record |

---

## Tables

### `skill_snapshots`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | TEXT FK → users | |
| skill_id | UUID FK → skills | |
| version_number | INT | Auto-incremented across all types per user+skill |
| type | VARCHAR | CHECK IN ('draft','published','execution') |
| conversation_id | UUID FK → conversations nullable | Set only for execution snapshots |
| created_at | TIMESTAMPTZ | |
| modified_at | TIMESTAMPTZ | Auto-updated by trigger |

UNIQUE (user_id, skill_id, version_number)

### `skill_snapshot_agents`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| snapshot_id | UUID FK → skill_snapshots CASCADE | |
| skill_agent_id | UUID FK → skill_agents CASCADE | |
| content | TEXT | Frozen at snapshot time for execution type |
| model_id | UUID FK → user_llm_models nullable | Can be updated mid-run for fallback |
| created_at | TIMESTAMPTZ | |
| modified_at | TIMESTAMPTZ | Auto-updated by trigger on content change |

UNIQUE (snapshot_id, skill_agent_id)

### `skill_executions`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | Also the LangGraph thread_id |
| snapshot_id | UUID FK → skill_snapshots CASCADE | Always an execution snapshot |
| status | TEXT | CHECK IN ('running','complete','halted','error','invalid_input') |
| started_at | TIMESTAMPTZ | |
| completed_at | TIMESTAMPTZ nullable | |

---

## Business Rules

### Install
A user "has" a skill the moment they create any snapshot. No explicit install step.
- Check: `SELECT 1 FROM skill_snapshots WHERE user_id=X AND skill_id=Y LIMIT 1`

### Uninstall
Delete all `draft` and `published` snapshots for that user+skill.
`execution` snapshots are **never deleted** — they are the permanent audit record.
```sql
DELETE FROM skill_snapshots
WHERE user_id=X AND skill_id=Y AND type IN ('draft','published')
```

### Draft creation
At most ONE draft per user+skill at any time (enforced at application level).

When user edits an agent:
1. If no draft exists, create one by copying agents from the current published version (or from OOB `skill_agents` if no published version exists yet).
2. Apply the edit to that agent's row in `skill_snapshot_agents`.
3. `version_number = MAX(version_number) + 1` across ALL types for that user+skill.

### Publishing
```sql
UPDATE skill_snapshots SET type='published' WHERE id=<draft_id>
```
Single write. Publishing is **one-way**: once published, a version cannot be reverted to draft.
**Current version** = highest `version_number` WHERE `type='published'`.
Old published versions are kept as history (read-only, no rollback).

### Discard draft
```sql
DELETE FROM skill_snapshots WHERE user_id=X AND skill_id=Y AND type='draft'
```
Cascades to `skill_snapshot_agents` automatically.

### Add skill to conversation
Creates an execution snapshot — a frozen copy of the current published version.

1. Get current published: `WHERE user_id=X AND skill_id=Y AND type='published' ORDER BY version_number DESC LIMIT 1`
2. If none: fall back to OOB `skill_agents` content.
3. `INSERT INTO skill_snapshots (type='execution', conversation_id=<conv_id>)`
4. Copy all agents: `INSERT INTO skill_snapshot_agents` (one row per agent, content frozen).

**Content is immutable after this point.** Only `model_id` can change (provider fallback).

### Execution run
```sql
INSERT INTO skill_executions (id=<uuid>, snapshot_id=<execution_snapshot_id>, status='running')
```
The `id` is also the LangGraph `thread_id` — it anchors the pipeline's checkpoint state.

**Concurrent run guard:**
```sql
SELECT e.id FROM skill_executions e
JOIN skill_snapshots s ON s.id = e.snapshot_id
WHERE s.conversation_id=X AND e.status='running'
```

On completion:
```sql
UPDATE skill_executions SET status='complete|halted|error', completed_at=now()
WHERE id=<execution_id>
```

### Retry
```sql
UPDATE skill_executions SET status='running', completed_at=NULL WHERE id=<execution_id>
```
Same snapshot reused — agent content does not change between retries.
`model_id` on `skill_snapshot_agents` can be patched before retry to change the provider/model.

---

## Key Invariants

1. `type='draft'` — at most 1 per (user_id, skill_id)
2. `type='execution'` — exactly 1 per (conversation_id, skill_id) — never deleted
3. Published versions accumulate; the highest `version_number` is "current"
4. `skill_snapshot_agents.content` is immutable for `execution` snapshots
5. `skill_executions.id` == LangGraph `thread_id` — never reuse an id

---

## Snapshot Lifecycle

```
User edits an agent
  → CREATE skill_snapshots (type='draft', version_number=next)
  → CREATE skill_snapshot_agents (copy from latest published + edit applied)

User publishes draft
  → UPDATE skill_snapshots SET type='published' WHERE id=draft_id
  → Current = MAX(version_number) WHERE type='published' (single write, no second row)

User adds skill to conversation
  → CREATE skill_snapshots (type='execution', conversation_id=X)
     content copied from: WHERE user+skill AND type='published' ORDER BY version_number DESC LIMIT 1
  → CREATE skill_snapshot_agents (frozen — content immutable from this point)

Execution runs
  → CREATE skill_executions (snapshot_id=execution_snapshot.id, status='running')
  → _stream_graph() runs using skill_snapshot_agents.content
  → model_id on skill_snapshot_agents can be updated mid-run (provider fallback)
  → UPDATE skill_executions SET status='complete|halted|error', completed_at=now()

User retries
  → UPDATE skill_executions SET status='running', completed_at=NULL
  → Same snapshot_id reused

User uninstalls skill
  → DELETE skill_snapshots WHERE type IN ('draft','published') AND user_id=X AND skill_id=Y
  → Execution snapshots (type='execution') + their executions remain (audit trail)
```

---

## Repository Layer

| Repository | Responsibility |
|---|---|
| `SkillSnapshotRepository` | CRUD for `skill_snapshots` + `skill_snapshot_agents` |
| `SkillExecutionRepository` | CRUD for `skill_executions`; concurrent run guard |

Key methods on `SkillSnapshotRepository`:
- `is_installed(user_id, skill_id)` — check if user has any snapshot
- `get_draft / get_current_published / list_published` — read snapshots
- `create_draft / upsert_draft_agent / publish_draft / discard_draft` — draft lifecycle
- `create_execution_snapshot` — freeze a copy for a conversation
- `list_for_conversation(conversation_id)` — all execution snapshots for a conversation
- `update_agent_model(snapshot_id, skill_agent_id, model_id)` — model fallback update
- `uninstall(user_id, skill_id)` — remove draft+published only

Key methods on `SkillExecutionRepository`:
- `create(execution_id, snapshot_id)` — start a run
- `get_running(conversation_id)` — concurrent run guard
- `complete(execution_id, status)` — finish a run
- `reset_running(execution_id)` — reset for retry
- `get_latest_for_conversation(conversation_id)` — most recent execution status
