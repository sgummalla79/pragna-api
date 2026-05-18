from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from repositories.base import BaseRepository


@dataclass
class User:
    id:         str
    email:      str
    name:       Optional[str]
    picture:    Optional[str]
    created_at: str
    last_login: Optional[str]


class UserRepository(BaseRepository):

    async def upsert(
        self,
        user_id: str,
        email:   str,
        name:    Optional[str],
        picture: Optional[str],
    ) -> User:
        now = datetime.now(timezone.utc).isoformat()
        await self._exec(
            "INSERT INTO users (id, email, name, picture, created_at, last_login)"
            " VALUES (%s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (id) DO UPDATE SET"
            "   email = EXCLUDED.email,"
            "   name = EXCLUDED.name,"
            "   picture = EXCLUDED.picture,"
            "   last_login = EXCLUDED.last_login",
            (user_id, email, name, picture, now, now),
        )
        return await self.get_by_id(user_id)

    async def get_by_id(self, user_id: str) -> Optional[User]:
        row = await self._fetchone(
            "SELECT id, email, name, picture, created_at, last_login"
            " FROM users WHERE id = %s",
            (user_id,),
        )
        return self._row_to_user(row) if row else None

    async def save_llm_provider_key(self, user_id: str, key_name: str, encrypted_value: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self._exec(
            "INSERT INTO user_llm_providers (user_id, key_name, encrypted_value, isactive, updated_at)"
            " VALUES (%s, %s, %s, TRUE, %s)"
            " ON CONFLICT (user_id, key_name) DO UPDATE SET"
            "   encrypted_value = EXCLUDED.encrypted_value,"
            "   isactive = TRUE,"
            "   updated_at = EXCLUDED.updated_at",
            (user_id, key_name, encrypted_value, now),
        )

    async def get_all_llm_provider_keys(self, user_id: str) -> dict[str, str]:
        """Return {key_name: encrypted_value} for ACTIVE keys only — used by auth and LLM factory."""
        rows = await self._fetchall(
            "SELECT key_name, encrypted_value FROM user_llm_providers"
            " WHERE user_id = %s AND isactive = TRUE",
            (user_id,),
        )
        return {r[0]: r[1] for r in rows}

    async def get_llm_provider_key_statuses(self, user_id: str) -> dict[str, bool]:
        """Return {key_name: isactive} for ALL stored keys — used by the providers UI."""
        rows = await self._fetchall(
            "SELECT key_name, isactive FROM user_llm_providers WHERE user_id = %s",
            (user_id,),
        )
        return {r[0]: bool(r[1]) for r in rows}

    async def set_llm_provider_key_active(self, user_id: str, key_name: str, isactive: bool) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self._exec(
            "UPDATE user_llm_providers SET isactive = %s, updated_at = %s"
            " WHERE user_id = %s AND key_name = %s",
            (isactive, now, user_id, key_name),
        )

    async def delete_llm_provider_key(self, user_id: str, key_name: str) -> None:
        await self._exec(
            "DELETE FROM user_llm_providers WHERE user_id = %s AND key_name = %s",
            (user_id, key_name),
        )

    async def save_config(self, user_id: str, key: str, value: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self._exec(
            "INSERT INTO user_config (user_id, key, value, updated_at)"
            " VALUES (%s, %s, %s, %s)"
            " ON CONFLICT (user_id, key) DO UPDATE SET"
            "   value = EXCLUDED.value, updated_at = EXCLUDED.updated_at",
            (user_id, key, value, now),
        )

    async def get_config(self, user_id: str, key: str) -> Optional[str]:
        row = await self._fetchone(
            "SELECT value FROM user_config WHERE user_id = %s AND key = %s",
            (user_id, key),
        )
        return row[0] if row else None

    async def get_all_config(self, user_id: str) -> dict[str, str]:
        rows = await self._fetchall(
            "SELECT key, value FROM user_config WHERE user_id = %s",
            (user_id,),
        )
        return {r[0]: r[1] for r in rows}

    async def delete_config(self, user_id: str, key: str) -> None:
        await self._exec(
            "DELETE FROM user_config WHERE user_id = %s AND key = %s",
            (user_id, key),
        )

    @staticmethod
    def _row_to_user(row) -> User:
        return User(
            id=row[0], email=row[1], name=row[2],
            picture=row[3], created_at=str(row[4]), last_login=str(row[5]) if row[5] else None,
        )
