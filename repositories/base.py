"""
BaseRepository — shared async PostgreSQL helpers.

All repositories inherit from this class. Each repository must:
  - Own exactly one table domain (Single Responsibility Principle)
  - Expose only CRUD methods — no business logic, no cross-domain orchestration
  - Use _now() to set created_at on INSERT and modified_at on every UPDATE

Audit columns (created_at, modified_at) are managed entirely at the Python
code level — no DB triggers, no DB DEFAULT values for these columns.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class BaseRepository:
    """
    Base class for all repositories.

    Provides three async helpers for parameterised SQL and a _now() utility
    that returns the current UTC time as an ISO-8601 string. Subclasses must
    call _now() when setting created_at (on INSERT) or modified_at (on UPDATE).
    """

    def __init__(self, pool: Any) -> None:
        """Initialise with the shared async connection pool."""
        self._pool = pool

    def _now(self) -> str:
        """
        Return the current UTC time as an ISO-8601 string.

        Use this when writing created_at on INSERT or modified_at on UPDATE.
        Using a single call per operation ensures both fields share the same
        instant within one request.
        """
        return datetime.now(timezone.utc).isoformat()

    async def _exec(self, sql: str, params: tuple = ()) -> None:
        """
        Execute a write statement (INSERT / UPDATE / DELETE) with no return value.

        Acquires a connection from the pool, executes the statement, and releases
        the connection automatically. Raises on DB errors.
        """
        async with self._pool.connection() as conn:
            await conn.execute(sql, params)

    async def _fetchone(self, sql: str, params: tuple = ()) -> Any:
        """
        Execute a SELECT and return the first row, or None if no rows match.

        Use for lookups by primary key or any query expected to return at most
        one row. Returns the raw psycopg Row object — pass it to the repo's
        _row() static method to convert to a typed dataclass.
        """
        async with self._pool.connection() as conn:
            cur = await conn.execute(sql, params)
            return await cur.fetchone()

    async def _fetchall(self, sql: str, params: tuple = ()) -> list:
        """
        Execute a SELECT and return all matching rows as a list.

        Returns a list of raw psycopg Row objects. Pass each through the repo's
        _row() static method to convert to typed dataclasses.
        """
        async with self._pool.connection() as conn:
            cur = await conn.execute(sql, params)
            return await cur.fetchall()
