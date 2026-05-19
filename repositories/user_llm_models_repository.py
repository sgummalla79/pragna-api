from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from repositories.base import BaseRepository


@dataclass
class UserLLMModel:
    id:           str
    user_id:      str
    llm_model_id: str
    display_name: str
    is_active:    bool
    created_at:   str
    modified_at:  str


class UserLLMModelsRepository(BaseRepository):

    async def seed(
        self,
        user_id:      str,
        llm_model_id: str,
        display_name: str,
    ) -> UserLLMModel:
        """Upsert a model for a user — preserves is_active state on conflict."""
        row = await self._fetchone(
            "INSERT INTO user_llm_models (user_id, llm_model_id, display_name)"
            " VALUES (%s, %s, %s)"
            " ON CONFLICT (user_id, llm_model_id) DO UPDATE SET display_name = EXCLUDED.display_name"
            " RETURNING id, user_id, llm_model_id, display_name, is_active, created_at, modified_at",
            (user_id, llm_model_id, display_name),
        )
        return self._row(row)

    async def get_by_id_resolved(self, user_llm_model_id: str) -> Optional[tuple[str, str]]:
        """Resolve user_llm_models.id → (provider_name, model_name) strings."""
        row = await self._fetchone(
            "SELECT lp.name, lm.name"
            " FROM user_llm_models ulm"
            " JOIN llm_models lm ON lm.id = ulm.llm_model_id"
            " JOIN llm_providers lp ON lp.id = lm.llm_provider_id"
            " WHERE ulm.id = %s",
            (user_llm_model_id,),
        )
        return (row[0], row[1]) if row else None

    async def get_by_id(self, model_id: str) -> Optional[UserLLMModel]:
        row = await self._fetchone(
            "SELECT id, user_id, llm_model_id, display_name, is_active, created_at, modified_at"
            " FROM user_llm_models WHERE id = %s",
            (model_id,),
        )
        return self._row(row) if row else None

    async def get_active(self, user_id: str) -> list[UserLLMModel]:
        """All active models for a user."""
        rows = await self._fetchall(
            "SELECT id, user_id, llm_model_id, display_name, is_active, created_at, modified_at"
            " FROM user_llm_models"
            " WHERE user_id = %s AND is_active = TRUE"
            " ORDER BY display_name",
            (user_id,),
        )
        return [self._row(r) for r in rows]

    async def get_for_user(self, user_id: str) -> list[UserLLMModel]:
        """All models for a user regardless of active status."""
        rows = await self._fetchall(
            "SELECT id, user_id, llm_model_id, display_name, is_active, created_at, modified_at"
            " FROM user_llm_models WHERE user_id = %s ORDER BY display_name",
            (user_id,),
        )
        return [self._row(r) for r in rows]

    async def toggle(self, user_id: str, llm_model_id: str) -> Optional[bool]:
        """Flip is_active. Returns new value or None if not found."""
        row = await self._fetchone(
            "SELECT is_active FROM user_llm_models WHERE user_id = %s AND llm_model_id = %s",
            (user_id, llm_model_id),
        )
        if not row:
            return None
        new_state = not bool(row[0])
        await self._exec(
            "UPDATE user_llm_models SET is_active = %s WHERE user_id = %s AND llm_model_id = %s",
            (new_state, user_id, llm_model_id),
        )
        return new_state

    async def rename(self, user_id: str, llm_model_id: str, display_name: str) -> bool:
        """Update display_name. Returns True if found."""
        row = await self._fetchone(
            "SELECT id FROM user_llm_models WHERE user_id = %s AND llm_model_id = %s",
            (user_id, llm_model_id),
        )
        if not row:
            return False
        await self._exec(
            "UPDATE user_llm_models SET display_name = %s WHERE user_id = %s AND llm_model_id = %s",
            (display_name.strip()[:100], user_id, llm_model_id),
        )
        return True

    async def deactivate_for_provider(self, user_id: str, llm_provider_id: str) -> None:
        """Deactivate all models belonging to a provider (via llm_models catalog)."""
        await self._exec(
            "UPDATE user_llm_models SET is_active = FALSE"
            " WHERE user_id = %s"
            "   AND llm_model_id IN (SELECT id FROM llm_models WHERE llm_provider_id = %s)",
            (user_id, llm_provider_id),
        )

    async def delete_for_provider(self, user_id: str, llm_provider_id: str) -> None:
        """Delete all models belonging to a provider (via llm_models catalog)."""
        await self._exec(
            "DELETE FROM user_llm_models"
            " WHERE user_id = %s"
            "   AND llm_model_id IN (SELECT id FROM llm_models WHERE llm_provider_id = %s)",
            (user_id, llm_provider_id),
        )

    @staticmethod
    def _row(row) -> UserLLMModel:
        return UserLLMModel(
            id=str(row[0]), user_id=row[1], llm_model_id=str(row[2]),
            display_name=row[3], is_active=bool(row[4]),
            created_at=str(row[5]), modified_at=str(row[6]),
        )
