# Database Model

## Table of Contents
1. [users](#users)
2. [llm_providers](#llm_providers)
3. [llm_models](#llm_models)
4. [user_llm_providers](#user_llm_providers)
5. [user_llm_models](#user_llm_models)
6. [skills](#skills)
7. [skill_agents](#skill_agents)
8. [user_skills](#user_skills)
9. [user_skill_versions](#user_skill_versions)
10. [user_skill_agent_versions](#user_skill_agent_versions)

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
| icon | TEXT | YES | `'⚡'` | |
| version | INTEGER | YES | `1` | OOB version from disk |
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

## user_skills

Records which skills a user has installed.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | UUID | NO | `gen_random_uuid()` | **PK** |
| user_id | TEXT | NO | | **FK** → `users(id)` ON DELETE CASCADE |
| skill_id | UUID | NO | | **FK** → `skills(id)` ON DELETE CASCADE |
| current_version | INTEGER | NO | `0` | `0` = no published version yet |
| created_at | TIMESTAMPTZ | NO | `now()` | Installation timestamp |
| modified_at | TIMESTAMPTZ | NO | `now()` | Auto-updated by trigger on any UPDATE |

**Unique:** `(user_id, skill_id)`

**Indexes:**
- `idx_user_skills_user_id` on `(user_id)`

**Trigger:** `trg_user_skills_modified_at` — updates `modified_at` on every UPDATE.

---

## user_skill_versions

Version history for a user's installed skill. Each edit cycle creates a new draft version; publishing makes it permanent.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | UUID | NO | `gen_random_uuid()` | **PK** |
| user_skill_id | UUID | NO | | **FK** → `user_skills(id)` ON DELETE CASCADE |
| version_number | INTEGER | NO | `1` | Auto-incremented per user_skill |
| status | VARCHAR | NO | `'draft'` | `'draft'` or `'published'` |
| created_at | TIMESTAMPTZ | NO | `now()` | |
| modified_at | TIMESTAMPTZ | NO | `now()` | Auto-updated by trigger on any UPDATE |

**Unique:** `(user_skill_id, version_number)`

**Check:** `status IN ('draft', 'published')`

**Indexes:**
- `idx_user_skill_versions_user_skill_id` on `(user_skill_id)`
- `idx_user_skill_versions_status` on `(user_skill_id, status)`

**Trigger:** `trg_user_skill_versions_modified_at` — updates `modified_at` on every UPDATE.

---

## user_skill_agent_versions

Stores a user's customised agent content within a specific skill version. On each edit, a full snapshot of all agents is created in a new draft version.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | UUID | NO | `gen_random_uuid()` | **PK** |
| user_skill_version_id | UUID | NO | | **FK** → `user_skill_versions(id)` ON DELETE CASCADE |
| skill_agent_id | UUID | NO | | **FK** → `skill_agents(id)` ON DELETE CASCADE |
| content | TEXT | NO | | User's customised system prompt |
| model_id | UUID | YES | | **FK** → `user_llm_models(id)` ON DELETE SET NULL |
| created_at | TIMESTAMPTZ | NO | `now()` | |
| modified_at | TIMESTAMPTZ | NO | `now()` | Auto-updated by trigger on content change |

**Unique:** `(user_skill_version_id, skill_agent_id)`

**Indexes:**
- `idx_user_skill_agent_versions_version_id` on `(user_skill_version_id)`

**Trigger:** `trg_user_skill_agents_v2_modified_at` — updates `modified_at` when `content` changes.

---

## Entity Relationships

```
users
  ├── user_llm_providers ──→ llm_providers
  ├── user_llm_models ──────→ llm_models ──→ llm_providers
  └── user_skills ──────────→ skills
        └── user_skill_versions
              └── user_skill_agent_versions ──→ skill_agents
                                             ──→ user_llm_models

skills
  └── skill_agents

llm_providers
  └── llm_models
```
