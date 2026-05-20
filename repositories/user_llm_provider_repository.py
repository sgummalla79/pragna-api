"""
UserLLMProviderRepository — CRUD for the `user_llm_providers` table.

Stores one row per user per LLM provider that the user has connected.
Each row holds the encrypted API key and an active flag.

The llm_provider_id FK references llm_providers(id) — not provider name strings.
Use LLMProviderRepository.get_by_name() to resolve a provider name to its UUID
before calling methods here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from repositories.base import BaseRepository


@dataclass
class UserLLMProvider:
    """Represents one row in the `user_llm_providers` table."""
    id:              str
    user_id:         str
    llm_provider_id: str   # UUID FK → llm_providers(id)
    encrypted_value: str
    is_active:       bool
    created_at:      str
    modified_at:     str


class UserLLMProviderRepository(BaseRepository):
    """Pure CRUD repository for the `user_llm_providers` table."""

    async def upsert(
        self,
        user_id:         str,
        llm_provider_id: str,
        encrypted_value: str,
    ) -> UserLLMProvider:
        """
        Insert a new provider key or overwrite the encrypted value if one already exists.

        Sets is_active=TRUE on first insert; updates encrypted_value, is_active, and
        modified_at on conflict. Returns the current row.
        """
        now = self._now()
        row = await self._fetchone(
            "INSERT INTO user_llm_providers"
            "  (user_id, llm_provider_id, encrypted_value, is_active, created_at, modified_at)"
            " VALUES (%s, %s, %s, TRUE, %s, %s)"
            " ON CONFLICT (user_id, llm_provider_id) DO UPDATE SET"
            "   encrypted_value = EXCLUDED.encrypted_value,"
            "   is_active       = TRUE,"
            "   modified_at     = EXCLUDED.modified_at"
            " RETURNING id, user_id, llm_provider_id, encrypted_value, is_active,"
            "           created_at, modified_at",
            (user_id, llm_provider_id, encrypted_value, now, now),
        )
        return self._row(row)

    async def get_by_id(self, record_id: str) -> Optional[UserLLMProvider]:
        """Return the provider row with the given PK, or None."""
        row = await self._fetchone(
            "SELECT id, user_id, llm_provider_id, encrypted_value, is_active,"
            "       created_at, modified_at"
            " FROM user_llm_providers WHERE id = %s",
            (record_id,),
        )
        return self._row(row) if row else None

    async def get_by_user_and_provider(
        self, user_id: str, llm_provider_id: str
    ) -> Optional[UserLLMProvider]:
        """Return the row for a specific user + provider UUID pair, or None."""
        row = await self._fetchone(
            "SELECT id, user_id, llm_provider_id, encrypted_value, is_active,"
            "       created_at, modified_at"
            " FROM user_llm_providers"
            " WHERE user_id = %s AND llm_provider_id = %s",
            (user_id, llm_provider_id),
        )
        return self._row(row) if row else None

    async def list_for_user(self, user_id: str) -> list[UserLLMProvider]:
        """Return all provider rows for a user, regardless of active state."""
        rows = await self._fetchall(
            "SELECT id, user_id, llm_provider_id, encrypted_value, is_active,"
            "       created_at, modified_at"
            " FROM user_llm_providers WHERE user_id = %s",
            (user_id,),
        )
        return [self._row(r) for r in rows]

    async def get_all_keys(self, user_id: str) -> dict[str, str]:
        """
        Return a mapping of {provider_name: encrypted_value} for all of the user's providers.

        Joins to llm_providers to resolve the UUID FK to a human-readable name.
        Used by the LLM factory to look up decryptable API keys by provider name.
        """
        rows = await self._fetchall(
            "SELECT p.name, ulp.encrypted_value"
            " FROM user_llm_providers ulp"
            " JOIN llm_providers p ON p.id = ulp.llm_provider_id"
            " WHERE ulp.user_id = %s",
            (user_id,),
        )
        return {r[0]: r[1] for r in rows}

    async def get_key_statuses(self, user_id: str) -> dict[str, bool]:
        """
        Return {provider_name: is_active} for every provider key the user has stored.

        A provider appears in this dict only if the user has saved an API key for it.
        Used by routes to determine which providers are connected and whether they
        are currently active (able to be used for inference).
        """
        rows = await self._fetchall(
            "SELECT p.name, ulp.is_active"
            " FROM user_llm_providers ulp"
            " JOIN llm_providers p ON p.id = ulp.llm_provider_id"
            " WHERE ulp.user_id = %s",
            (user_id,),
        )
        return {r[0]: bool(r[1]) for r in rows}

    async def update_is_active(
        self, user_id: str, llm_provider_id: str, is_active: bool
    ) -> None:
        """
        Set the is_active flag for a specific user + provider.

        Does not touch the encrypted key. Also updates modified_at.
        """
        await self._exec(
            "UPDATE user_llm_providers"
            " SET is_active = %s, modified_at = %s"
            " WHERE user_id = %s AND llm_provider_id = %s",
            (is_active, self._now(), user_id, llm_provider_id),
        )

    async def delete(self, user_id: str, llm_provider_id: str) -> None:
        """Delete the API key row for a specific user + provider pair."""
        await self._exec(
            "DELETE FROM user_llm_providers"
            " WHERE user_id = %s AND llm_provider_id = %s",
            (user_id, llm_provider_id),
        )

    @staticmethod
    def _row(row) -> UserLLMProvider:
        """Map a raw DB row to a UserLLMProvider dataclass."""
        return UserLLMProvider(
            id=str(row[0]), user_id=row[1],
            llm_provider_id=str(row[2]),
            encrypted_value=row[3],
            is_active=bool(row[4]),
            created_at=str(row[5]),
            modified_at=str(row[6]),
        )
