from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from repositories.base import BaseRepository


@dataclass
class UserLLMModel:
    id:           str
    user_id:      str
    provider_key: str
    model_id:     str
    display_name: str
    isactive:     bool
    created_at:   str


class UserLLMModelsRepository(BaseRepository):

    async def seed(
        self,
        user_id:      str,
        provider_key: str,
        models:       list[dict],   # [{model_id, display_name}]
    ) -> None:
        """Delete all existing models for this provider then insert fresh as inactive."""
        await self._exec(
            "DELETE FROM user_llm_models WHERE user_id = %s AND provider_key = %s",
            (user_id, provider_key),
        )
        now = datetime.now(timezone.utc).isoformat()
        for m in models:
            await self._exec(
                "INSERT INTO user_llm_models"
                " (user_id, provider_key, model_id, display_name, isactive, created_at)"
                " VALUES (%s, %s, %s, %s, FALSE, %s)"
                " ON CONFLICT (user_id, provider_key, model_id) DO NOTHING",
                (user_id, provider_key, m["model_id"], m["display_name"], now),
            )

    async def get_for_provider(
        self,
        user_id:      str,
        provider_key: str,
    ) -> list[UserLLMModel]:
        rows = await self._fetchall(
            "SELECT id, user_id, provider_key, model_id, display_name, isactive, created_at"
            " FROM user_llm_models WHERE user_id = %s AND provider_key = %s"
            " ORDER BY display_name",
            (user_id, provider_key),
        )
        return [self._row_to_model(r) for r in rows]

    async def get_active(self, user_id: str) -> list[UserLLMModel]:
        """All active models across all providers — used by dropdowns."""
        rows = await self._fetchall(
            "SELECT id, user_id, provider_key, model_id, display_name, isactive, created_at"
            " FROM user_llm_models WHERE user_id = %s AND isactive = TRUE"
            " ORDER BY provider_key, display_name",
            (user_id,),
        )
        return [self._row_to_model(r) for r in rows]

    async def toggle(
        self,
        user_id:      str,
        provider_key: str,
        model_id:     str,
    ) -> Optional[bool]:
        """Flip isactive for one model. Returns new isactive value, or None if not found."""
        row = await self._fetchone(
            "SELECT isactive FROM user_llm_models"
            " WHERE user_id = %s AND provider_key = %s AND model_id = %s",
            (user_id, provider_key, model_id),
        )
        if not row:
            return None
        new_state = not bool(row[0])
        await self._exec(
            "UPDATE user_llm_models SET isactive = %s"
            " WHERE user_id = %s AND provider_key = %s AND model_id = %s",
            (new_state, user_id, provider_key, model_id),
        )
        return new_state

    async def rename(
        self,
        user_id:      str,
        provider_key: str,
        model_id:     str,
        display_name: str,
    ) -> bool:
        """Update display_name for one model. Returns True if found, False otherwise."""
        row = await self._fetchone(
            "SELECT id FROM user_llm_models"
            " WHERE user_id = %s AND provider_key = %s AND model_id = %s",
            (user_id, provider_key, model_id),
        )
        if not row:
            return False
        await self._exec(
            "UPDATE user_llm_models SET display_name = %s"
            " WHERE user_id = %s AND provider_key = %s AND model_id = %s",
            (display_name.strip()[:100], user_id, provider_key, model_id),
        )
        return True

    async def deactivate_all(self, user_id: str, provider_key: str) -> None:
        """Called when provider is toggled inactive."""
        await self._exec(
            "UPDATE user_llm_models SET isactive = FALSE"
            " WHERE user_id = %s AND provider_key = %s",
            (user_id, provider_key),
        )

    async def delete_all(self, user_id: str, provider_key: str) -> None:
        """Called when provider is disconnected."""
        await self._exec(
            "DELETE FROM user_llm_models WHERE user_id = %s AND provider_key = %s",
            (user_id, provider_key),
        )

    @staticmethod
    def _row_to_model(row) -> UserLLMModel:
        return UserLLMModel(
            id=str(row[0]), user_id=row[1], provider_key=row[2],
            model_id=row[3], display_name=row[4], isactive=bool(row[5]),
            created_at=str(row[6]),
        )
