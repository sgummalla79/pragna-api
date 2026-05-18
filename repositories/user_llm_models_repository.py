from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from repositories.base import BaseRepository


@dataclass
class UserLLMModel:
    id:                   str
    user_id:              str
    user_llm_provider_id: str
    model_name:           str
    display_name:         str
    is_active:            bool
    created_at:           str
    modified_at:          str


class UserLLMModelsRepository(BaseRepository):

    async def seed(
        self,
        user_llm_provider_id: str,
        models:               list[dict],   # [{model_name, display_name}]
    ) -> None:
        """Delete all existing models for this provider then insert fresh as inactive."""
        await self._exec(
            "DELETE FROM user_llm_models WHERE user_llm_provider_id = %s",
            (user_llm_provider_id,),
        )
        now = datetime.now(timezone.utc).isoformat()
        for m in models:
            await self._exec(
                "INSERT INTO user_llm_models"
                " (user_llm_provider_id, model_name, display_name, is_active, created_at, modified_at)"
                " VALUES (%s, %s, %s, FALSE, %s, %s)"
                " ON CONFLICT (user_llm_provider_id, model_name) DO NOTHING",
                (user_llm_provider_id, m["model_name"], m["display_name"], now, now),
            )

    async def get_for_provider(
        self,
        user_llm_provider_id: str,
    ) -> list[UserLLMModel]:
        rows = await self._fetchall(
            "SELECT id, user_id, user_llm_provider_id, model_name, display_name,"
            "       is_active, created_at, modified_at"
            " FROM user_llm_models WHERE user_llm_provider_id = %s"
            " ORDER BY display_name",
            (user_llm_provider_id,),
        )
        return [self._row_to_model(r) for r in rows]

    async def get_active(self, user_id: str) -> list[UserLLMModel]:
        """All active models across all providers — used by dropdowns."""
        rows = await self._fetchall(
            "SELECT m.id, m.user_id, m.user_llm_provider_id, m.model_name,"
            "       m.display_name, m.is_active, m.created_at, m.modified_at"
            " FROM user_llm_models m"
            " JOIN user_llm_providers p ON p.id = m.user_llm_provider_id"
            " WHERE m.user_id = %s AND m.is_active = TRUE"
            " ORDER BY p.key_name, m.display_name",
            (user_id,),
        )
        return [self._row_to_model(r) for r in rows]

    async def toggle(
        self,
        user_llm_provider_id: str,
        model_name:           str,
    ) -> Optional[bool]:
        """Flip is_active for one model. Returns new value, or None if not found."""
        row = await self._fetchone(
            "SELECT is_active FROM user_llm_models"
            " WHERE user_llm_provider_id = %s AND model_name = %s",
            (user_llm_provider_id, model_name),
        )
        if not row:
            return None
        new_state = not bool(row[0])
        await self._exec(
            "UPDATE user_llm_models SET is_active = %s"
            " WHERE user_llm_provider_id = %s AND model_name = %s",
            (new_state, user_llm_provider_id, model_name),
        )
        return new_state

    async def rename(
        self,
        user_llm_provider_id: str,
        model_name:           str,
        display_name:         str,
    ) -> bool:
        """Update display_name. modified_at is auto-updated by DB trigger."""
        row = await self._fetchone(
            "SELECT id FROM user_llm_models"
            " WHERE user_llm_provider_id = %s AND model_name = %s",
            (user_llm_provider_id, model_name),
        )
        if not row:
            return False
        await self._exec(
            "UPDATE user_llm_models SET display_name = %s"
            " WHERE user_llm_provider_id = %s AND model_name = %s",
            (display_name.strip()[:100], user_llm_provider_id, model_name),
        )
        return True

    async def deactivate_all(self, user_llm_provider_id: str) -> None:
        """Called when provider is toggled inactive."""
        await self._exec(
            "UPDATE user_llm_models SET is_active = FALSE"
            " WHERE user_llm_provider_id = %s",
            (user_llm_provider_id,),
        )

    async def delete_all(self, user_llm_provider_id: str) -> None:
        """Called when provider is disconnected."""
        await self._exec(
            "DELETE FROM user_llm_models WHERE user_llm_provider_id = %s",
            (user_llm_provider_id,),
        )

    @staticmethod
    def _row_to_model(row) -> UserLLMModel:
        return UserLLMModel(
            id=str(row[0]), user_id=row[1], user_llm_provider_id=str(row[2]),
            model_name=row[3], display_name=row[4], is_active=bool(row[5]),
            created_at=str(row[6]), modified_at=str(row[7]),
        )
