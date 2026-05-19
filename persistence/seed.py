"""
Skill seeder — populates the `skills` and `skill_agents` tables from loaded skills.

Called once at startup after migrations. Idempotent via ON CONFLICT DO UPDATE,
so safe to run on every restart — updates OOB content if it changed on disk.
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
      2. Upsert each agent into `skill_agents` table

    New skills/agents added to disk appear in DB on next restart.
    Existing rows are updated (name, description, icon, version, display_name, content).
    """
    loaded_skills = skill_registry.list_all()

    for loaded in loaded_skills:
        m = loaded.manifest

        skill = await db.skills.upsert(
            name         = m.id,
            display_name = m.name,
            description  = m.description,
        )
        log.info("Seeded skill '%s' (id=%s)", skill.name, skill.id)

        for agent_name in m.ordered_agent_keys:
            display_name = m.agent_labels.get(agent_name)
            content      = loaded.agents.get(agent_name, "")

            await db.agents.upsert(
                skill_id     = skill.id,
                name         = agent_name,
                display_name = display_name,
                content      = content,
            )
            log.debug("  Seeded agent '%s'", agent_name)

    log.info("Skill seeding complete — %d skill(s)", len(loaded_skills))
