# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Development Commands

### Start the API locally
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in required variables
uvicorn api.app:app --reload --port 8000
```

### Health check
```bash
curl http://localhost:8000/health
# → {"status":"ok","graph":"ready"}
```

### Run tests
```bash
pytest tests/unit/ tests/e2e/ -v -s --tb=long -m "not live"
```

### Run database migrations
```bash
python -m alembic upgrade head
```

### Generate SETTINGS_SECRET (required once)
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Syntax check a Python file
```bash
python3 -m py_compile <path/to/file.py>
```

## Environment Setup

Copy `.env.example` to `.env`. Required variables:

| Variable | Purpose |
|---|---|
| `SETTINGS_SECRET` | Fernet key for encrypting user API keys in DB |
| `JWT_SECRET` | Signs session cookies (`openssl rand -hex 32`) |
| `AUTH0_DOMAIN`, `AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET` | Auth0 OAuth |
| `DATABASE_URL` | Empty → SQLite; `postgresql://...` → PostgreSQL |

User LLM API keys (Anthropic, OpenAI, Google, Perplexity, etc.) are **not** in `.env` — they're entered via the Settings UI and stored encrypted in the database using `SETTINGS_SECRET`.

## Architecture Overview

**Pragna API** is a multi-agent AI backend that runs structured pipelines ("skills") to produce Architecture Recommendation Documents. It also supports free-form chat.

The companion frontend lives at: `sgummalla79/sf-research-agent`

### Request Flow

FastAPI → `api/routes/chat.py` → LangGraph `astream_events` → SSE stream to browser.

### Key Files

- `api/app.py` — FastAPI lifespan: loads DB, compiles all skill graphs, registers middleware
- `api/routes/chat.py` — All SSE streaming endpoints; `_stream_graph()` is the central SSE emitter
- `state.py` — `AgentState` (Pydantic + LangGraph reducers) — the single state object flowing through the pipeline
- `framework/defaults.py` — Smart LLM slot selection: `available_providers()`, `smart_pick()`, `resolve_agent_config()`
- `utils/user_context.py` — Per-request user key storage; `set_user_context()` called in auth middleware, `get_user_key()` called in node threads
- `utils/llm_factory.py` — `build_llm(provider, model)` and `get_llm_for_slot(slot, session_config)` — only entry point for constructing LLM clients

### Framework (`framework/`)

- `schema.py` — `SkillManifest` and `StageConfig` parsed from `SKILL.md` files
- `registry.py` — Loads and caches skills from `skills/`
- `engine.py` — Compiles a `SkillManifest` into a LangGraph `StateGraph`
- `strategies/` — Stage execution patterns:
  - `intake.py` — Handles brief/document/image input, emits confirmation interrupt
  - `interrupt.py` — Structured output with `question` interrupt (discovery)
  - `structured.py` — Plain structured output (review, approval)
  - `fanout.py` — Parallel branches (`ThreadPoolExecutor`) + merge writer (research)

### Persistence (`persistence/checkpointer.py`)

Implements both SQLite and PostgreSQL backends behind the same async interface. Stores LangGraph checkpoints AND custom tables (users, sessions, agent_configs, usage). PostgreSQL requires `autocommit=True, prepare_threshold=None` for Neon PgBouncer compatibility.

### Skills (`skills/`)

Each skill is a directory containing:
- `SKILL.md` — Manifest: pipeline stages, execution strategies, llm_slots, routing logic
- `agents/*.md` — System prompts for each agent, versioned in DB as snapshots

### LLM Slot System

Each pipeline stage is assigned an `llm_slot` in `SKILL.md`. Slots: `intake`, `discovery`, `researcher_search`, `researcher_reasoning`, `researcher_writer`, `reviewer`, `approver`.

`resolve_agent_config()` in `framework/defaults.py` resolves slot → `{provider, model}` using priority: snapshot override → user saved config → smart_pick from connected providers.

### SSE Event Types (emitted to frontend)

| Event | Payload |
|---|---|
| `stage_start` | `{stage, label}` |
| `token` | `{content}` |
| `stage_end` | `{stage}` |
| `document_ready` | `{version, session_id}` |
| `review_complete` | `{passed, feedback, critical_issues}` |
| `approval_complete` | `{status, comments, required_changes}` |
| `confirm_understanding` | `{content, session_id}` |
| `question` | `{questions[], session_id}` |
| `done` | `{status, document_version}` |
| `error` | `{message}` |
| `provider_error` | `{message, can_smart_pick}` |

## Deployment

### Docker
```bash
docker build -t pragna-api .
docker run -p 8000:8000 --env-file .env pragna-api
```

### CI/CD
- **Staging**: Auto-deploys on push to `staging` branch → `ghcr.io/sgummalla79/pragna-api:staging`
- **Production**: Manual `workflow_dispatch` in `.github/workflows/build-and-push.yml` → version bump, Docker build, blue-green deploy via `scripts/blue-green-api.sh`

### First-time VPS setup (required once)
The production CI/CD SSHes to the VPS and runs `scripts/blue-green-api.sh` from a checkout of this repo. Clone this repo on the VPS and set the `VPS_API_REPO_PATH` GitHub secret to that path:
```bash
git clone git@github.com:sgummalla79/pragna-api.git /opt/pragna-api
# Then set: VPS_API_REPO_PATH=/opt/pragna-api
```

### GitHub Secrets Required
| Secret | Purpose |
|---|---|
| `VPS_HOST` | VPS IP / hostname |
| `VPS_SSH_KEY` | SSH private key for VPS access |
| `VPS_API_REPO_PATH` | Path to this repo's checkout on the VPS (e.g. `/opt/pragna-api`) |

## Key Invariants

- `session_agent_config` in `AgentState` is **frozen at session start** and patched on retry via `graph.aupdate_state()` — nodes must not write to it
- `session_type` in `agent_sessions` DB table is the **source of truth** for whether a session is a pipeline run or regular chat — do not infer from LangGraph checkpoint state
- `recursion_limit: 100` is set in `_stream_graph()` — the default of 25 is too low for a 5-stage pipeline with revision cycles
- PostgreSQL connections must use `autocommit=True, prepare_threshold=None` — Neon PgBouncer rejects prepared statements
- LangGraph runs synchronous node functions via `run_in_executor` inside tasks created with `asyncio.create_task`. These tasks do NOT inherit the HTTP request's `_user_keys` ContextVar — keys are propagated via `_session_store` in `utils/user_context.py`
