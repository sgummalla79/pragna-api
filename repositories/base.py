"""
BaseRepository — shared async Postgres helpers.

All repositories inherit from this. Each repository owns one domain and
should never reach into another repository's tables directly.
"""

from __future__ import annotations
from typing import Any


class BaseRepository:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def _exec(self, sql: str, params: tuple = ()) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(sql, params)

    async def _fetchone(self, sql: str, params: tuple = ()) -> Any:
        async with self._pool.connection() as conn:
            cur = await conn.execute(sql, params)
            return await cur.fetchone()

    async def _fetchall(self, sql: str, params: tuple = ()) -> list:
        async with self._pool.connection() as conn:
            cur = await conn.execute(sql, params)
            return await cur.fetchall()
