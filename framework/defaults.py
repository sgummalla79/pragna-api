"""
Smart model selection per agent key.

Each agent maps to a slot via skill.manifest.agent_slot_map.
Each slot has an ordered provider preference and best-model-per-provider mapping.

Priority at execution start:
  1. Snapshot model override (from conversation_skill_agents) → used if provider connected
  2. User's saved model config → used if provider connected
  3. Smart pick from connected providers using slot preference
"""

# Ordered provider preference per slot
_SLOT_PREFERENCE: dict[str, list[str]] = {
    "researcher_search":    ["perplexity", "google", "anthropic", "openai"],
    "researcher_reasoning": ["google",     "anthropic", "openai", "perplexity"],
    "approver":             ["anthropic",  "google",    "openai", "perplexity"],
}
_DEFAULT_PREFERENCE = ["anthropic", "google", "openai", "perplexity"]


def available_providers(user_keys: dict) -> set[str]:
    """Return provider IDs for which the user has a non-empty decrypted key."""
    providers: set[str] = set()
    for key_name, key_value in user_keys.items():
        if not key_value:
            continue
        if key_name.startswith("anthropic"):
            providers.add("anthropic")
        elif key_name.startswith("google"):
            providers.add("google")
        elif key_name.startswith("perplexity"):
            providers.add("perplexity")
        elif key_name.startswith("openai"):
            providers.add("openai")
        elif key_name.startswith("groq"):
            providers.add("groq")
        elif key_name.startswith("mistral"):
            providers.add("mistral")
    return providers


def smart_pick(slot: str, connected: set[str], active_models: list[dict] | None = None) -> dict:
    """
    Pick the best available provider/model for a slot from the user's active models.

    Resolution order:
      1. First connected provider in the slot preference list that has active models
      2. Any other connected provider that has active models

    Raises ValueError if no connected provider has active models.
    """
    if not active_models:
        raise ValueError(
            "No models are activated. "
            "Go to Settings → Providers, open a connected provider, and activate at least one model."
        )

    def _pick_for_provider(provider: str) -> dict | None:
        if provider not in connected:
            return None
        provider_models = [m for m in active_models if m["provider"] == provider]
        if not provider_models:
            return None
        return {"provider": provider, "model": provider_models[0]["model_id"]}

    for provider in _SLOT_PREFERENCE.get(slot, _DEFAULT_PREFERENCE):
        result = _pick_for_provider(provider)
        if result:
            return result

    for provider in connected:
        result = _pick_for_provider(provider)
        if result:
            return result

    raise ValueError(
        "No active models found for any connected provider. "
        "Go to Settings → Providers and activate at least one model."
    )


def smart_pick_for_agent(agent_key: str, slot: str, connected: set[str], active_models: list[dict] | None = None) -> dict:
    """Smart pick for a specific agent using its slot's preference order."""
    return smart_pick(slot, connected, active_models)


def resolve_agent_config(
    agent_slot_map: dict[str, str],    # {agent_key: slot} from skill manifest
    snapshot_cfg:   dict[str, dict],   # {agent_key: {provider, model}} from conversation_skill_agents
    connected:      set[str],
    active_models:  list[dict] | None = None,
) -> dict[str, dict]:
    """
    Resolve the final per-agent config for an execution.

    For each agent:
      - If snapshot has a valid (non-null) provider that is connected → use it
      - Otherwise → smart_pick from connected providers using the agent's slot
    """
    resolved: dict[str, dict] = {}
    for agent_key, slot in agent_slot_map.items():
        snapshot = snapshot_cfg.get(agent_key, {})
        provider = snapshot.get("provider") if snapshot else None
        model    = snapshot.get("model")    if snapshot else None

        if provider and model and provider in connected:
            resolved[agent_key] = {"provider": provider, "model": model}
        else:
            resolved[agent_key] = smart_pick(slot, connected, active_models)

    return resolved
