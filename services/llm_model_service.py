"""
LLMModelService — manage per-user LLM model activations and display names.

Handles seeding models from provider APIs, toggling active state, renaming,
and listing for UI rendering. All persistence is delegated to the repositories.
"""

from __future__ import annotations

import logging
from typing import Optional

from repositories.llm_model_repository import LLMModelRepository, LLMModel
from repositories.llm_provider_repository import LLMProviderRepository
from repositories.user_llm_model_repository import (
    UserLLMModelRepository,
    UserLLMModelResolved,
)

log = logging.getLogger(__name__)

# Maximum length enforced on user-supplied display names
_DISPLAY_NAME_MAX_LEN = 100


class LLMModelService:
    """
    Business logic for per-user model management.

    Coordinates between the global llm_models catalog and per-user
    user_llm_models records to manage which models each user can use.
    """

    def __init__(
        self,
        llm_provider_repo:   LLMProviderRepository,
        llm_model_repo:      LLMModelRepository,
        user_llm_model_repo: UserLLMModelRepository,
    ) -> None:
        """Initialise with injected repository instances."""
        self._providers  = llm_provider_repo
        self._models     = llm_model_repo
        self._user_models = user_llm_model_repo

    async def seed_for_provider(
        self,
        user_id:      str,
        provider_key: str,
        model_names:  list[str],
    ) -> int:
        """
        Ensure user_llm_models rows exist for each model name in the given list.

        Looks up each model name in the global llm_models catalog. Models not in
        the catalog are skipped with a warning. Existing rows are not overwritten —
        active state and display name are preserved on conflict.

        Returns the number of models successfully seeded.

        Args:
            user_id:      The user's Auth0 sub.
            provider_key: Machine name of the provider (e.g. 'openai').
            model_names:  List of model name strings returned by the provider API.
        """
        seeded = 0
        for name in model_names:
            model = await self._models.get_by_name(name)
            if not model:
                log.warning("Seed: model '%s' not in catalog — skipped", name)
                continue
            await self._user_models.upsert(user_id, model.id, name)
            seeded += 1
        return seeded

    async def get_active(self, user_id: str) -> list[UserLLMModelResolved]:
        """
        Return all models the user currently has marked active.

        Includes resolved provider_key and model_name fields for rendering
        in dropdowns and inference selection.

        Args:
            user_id: The user's Auth0 sub.
        """
        return await self._user_models.get_active(user_id)

    async def list_for_provider(
        self, user_id: str, provider_key: str
    ) -> list[UserLLMModelResolved]:
        """
        Return all model rows for a user scoped to a specific provider.

        Used by the per-provider model management UI.

        Args:
            user_id:      The user's Auth0 sub.
            provider_key: Machine name of the provider (e.g. 'openai').
        """
        provider = await self._providers.get_by_name(provider_key)
        if not provider:
            return []
        return await self._user_models.list_for_provider(user_id, provider.id)

    async def toggle(
        self, user_id: str, provider_key: str, model_name: str
    ) -> Optional[bool]:
        """
        Flip the is_active state for a specific model.

        Returns the new active state, or None if the model row is not found.

        Args:
            user_id:      The user's Auth0 sub.
            provider_key: Machine name of the provider (for catalog lookup).
            model_name:   Model identifier, e.g. 'gpt-4o'.
        """
        model = await self._models.get_by_name(model_name)
        if not model:
            return None

        # Read current state, then write the opposite value (two-step by design —
        # the repo has no atomic toggle because toggle is domain logic, not data logic).
        rows = await self._user_models.list_for_provider(
            user_id, model.llm_provider_id
        )
        match = next((r for r in rows if r.llm_model_id == model.id), None)
        if not match:
            return None

        new_state = not match.is_active
        await self._user_models.update_is_active(user_id, model.id, new_state)
        return new_state

    async def rename(
        self, user_id: str, provider_key: str, model_name: str, display_name: str
    ) -> bool:
        """
        Update the display name for a model row.

        Trims whitespace and enforces a maximum length. Returns False if the model
        row is not found for this user.

        Args:
            user_id:       The user's Auth0 sub.
            provider_key:  Machine name of the provider.
            model_name:    Model identifier to rename.
            display_name:  New display name (will be stripped and capped).
        """
        safe_name = display_name.strip()[:_DISPLAY_NAME_MAX_LEN]
        model = await self._models.get_by_name(model_name)
        if not model:
            return False
        await self._user_models.update_display_name(user_id, model.id, safe_name)
        return True

    async def deactivate_all_for_provider(
        self, user_id: str, provider_key: str
    ) -> None:
        """
        Mark all of a user's models for a provider as inactive.

        Called when a provider is toggled off. Does nothing if the provider
        is not found in the catalog.

        Args:
            user_id:      The user's Auth0 sub.
            provider_key: Machine name of the provider.
        """
        provider = await self._providers.get_by_name(provider_key)
        if not provider:
            return
        await self._user_models.update_is_active_for_provider(user_id, provider.id, False)

    async def delete_all_for_provider(
        self, user_id: str, provider_key: str
    ) -> None:
        """
        Remove all user model rows for a provider.

        Called when a user disconnects a provider entirely. Does nothing if
        the provider is not in the catalog.

        Args:
            user_id:      The user's Auth0 sub.
            provider_key: Machine name of the provider.
        """
        provider = await self._providers.get_by_name(provider_key)
        if not provider:
            return
        await self._user_models.delete_for_provider(user_id, provider.id)
