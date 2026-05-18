from __future__ import annotations
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from repositories.base import BaseRepository


@dataclass
class ProviderEntry:
    provider_key:  str
    name:          str
    description:   str
    display_order: int
    auth_config:   dict
    capabilities:  dict
    is_enabled:    bool


class ProviderRegistryRepository(BaseRepository):

    async def get_all(self) -> list[ProviderEntry]:
        rows = await self._fetchall(
            "SELECT provider_key, name, description, display_order, auth_config, capabilities, is_enabled"
            " FROM provider_registry WHERE is_enabled = TRUE"
            " ORDER BY display_order"
        )
        return [self._row(r) for r in rows]

    async def get_by_key(self, provider_key: str) -> ProviderEntry | None:
        row = await self._fetchone(
            "SELECT provider_key, name, description, display_order, auth_config, capabilities, is_enabled"
            " FROM provider_registry WHERE provider_key = %s",
            (provider_key,),
        )
        return self._row(row) if row else None

    async def upsert(
        self,
        provider_key:  str,
        name:          str,
        description:   str,
        display_order: int,
        auth_config:   dict,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self._exec(
            """
            INSERT INTO provider_registry
                (provider_key, name, description, display_order, auth_config, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (provider_key) DO UPDATE
                SET name          = EXCLUDED.name,
                    description   = EXCLUDED.description,
                    display_order = EXCLUDED.display_order,
                    auth_config   = EXCLUDED.auth_config,
                    updated_at    = EXCLUDED.updated_at
            """,
            (provider_key, name, description, display_order, json.dumps(auth_config), now),
        )

    @staticmethod
    def _row(r) -> ProviderEntry:
        cfg  = r[4] if not isinstance(r[4], str) else json.loads(r[4])
        caps = r[5] if not isinstance(r[5], str) else json.loads(r[5])
        return ProviderEntry(
            provider_key  = r[0],
            name          = r[1],
            description   = r[2],
            display_order = r[3],
            auth_config   = cfg,
            capabilities  = caps,
            is_enabled    = bool(r[6]),
        )
