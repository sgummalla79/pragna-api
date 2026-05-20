"""
UserLLMModelRepository — CRUD for the `user_llm_models` table.

Maps which global catalog models a user has activated. Each row links a user
to a single llm_models entry and tracks their display name and active state.

Several read methods JOIN to llm_models and llm_providers to return the
human-readable provider name and model identifier alongside each row — this
is the resolved view callers need for inference and UI rendering.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from repositories.base import BaseRepository


@dataclass
class UserLLMModel:
    """Raw row from the `user_llm_models` table without JOIN fields."""
    id:           str
    user_id:      str
    llm_model_id: str   # UUID FK → llm_models(id)
    display_name: str
    is_active:    bool
    created_at:   str
    modified_at:  str


@dataclass
class UserLLMModelResolved:
    """
    Enriched view of user_llm_models joined to llm_models and llm_providers.

    Used wherever callers need the provider name (e.g. 'openai') and model
    name (e.g. 'gpt-4o') in addition to user-specific fields.
    """
    id:           str
    user_id:      str
    llm_model_id: str
    model_name:   str   # llm_models.name
    provider_key: str   # llm_providers.name
    display_name: str
    is_active:    bool
    created_at:   str
    modified_at:  str


class UserLLMModelRepository(BaseRepository):
    """Pure CRUD repository for the `user_llm_models` table."""

    async def upsert(
        self,
        user_id:      str,
        llm_model_id: str,
        display_name: str,
    ) -> UserLLMModel:
        """
        Insert a model entry for a user or update its display name if it already exists.

        Does NOT change is_active on conflict — existing active state is preserved.
        Sets created_at on first insert; updates display_name and modified_at on conflict.
        Returns the current row.
        """
        now = self._now()
        row = await self._fetchone(
            "INSERT INTO user_llm_models"
            "  (user_id, llm_model_id, display_name, is_active, created_at, modified_at)"
            " VALUES (%s, %s, %s, FALSE, %s, %s)"
            " ON CONFLICT (user_id, llm_model_id) DO UPDATE SET"
            "   display_name = EXCLUDED.display_name,"
            "   modified_at  = EXCLUDED.modified_at"
            " RETURNING id, user_id, llm_model_id, display_name, is_active,"
            "           created_at, modified_at",
            (user_id, llm_model_id, display_name, now, now),
        )
        return self._row(row)

    async def get_by_id(self, record_id: str) -> Optional[UserLLMModel]:
        """Return the user model row with the given PK, or None."""
        row = await self._fetchone(
            "SELECT id, user_id, llm_model_id, display_name, is_active, created_at, modified_at"
            " FROM user_llm_models WHERE id = %s",
            (record_id,),
        )
        return self._row(row) if row else None

    async def get_by_id_resolved(self, record_id: str) -> Optional[tuple[str, str]]:
        """
        Resolve a user_llm_models.id to a (provider_name, model_name) tuple.

        Returns None if the record is not found. Used at execution time to convert
        a stored UUID reference into the provider/model strings the LLM factory needs.
        """
        row = await self._fetchone(
            "SELECT lp.name, lm.name"
            " FROM user_llm_models ulm"
            " JOIN llm_models lm ON lm.id = ulm.llm_model_id"
            " JOIN llm_providers lp ON lp.id = lm.llm_provider_id"
            " WHERE ulm.id = %s",
            (record_id,),
        )
        return (str(row[0]), str(row[1])) if row else None

    async def get_active(self, user_id: str) -> list[UserLLMModelResolved]:
        """
        Return all models the user has marked active, with provider and model name included.

        Results are ordered by provider then model name. Used by the smart-pick logic
        and by the /models/active endpoint to populate inference dropdowns.
        """
        rows = await self._fetchall(
            "SELECT ulm.id, ulm.user_id, ulm.llm_model_id, ulm.display_name,"
            "       ulm.is_active, ulm.created_at, ulm.modified_at,"
            "       lm.name AS model_name, lp.name AS provider_key"
            " FROM user_llm_models ulm"
            " JOIN llm_models lm ON lm.id = ulm.llm_model_id"
            " JOIN llm_providers lp ON lp.id = lm.llm_provider_id"
            " WHERE ulm.user_id = %s AND ulm.is_active = TRUE"
            " ORDER BY lp.name, lm.name",
            (user_id,),
        )
        return [self._row_resolved(r) for r in rows]

    async def list_for_user(self, user_id: str) -> list[UserLLMModelResolved]:
        """
        Return all model rows for a user regardless of active state, with names resolved.

        Ordered by provider then model name. Used by the settings UI to show all
        available models for a user.
        """
        rows = await self._fetchall(
            "SELECT ulm.id, ulm.user_id, ulm.llm_model_id, ulm.display_name,"
            "       ulm.is_active, ulm.created_at, ulm.modified_at,"
            "       lm.name AS model_name, lp.name AS provider_key"
            " FROM user_llm_models ulm"
            " JOIN llm_models lm ON lm.id = ulm.llm_model_id"
            " JOIN llm_providers lp ON lp.id = lm.llm_provider_id"
            " WHERE ulm.user_id = %s"
            " ORDER BY lp.name, lm.name",
            (user_id,),
        )
        return [self._row_resolved(r) for r in rows]

    async def list_for_provider(
        self, user_id: str, llm_provider_id: str
    ) -> list[UserLLMModelResolved]:
        """
        Return all model rows for a user that belong to a specific provider UUID.

        Ordered by model name. Used by the per-provider model management UI.
        """
        rows = await self._fetchall(
            "SELECT ulm.id, ulm.user_id, ulm.llm_model_id, ulm.display_name,"
            "       ulm.is_active, ulm.created_at, ulm.modified_at,"
            "       lm.name AS model_name, lp.name AS provider_key"
            " FROM user_llm_models ulm"
            " JOIN llm_models lm ON lm.id = ulm.llm_model_id"
            " JOIN llm_providers lp ON lp.id = lm.llm_provider_id"
            " WHERE ulm.user_id = %s AND lm.llm_provider_id = %s"
            " ORDER BY lm.name",
            (user_id, llm_provider_id),
        )
        return [self._row_resolved(r) for r in rows]

    async def update_is_active(
        self, user_id: str, llm_model_id: str, is_active: bool
    ) -> None:
        """
        Set the is_active flag for a specific user + model UUID pair.

        Also updates modified_at. The toggle decision (read current → flip) is the
        caller's responsibility and belongs in the service layer.
        """
        await self._exec(
            "UPDATE user_llm_models SET is_active = %s, modified_at = %s"
            " WHERE user_id = %s AND llm_model_id = %s",
            (is_active, self._now(), user_id, llm_model_id),
        )

    async def update_is_active_for_provider(
        self, user_id: str, llm_provider_id: str, is_active: bool
    ) -> None:
        """
        Set is_active on all models belonging to a specific provider for a user.

        Used when toggling or disconnecting an entire provider at once.
        """
        await self._exec(
            "UPDATE user_llm_models SET is_active = %s, modified_at = %s"
            " WHERE user_id = %s"
            "   AND llm_model_id IN"
            "       (SELECT id FROM llm_models WHERE llm_provider_id = %s)",
            (is_active, self._now(), user_id, llm_provider_id),
        )

    async def update_display_name(
        self, user_id: str, llm_model_id: str, display_name: str
    ) -> None:
        """
        Update the user-facing display name for a model and set modified_at.

        Any validation or trimming of display_name belongs in the service layer.
        """
        await self._exec(
            "UPDATE user_llm_models SET display_name = %s, modified_at = %s"
            " WHERE user_id = %s AND llm_model_id = %s",
            (display_name, self._now(), user_id, llm_model_id),
        )

    async def delete_for_provider(self, user_id: str, llm_provider_id: str) -> None:
        """
        Delete all user model rows for a specific provider.

        Called when a user disconnects a provider. The FK cascade from llm_models
        is not relied on here — we explicitly delete to remain explicit.
        """
        await self._exec(
            "DELETE FROM user_llm_models"
            " WHERE user_id = %s"
            "   AND llm_model_id IN"
            "       (SELECT id FROM llm_models WHERE llm_provider_id = %s)",
            (user_id, llm_provider_id),
        )

    @staticmethod
    def _row(row) -> UserLLMModel:
        """Map a raw DB row (no JOIN columns) to a UserLLMModel dataclass."""
        return UserLLMModel(
            id=str(row[0]), user_id=row[1],
            llm_model_id=str(row[2]),
            display_name=row[3],
            is_active=bool(row[4]),
            created_at=str(row[5]),
            modified_at=str(row[6]),
        )

    @staticmethod
    def _row_resolved(row) -> UserLLMModelResolved:
        """Map a JOIN row (with model_name and provider_key) to a UserLLMModelResolved dataclass."""
        return UserLLMModelResolved(
            id=str(row[0]), user_id=row[1],
            llm_model_id=str(row[2]),
            display_name=row[3],
            is_active=bool(row[4]),
            created_at=str(row[5]),
            modified_at=str(row[6]),
            model_name=row[7],
            provider_key=row[8],
        )
