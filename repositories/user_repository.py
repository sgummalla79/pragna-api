"""
UserRepository — CRUD for the `users` table.

Owns only the `users` table. All provider-key and config operations
belong to UserLLMProviderRepository and UserConfigRepository respectively.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from repositories.base import BaseRepository


@dataclass
class User:
    """Represents a single row in the `users` table."""
    id:          str
    email:       str
    name:        Optional[str]
    picture:     Optional[str]
    created_at:  str
    last_login:  Optional[str]
    modified_at: str


class UserRepository(BaseRepository):
    """Pure CRUD repository for the `users` table."""

    async def upsert(
        self,
        user_id: str,
        email:   str,
        name:    Optional[str],
        picture: Optional[str],
    ) -> User:
        """
        Insert a new user or update their profile fields if they already exist.

        Sets created_at on first insert; updates email, name, picture, last_login,
        and modified_at on every subsequent call. Returns the current user row.
        """
        now = self._now()
        await self._exec(
            "INSERT INTO users (id, email, name, picture, created_at, last_login, modified_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (id) DO UPDATE SET"
            "   email       = EXCLUDED.email,"
            "   name        = EXCLUDED.name,"
            "   picture     = EXCLUDED.picture,"
            "   last_login  = EXCLUDED.last_login,"
            "   modified_at = EXCLUDED.modified_at",
            (user_id, email, name, picture, now, now, now),
        )
        return await self.get_by_id(user_id)

    async def get_by_id(self, user_id: str) -> Optional[User]:
        """Return the user with the given Auth0 sub, or None if not found."""
        row = await self._fetchone(
            "SELECT id, email, name, picture, created_at, last_login, modified_at"
            " FROM users WHERE id = %s",
            (user_id,),
        )
        return self._row(row) if row else None

    async def get_by_email(self, email: str) -> Optional[User]:
        """Return the user with the given email address, or None if not found."""
        row = await self._fetchone(
            "SELECT id, email, name, picture, created_at, last_login, modified_at"
            " FROM users WHERE email = %s",
            (email,),
        )
        return self._row(row) if row else None

    @staticmethod
    def _row(row) -> User:
        """Map a raw DB row to a User dataclass."""
        return User(
            id=str(row[0]), email=row[1], name=row[2],
            picture=row[3], created_at=str(row[4]),
            last_login=str(row[5]) if row[5] else None,
            modified_at=str(row[6]),
        )
