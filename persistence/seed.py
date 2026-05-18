"""
Skill seeder — populates the `skills` and `agents` tables from loaded skills.

Called once at startup after migrations. Idempotent via ON CONFLICT DO NOTHING,
so safe to run on every restart — only inserts rows that don't exist yet.
"""

from __future__ import annotations
import logging

from persistence.db import DBContext
from framework.registry import SkillRegistry

log = logging.getLogger(__name__)


async def seed_skills(db: DBContext, skill_registry: SkillRegistry) -> None:
    """
    For each skill loaded from disk:
      1. Upsert into `skills` table
      2. Upsert each agent into `agents` table

    New skills/agents added to disk appear in DB on next restart.
    Existing rows are updated (name, description, icon, version, label, default_content).
    """
    loaded_skills = skill_registry.list_all()

    for loaded in loaded_skills:
        m = loaded.manifest

        skill = await db.skills.upsert(
            skill_key   = m.id,
            name        = m.name,
            description = m.description,
            icon        = m.icon,
            version     = m.version,
        )
        log.info("Seeded skill '%s' (id=%s)", skill.skill_key, skill.id)

        for agent_key in m.ordered_agent_keys:
            label           = m.agent_labels.get(agent_key)
            default_content = loaded.agents.get(agent_key, "")

            await db.agents.upsert(
                skill_id        = skill.id,
                agent_key       = agent_key,
                label           = label,
                default_content = default_content,
            )
            log.debug("  Seeded agent '%s'", agent_key)

    log.info("Skill seeding complete — %d skill(s)", len(loaded_skills))
