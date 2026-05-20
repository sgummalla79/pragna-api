"""
ProviderService — connect, disconnect, and query LLM provider connections.

Manages the relationship between users and their LLM provider API keys.
Bedrock credentials are stored separately in user_config (not user_llm_providers)
because Bedrock uses URL+token credentials rather than a single API key.
"""

from __future__ import annotations

import logging
from typing import Optional

from repositories.constants import ConfigKey
from repositories.llm_provider_repository import LLMProviderRepository
from repositories.user_llm_provider_repository import UserLLMProviderRepository
from repositories.user_llm_model_repository import UserLLMModelRepository
from repositories.user_config_repository import UserConfigRepository

log = logging.getLogger(__name__)


class ProviderService:
    """
    Handles all business logic for connecting and disconnecting LLM providers.

    Provider keys are stored encrypted. The encryption/decryption utilities
    live in utils/key_encryption.py and are called by the routes before
    passing values to this service.
    """

    def __init__(
        self,
        llm_provider_repo:      LLMProviderRepository,
        user_llm_provider_repo: UserLLMProviderRepository,
        user_llm_model_repo:    UserLLMModelRepository,
        user_config_repo:       UserConfigRepository,
    ) -> None:
        """Initialise with injected repository instances."""
        self._providers      = llm_provider_repo
        self._user_providers = user_llm_provider_repo
        self._user_models    = user_llm_model_repo
        self._config         = user_config_repo

    async def connect(
        self,
        user_id:         str,
        provider_key:    str,
        encrypted_value: str,
    ) -> None:
        """
        Save an encrypted API key for a catalog provider and mark it active.

        Resolves the provider_key (e.g. 'openai') to its UUID in llm_providers
        before storing. Raises ValueError if the provider is not in the catalog.

        Args:
            user_id:         The user's Auth0 sub.
            provider_key:    Machine name of the provider (e.g. 'anthropic').
            encrypted_value: Already-encrypted API key string.
        """
        provider = await self._providers.get_by_name(provider_key)
        if not provider:
            raise ValueError(f"Unknown provider: '{provider_key}'")
        await self._user_providers.upsert(user_id, provider.id, encrypted_value)

    async def disconnect(self, user_id: str, provider_key: str) -> None:
        """
        Remove a provider API key and deactivate all models for that provider.

        If the provider is not found in the catalog, the operation is a no-op
        (the key may already have been deleted).

        Args:
            user_id:      The user's Auth0 sub.
            provider_key: Machine name of the provider to disconnect.
        """
        provider = await self._providers.get_by_name(provider_key)
        if not provider:
            return
        await self._user_providers.delete(user_id, provider.id)
        await self._user_models.delete_for_provider(user_id, provider.id)

    async def get_key_statuses(self, user_id: str) -> dict[str, bool]:
        """
        Return {provider_name: is_active} for all providers the user has connected.

        A provider appears in this dict only if the user has saved an API key.
        Bedrock status is appended separately from user_config.

        Args:
            user_id: The user's Auth0 sub.

        Returns:
            Mapping of provider machine name to its current active state.
        """
        statuses = await self._user_providers.get_key_statuses(user_id)

        # Bedrock is stored in user_config rather than user_llm_providers
        # because its credentials are URL+token rather than a single API key.
        bedrock_url = await self._config.get(user_id, ConfigKey.BEDROCK_URL)
        if bedrock_url:
            statuses[ConfigKey.BEDROCK_URL] = True   # connected = active by default

        return statuses

    async def get_all_encrypted_keys(self, user_id: str) -> dict[str, str]:
        """
        Return {provider_name: encrypted_value} for all catalog providers.

        Used by the LLM factory to retrieve API keys for decryption.

        Args:
            user_id: The user's Auth0 sub.
        """
        return await self._user_providers.get_all_keys(user_id)

    async def toggle(self, user_id: str, provider_key: str) -> bool:
        """
        Flip the is_active state for a provider.

        If deactivating, also deactivates all models for that provider.
        Returns the new active state.

        Raises ValueError if the provider key is not connected.

        Args:
            user_id:      The user's Auth0 sub.
            provider_key: Machine name of the provider to toggle.
        """
        provider = await self._providers.get_by_name(provider_key)
        if not provider:
            raise ValueError(f"Unknown provider: '{provider_key}'")

        existing = await self._user_providers.get_by_user_and_provider(user_id, provider.id)
        if not existing:
            raise ValueError(f"Provider '{provider_key}' is not connected.")

        new_state = not existing.is_active
        await self._user_providers.update_is_active(user_id, provider.id, new_state)

        if not new_state:
            # When deactivating a provider, deactivate all its models too.
            await self._user_models.update_is_active_for_provider(user_id, provider.id, False)

        return new_state

    async def connect_bedrock(
        self,
        user_id:         str,
        bedrock_url:     str,
        bedrock_token:   str,
    ) -> None:
        """
        Save Bedrock credentials in user_config.

        Bedrock uses a URL+token auth scheme rather than a single API key,
        so its credentials are stored in user_config rather than user_llm_providers.
        Values must already be encrypted by the caller.

        Args:
            user_id:       The user's Auth0 sub.
            bedrock_url:   Encrypted Bedrock endpoint URL.
            bedrock_token: Encrypted Bedrock access token.
        """
        await self._config.upsert(user_id, ConfigKey.BEDROCK_URL,   bedrock_url)
        await self._config.upsert(user_id, ConfigKey.BEDROCK_TOKEN, bedrock_token)
        await self._config.upsert(user_id, ConfigKey.BEDROCK_MODE,  "bedrock")

    async def disconnect_bedrock(self, user_id: str) -> None:
        """
        Remove all Bedrock credentials from user_config.

        Args:
            user_id: The user's Auth0 sub.
        """
        await self._config.delete(user_id, ConfigKey.BEDROCK_URL)
        await self._config.delete(user_id, ConfigKey.BEDROCK_TOKEN)
        await self._config.delete(user_id, ConfigKey.BEDROCK_MODE)

    async def get_bedrock_credentials(self, user_id: str) -> dict[str, Optional[str]]:
        """
        Return the stored Bedrock credentials for a user.

        Returns a dict with keys 'url', 'token', and 'mode'. Values are None if
        the credential has not been set.

        Args:
            user_id: The user's Auth0 sub.
        """
        return {
            "url":   await self._config.get(user_id, ConfigKey.BEDROCK_URL),
            "token": await self._config.get(user_id, ConfigKey.BEDROCK_TOKEN),
            "mode":  await self._config.get(user_id, ConfigKey.BEDROCK_MODE),
        }
