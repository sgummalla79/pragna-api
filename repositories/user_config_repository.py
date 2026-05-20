"""
UserConfigRepository — CRUD for the `user_config` table.

Stores arbitrary key/value pairs per user. Used for UI preferences (theme),
Bedrock credentials, and any other per-user string configuration.

Keys are plain strings defined in repositories.constants.ConfigKey to avoid
typos across call sites.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from repositories.base import BaseRepository


@dataclass
class UserConfig:
    """Represents one row in the `user_config` table."""
    id:          str
    user_id:     str
    key:         str
    value:       str
    created_at:  str
    modified_at: str


class UserConfigRepository(BaseRepository):
    """Pure CRUD repository for the `user_config` table."""

    async def upsert(self, user_id: str, key: str, value: str) -> None:
        """
        Insert a config entry or overwrite its value if the key already exists.

        Sets created_at on first insert; updates value and modified_at on conflict.
        """
        now = self._now()
        await self._exec(
            "INSERT INTO user_config (user_id, key, value, created_at, modified_at)"
            " VALUES (%s, %s, %s, %s, %s)"
            " ON CONFLICT (user_id, key) DO UPDATE SET"
            "   value       = EXCLUDED.value,"
            "   modified_at = EXCLUDED.modified_at",
            (user_id, key, value, now, now),
        )

    async def get(self, user_id: str, key: str) -> Optional[str]:
        """Return the config value for the given user + key, or None if not set."""
        row = await self._fetchone(
            "SELECT value FROM user_config WHERE user_id = %s AND key = %s",
            (user_id, key),
        )
        return row[0] if row else None

    async def get_all(self, user_id: str) -> dict[str, str]:
        """Return all config entries for a user as a {key: value} dict."""
        rows = await self._fetchall(
            "SELECT key, value FROM user_config WHERE user_id = %s",
            (user_id,),
        )
        return {r[0]: r[1] for r in rows}

    async def delete(self, user_id: str, key: str) -> None:
        """Delete a specific config entry for a user."""
        await self._exec(
            "DELETE FROM user_config WHERE user_id = %s AND key = %s",
            (user_id, key),
        )
