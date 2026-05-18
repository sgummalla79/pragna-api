from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from repositories.base import BaseRepository


@dataclass
class User:
    id:          str
    email:       str
    name:        Optional[str]
    picture:     Optional[str]
    created_at:  str
    last_login:  Optional[str]
    modified_at: str


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
            "SELECT id, email, name, picture, created_at, last_login, modified_at"
            " FROM users WHERE id = %s",
            (user_id,),
        )
        return self._row_to_user(row) if row else None

    async def save_llm_provider_key(
        self, user_id: str, llm_provider_id: str, encrypted_value: str
    ) -> None:
        await self._exec(
            "INSERT INTO user_llm_providers (user_id, llm_provider_id, encrypted_value)"
            " VALUES (%s, %s, %s)"
            " ON CONFLICT (user_id, llm_provider_id) DO UPDATE SET"
            "   encrypted_value = EXCLUDED.encrypted_value",
            (user_id, llm_provider_id, encrypted_value),
        )

    async def get_all_llm_provider_keys(self, user_id: str) -> dict[str, str]:
        """Return {provider_name: encrypted_value} — used by auth and LLM factory."""
        rows = await self._fetchall(
            "SELECT p.name, u.encrypted_value"
            " FROM user_llm_providers u"
            " JOIN llm_providers p ON p.id = u.llm_provider_id"
            " WHERE u.user_id = %s",
            (user_id,),
        )
        return {r[0]: r[1] for r in rows}

    async def get_connected_providers(self, user_id: str) -> set[str]:
        """Return set of provider names the user has connected."""
        rows = await self._fetchall(
            "SELECT p.name FROM user_llm_providers u"
            " JOIN llm_providers p ON p.id = u.llm_provider_id"
            " WHERE u.user_id = %s",
            (user_id,),
        )
        return {r[0] for r in rows}

    async def delete_llm_provider_key(self, user_id: str, llm_provider_id: str) -> None:
        await self._exec(
            "DELETE FROM user_llm_providers WHERE user_id = %s AND llm_provider_id = %s",
            (user_id, llm_provider_id),
        )

    async def get_llm_provider_id(self, user_id: str, llm_provider_id: str) -> Optional[str]:
        """Return user_llm_providers.id for a given user + llm_provider_id, or None."""
        row = await self._fetchone(
            "SELECT id FROM user_llm_providers WHERE user_id = %s AND llm_provider_id = %s",
            (user_id, llm_provider_id),
        )
        return str(row[0]) if row else None

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
            picture=row[3], created_at=str(row[4]),
            last_login=str(row[5]) if row[5] else None,
            modified_at=str(row[6]),
        )
