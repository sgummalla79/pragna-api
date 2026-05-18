"""
Per-request user context via Python contextvars + execution-scoped key store.

LangGraph nodes run deep in the async call stack and cannot receive the HTTP
request object. Two mechanisms propagate user keys into nodes:

1. ContextVar (_user_keys) — works for async code and threads created directly
   from the request's asyncio task (intake, interrupt, structured strategies).

2. Execution key store (_execution_store) — a plain thread-safe dict keyed by
   execution_id. Survives all asyncio/thread context boundaries. This is the
   definitive fallback for LangGraph nodes running inside ThreadPoolExecutor
   threads (fanout strategy).

Nodes read keys via get_user_key() which tries the ContextVar first (fast path),
then falls back to the execution store.
"""

import logging
import threading
from contextvars import ContextVar

log = logging.getLogger(__name__)

_user_keys:      ContextVar[dict] = ContextVar("user_keys",      default={})
_anthropic_mode: ContextVar[str]  = ContextVar("anthropic_mode", default="direct")
_active_models:  ContextVar[list] = ContextVar("active_models",  default=[])

# Execution-scoped store: {execution_id: {"keys": {...}, "mode": "...", "active_models": [...]}}
_execution_store:      dict[str, dict] = {}
_execution_store_lock: threading.Lock  = threading.Lock()


def set_user_context(keys: dict, anthropic_mode: str = "direct") -> None:
    _user_keys.set(keys)
    _anthropic_mode.set(anthropic_mode)


def set_active_models(models: list[dict]) -> None:
    """Store the user's active models in the current async context."""
    _active_models.set(models)


def get_active_models() -> list[dict]:
    """Return active models from context, falling back to empty list."""
    return _active_models.get()


def register_execution_keys(execution_id: str, keys: dict, mode: str = "direct", active_models: list[dict] | None = None) -> None:
    """Store decrypted keys (and optionally active models) for an execution so node threads can retrieve them."""
    if not execution_id or not keys:
        return
    with _execution_store_lock:
        _execution_store[execution_id] = {"keys": keys, "mode": mode, "active_models": active_models or []}
    log.debug("register_execution_keys  execution=%s  providers=%s", execution_id, list(keys.keys()))


def unregister_execution_keys(execution_id: str) -> None:
    """Remove execution keys once a stream ends (cleanup)."""
    with _execution_store_lock:
        _execution_store.pop(execution_id, None)


def get_execution_keys(execution_id: str) -> dict:
    with _execution_store_lock:
        return _execution_store.get(execution_id, {}).get("keys", {})


def get_execution_mode(execution_id: str) -> str:
    with _execution_store_lock:
        return _execution_store.get(execution_id, {}).get("mode", "direct")


def get_execution_active_models(execution_id: str) -> list[dict]:
    with _execution_store_lock:
        return _execution_store.get(execution_id, {}).get("active_models", [])


def get_user_key(provider: str) -> str:
    keys  = _user_keys.get()
    value = keys.get(provider) if keys else None
    log.info("get_user_key  provider=%s  found=%s  keys_present=%s",
             provider, bool(value), list(keys.keys()) if keys else [])
    if not value:
        raise RuntimeError(
            f"API key not configured for '{provider}'. "
            "Open Settings → Providers and connect this provider."
        )
    return value


def get_anthropic_mode() -> str:
    return _anthropic_mode.get()


def has_key(provider: str) -> bool:
    return bool(_user_keys.get().get(provider))


def connected_providers() -> set[str]:
    from framework.defaults import available_providers
    return available_providers(_user_keys.get())
