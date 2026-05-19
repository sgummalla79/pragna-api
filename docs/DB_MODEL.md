# Database Model

## Table of Contents
1. [llm_providers](#llm_providers)
2. [llm_models](#llm_models)
3. [users](#users)
4. [user_config](#user_config)
5. [user_llm_providers](#user_llm_providers)
6. [user_llm_models](#user_llm_models)
7. [skills](#skills)
8. [skill_agents](#skill_agents)
9. [skill_snapshots](#skill_snapshots)
10. [skill_snapshot_agents](#skill_snapshot_agents)
11. [skill_executions](#skill_executions)

---

## llm_providers

Global catalog of supported LLM providers. Seeded at startup; not user-specific.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | UUID | NO | `gen_random_uuid()` | **PK** |
| name | TEXT | NO | | UNIQUE — e.g. `anthropic`, `openai` |
| created_at | TIMESTAMPTZ | NO | `now()` | |
| modified_at | TIMESTAMPTZ | NO | `now()` | Auto-updated by trigger on any UPDATE |

**Trigger:** `trg_llm_providers_modified_at` — updates `modified_at` on every UPDATE.

---

## llm_models

Global catalog of LLM models with pricing. Each model belongs to one provider.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | UUID | NO | `gen_random_uuid()` | **PK** |
| name | TEXT | NO | | UNIQUE — e.g. `claude-sonnet-4-6` |
| llm_provider_id | UUID | NO | | **FK** → `llm_providers(id)` ON DELETE CASCADE |
| input_usd_per_1m_tokens | NUMERIC(12,6) | NO | `0` | Cost per 1M input tokens in USD |
| output_usd_per_1m_tokens | NUMERIC(12,6) | NO | `0` | Cost per 1M output tokens in USD |
| created_at | TIMESTAMPTZ | NO | `now()` | |
| modified_at | TIMESTAMPTZ | NO | `now()` | Auto-updated by trigger on any UPDATE |

**Indexes:**
- `idx_llm_models_provider_id` on `(llm_provider_id)`

**Trigger:** `trg_llm_models_modified_at` — updates `modified_at` on every UPDATE.

---

## users

Stores authenticated users (populated via Auth0 OAuth callback).

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | TEXT | NO | | **PK** — Auth0 `sub` (e.g. `auth0\|abc123`) |
| email | TEXT | NO | | UNIQUE |
| name | TEXT | YES | | Display name from Auth0 |
| picture | TEXT | YES | | Avatar URL |
| created_at | TIMESTAMPTZ | YES | `now()` | |
| last_login | TIMESTAMPTZ | YES | | Updated on each login |
| modified_at | TIMESTAMPTZ | NO | `now()` | Auto-updated by trigger on any UPDATE |

**Trigger:** `trg_users_modified_at` — updates `modified_at` on every UPDATE.

---

## user_config

Stores per-user key/value preferences (e.g. theme settings).

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | UUID | NO | `gen_random_uuid()` | **PK** |
| user_id | TEXT | NO | | **FK** → `users(id)` ON DELETE CASCADE |
| key | TEXT | NO | | Config key, e.g. `theme` |
| value | TEXT | NO | | Config value |
| created_at | TIMESTAMPTZ | NO | `now()` | |
| modified_at | TIMESTAMPTZ | NO | `now()` | Auto-updated by trigger on any UPDATE |

**Unique:** `(user_id, key)`

**Trigger:** `trg_user_config_modified_at` — updates `modified_at` on every UPDATE.

---

## user_llm_providers

Stores a user's API key for each connected provider.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | UUID | NO | `gen_random_uuid()` | **PK** |
| user_id | TEXT | NO | | **FK** → `users(id)` ON DELETE CASCADE |
| llm_provider_id | UUID | NO | | **FK** → `llm_providers(id)` ON DELETE CASCADE |
| encrypted_value | TEXT | NO | | Fernet-encrypted API key |
| created_at | TIMESTAMPTZ | NO | `now()` | |
| modified_at | TIMESTAMPTZ | NO | `now()` | Auto-updated by trigger on key change |

**Unique:** `(user_id, llm_provider_id)`

**Indexes:**
- `idx_user_llm_providers_user_id` on `(user_id)`

**Trigger:** `trg_user_llm_providers_modified_at` — updates `modified_at` when `encrypted_value` changes.

---

## user_llm_models

Tracks which global models a user has activated.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | UUID | NO | `gen_random_uuid()` | **PK** |
| user_id | TEXT | NO | | **FK** → `users(id)` ON DELETE CASCADE |
| llm_model_id | UUID | NO | | **FK** → `llm_models(id)` ON DELETE CASCADE |
| display_name | TEXT | NO | | User-visible name (can be renamed) |
| is_active | BOOLEAN | NO | `FALSE` | Whether user has this model enabled |
| created_at | TIMESTAMPTZ | NO | `now()` | |
| modified_at | TIMESTAMPTZ | NO | `now()` | Auto-updated by trigger |

**Unique:** `(user_id, llm_model_id)`

**Indexes:**
- `idx_user_llm_models_user_id` on `(user_id)`
- `idx_user_llm_models_active` on `(user_id, is_active)`

**Trigger:** `trg_user_llm_models_modified_at` — updates `modified_at` when `is_active` or `display_name` changes.

---

## skills

Out-of-the-box skill definitions (e.g. `architect`). Seeded from disk at startup.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | UUID | NO | `gen_random_uuid()` | **PK** |
| name | TEXT | NO | | UNIQUE — machine identifier, e.g. `architect` |
| display_name | TEXT | NO | | Human-readable name |
| description | TEXT | YES | | |
| created_at | TIMESTAMPTZ | YES | `now()` | |
| modified_at | TIMESTAMPTZ | NO | `now()` | Auto-updated by trigger on any UPDATE |

**Trigger:** `trg_skills_modified_at` — updates `modified_at` on every UPDATE.

---

## skill_agents

Out-of-the-box agent definitions for each skill. Seeded from disk at startup.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | UUID | NO | `gen_random_uuid()` | **PK** |
| skill_id | UUID | NO | | **FK** → `skills(id)` ON DELETE CASCADE |
| name | TEXT | NO | | Machine key, e.g. `intake`, `discovery` |
| display_name | TEXT | YES | | Human label |
| content | TEXT | NO | | Default OOB system prompt |
| created_at | TIMESTAMPTZ | YES | `now()` | |
| modified_at | TIMESTAMPTZ | NO | `now()` | Auto-updated by trigger on content change |

**Unique:** `(skill_id, name)`

**Trigger:** `trg_skill_agents_modified_at` — updates `modified_at` when `content` changes.

---

## skill_snapshots

A user's point-in-time copy of a skill's agent prompts. Replaces `user_skills`, `user_skill_versions`, `conversation_skills`, and `conversation_skill_agents`.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | UUID | NO | `gen_random_uuid()` | **PK** |
| user_id | TEXT | NO | | **FK** → `users(id)` ON DELETE CASCADE |
| skill_id | UUID | NO | | **FK** → `skills(id)` ON DELETE CASCADE |
| version_number | INT | NO | `1` | Auto-incremented across all types per user+skill |
| type | VARCHAR | NO | | `'draft'` \| `'published'` \| `'execution'` |
| conversation_id | UUID | YES | | **FK** → `conversations(id)` ON DELETE SET NULL — set only for execution snapshots |
| created_at | TIMESTAMPTZ | NO | `now()` | |
| modified_at | TIMESTAMPTZ | NO | `now()` | Auto-updated by trigger on any UPDATE |

**Unique:** `(user_id, skill_id, version_number)`

**Check:** `type IN ('draft','published','execution')`

**Indexes:**
- `idx_skill_snapshots_user_skill` on `(user_id, skill_id)`
- `idx_skill_snapshots_type` on `(user_id, skill_id, type)`
- `idx_skill_snapshots_published` on `(user_id, skill_id, type, version_number DESC)`
- `idx_skill_snapshots_conversation` on `(conversation_id)`

**Trigger:** `trg_skill_snapshots_modified_at` — updates `modified_at` on every UPDATE.

**Business rules:**
- `type='draft'` — at most 1 per (user_id, skill_id); deleted when user discards or publishes
- `type='published'` — accumulates; current = MAX(version_number) WHERE type='published'
- `type='execution'` — exactly 1 per (conversation_id, skill_id); **never deleted**

---

## skill_snapshot_agents

Agent content per snapshot. Content is frozen at snapshot time for execution snapshots; only `model_id` can be updated after creation.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | UUID | NO | `gen_random_uuid()` | **PK** |
| snapshot_id | UUID | NO | | **FK** → `skill_snapshots(id)` ON DELETE CASCADE |
| skill_agent_id | UUID | NO | | **FK** → `skill_agents(id)` ON DELETE CASCADE |
| content | TEXT | NO | | Frozen system prompt at snapshot time |
| model_id | UUID | YES | | **FK** → `user_llm_models(id)` ON DELETE SET NULL — updatable for provider fallback |
| created_at | TIMESTAMPTZ | NO | `now()` | |
| modified_at | TIMESTAMPTZ | NO | `now()` | Auto-updated by trigger on content change |

**Unique:** `(snapshot_id, skill_agent_id)`

**Indexes:**
- `idx_skill_snapshot_agents` on `(snapshot_id)`

**Trigger:** `trg_skill_snapshot_agents_modified_at` — updates `modified_at` when `content` changes.

---

## skill_executions

Execution run lifecycle. The `id` doubles as the LangGraph `thread_id`.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | UUID | NO | | **PK** — also the LangGraph thread_id |
| snapshot_id | UUID | NO | | **FK** → `skill_snapshots(id)` ON DELETE CASCADE — must be an execution snapshot |
| status | TEXT | NO | | `'running'` \| `'complete'` \| `'halted'` \| `'error'` \| `'invalid_input'` |
| started_at | TIMESTAMPTZ | NO | `now()` | |
| completed_at | TIMESTAMPTZ | YES | | Set when status transitions out of 'running' |

**Indexes:**
- `idx_skill_executions_snapshot` on `(snapshot_id)`
- `idx_skill_executions_status` on `(snapshot_id, status)`

---

## Entity Relationships

```
llm_providers
  └── llm_models

users
  ├── user_config
  ├── user_llm_providers ──→ llm_providers
  └── user_llm_models ──────→ llm_models

skills
  └── skill_agents

conversations ──→ users

skill_snapshots ──→ users
                ──→ skills
                ──→ conversations (execution type only)
  └── skill_snapshot_agents ──→ skill_agents
                             ──→ user_llm_models
        └── skill_executions
```
