"""
SkillService — install/uninstall skills and manage the draft/publish lifecycle.

Coordinates between SkillRepository, AgentRepository, and SkillSnapshotRepository
to enforce the business rules around skill versioning.

See docs/SKILL_SNAPSHOT_DESIGN.md for the full snapshot lifecycle.
"""

from __future__ import annotations

import logging
from typing import Optional

from repositories.agent_repository import AgentRepository
from repositories.skill_repository import SkillRepository
from repositories.skill_snapshot_repository import (
    SkillSnapshot,
    SkillSnapshotAgent,
    SkillSnapshotRepository,
)

log = logging.getLogger(__name__)


class SkillService:
    """
    Business logic for skill installation and snapshot management.

    A skill is considered 'installed' for a user when at least one snapshot
    (draft, published, or execution) exists. There is no separate install record.
    """

    def __init__(
        self,
        skill_repo:    SkillRepository,
        agent_repo:    AgentRepository,
        snapshot_repo: SkillSnapshotRepository,
    ) -> None:
        """Initialise with injected repository instances."""
        self._skills    = skill_repo
        self._agents    = agent_repo
        self._snapshots = snapshot_repo

    async def is_installed(self, user_id: str, skill_name: str) -> bool:
        """
        Return True if the user has any snapshot for the named skill.

        Args:
            user_id:    The user's Auth0 sub.
            skill_name: Machine name of the skill (e.g. 'architect').
        """
        skill = await self._skills.get_by_name(skill_name)
        if not skill:
            return False
        return await self._snapshots.is_installed(user_id, skill.id)

    async def install(self, user_id: str, skill_name: str) -> SkillSnapshot:
        """
        Install a skill for a user by creating an initial draft snapshot.

        Copies the out-of-the-box agent content from skill_agents into the draft.
        If the skill is already installed (any snapshot exists), returns the
        existing draft or the current published snapshot without creating a duplicate.

        Raises ValueError if the skill is not found in the catalog.

        Args:
            user_id:    The user's Auth0 sub.
            skill_name: Machine name of the skill to install.
        """
        skill = await self._skills.get_by_name(skill_name)
        if not skill:
            raise ValueError(f"Skill '{skill_name}' not found in catalog.")

        # If already installed, return current state rather than creating a duplicate draft.
        if await self._snapshots.is_installed(user_id, skill.id):
            published = await self._snapshots.get_current_published(user_id, skill.id)
            if published:
                return published
            draft = await self._snapshots.get_draft(user_id, skill.id)
            if draft:
                return draft

        # Build base agents from OOB skill_agents content
        oob_agents = await self._agents.list_for_skill(skill.id)
        base_agents = [
            SkillSnapshotAgent(
                id="", snapshot_id="",
                skill_agent_id = a.id,
                content        = a.content,
                model_id       = None,
                created_at="", modified_at="",
            )
            for a in oob_agents
        ]
        return await self._snapshots.create_draft(user_id, skill.id, base_agents)

    async def uninstall(self, user_id: str, skill_name: str) -> None:
        """
        Remove all draft and published snapshots for a user+skill.

        Execution snapshots are permanently preserved — they are the audit record
        of what ran in each conversation and must never be deleted.

        Does nothing if the skill is not found or not installed.

        Args:
            user_id:    The user's Auth0 sub.
            skill_name: Machine name of the skill to uninstall.
        """
        skill = await self._skills.get_by_name(skill_name)
        if not skill:
            return
        await self._snapshots.uninstall(user_id, skill.id)

    async def get_draft(
        self, user_id: str, skill_name: str
    ) -> Optional[SkillSnapshot]:
        """
        Return the current draft snapshot for a user+skill, or None.

        Args:
            user_id:    The user's Auth0 sub.
            skill_name: Machine name of the skill.
        """
        skill = await self._skills.get_by_name(skill_name)
        if not skill:
            return None
        return await self._snapshots.get_draft(user_id, skill.id)

    async def update_agent(
        self,
        user_id:     str,
        skill_name:  str,
        agent_name:  str,
        content:     str,
        model_id:    Optional[str],
    ) -> SkillSnapshot:
        """
        Edit one agent's content within a draft snapshot.

        If no draft exists, creates one by copying all agents from the current
        published snapshot (or from OOB content if no published version exists).
        Returns the updated draft snapshot.

        Args:
            user_id:    The user's Auth0 sub.
            skill_name: Machine name of the skill.
            agent_name: Machine name of the agent to edit (e.g. 'intake').
            content:    New system prompt content.
            model_id:   Optional user_llm_models.id UUID for model override.
        """
        skill = await self._skills.get_by_name(skill_name)
        if not skill:
            raise ValueError(f"Skill '{skill_name}' not found.")

        skill_agent = await self._agents.get_by_name(skill.id, agent_name)
        if not skill_agent:
            raise ValueError(f"Agent '{agent_name}' not found in skill '{skill_name}'.")

        draft = await self._snapshots.get_draft(user_id, skill.id)
        if not draft:
            draft = await self._create_draft_from_published(user_id, skill.id)

        await self._snapshots.upsert_draft_agent(
            snapshot_id    = draft.id,
            skill_agent_id = skill_agent.id,
            content        = content,
            model_id       = model_id,
        )
        # Reload to reflect changes
        return await self._snapshots.get_draft(user_id, skill.id)

    async def publish_draft(self, user_id: str, skill_name: str) -> SkillSnapshot:
        """
        Publish the current draft for a skill, making it the new current version.

        Raises ValueError if no draft exists or the draft has no agents.

        Args:
            user_id:    The user's Auth0 sub.
            skill_name: Machine name of the skill.
        """
        skill = await self._skills.get_by_name(skill_name)
        if not skill:
            raise ValueError(f"Skill '{skill_name}' not found.")

        draft = await self._snapshots.get_draft(user_id, skill.id)
        if not draft or not draft.agents:
            raise ValueError("No draft to publish.")

        return await self._snapshots.publish_draft(draft.id)

    async def discard_draft(self, user_id: str, skill_name: str) -> None:
        """
        Delete the current draft for a skill.

        Does nothing if no draft exists.

        Args:
            user_id:    The user's Auth0 sub.
            skill_name: Machine name of the skill.
        """
        skill = await self._skills.get_by_name(skill_name)
        if not skill:
            return
        await self._snapshots.discard_draft(user_id, skill.id)

    async def list_published_versions(
        self, user_id: str, skill_name: str
    ) -> list[SkillSnapshot]:
        """
        Return all published versions for a user+skill, newest first.

        Args:
            user_id:    The user's Auth0 sub.
            skill_name: Machine name of the skill.
        """
        skill = await self._skills.get_by_name(skill_name)
        if not skill:
            return []
        return await self._snapshots.list_published(user_id, skill.id)

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _create_draft_from_published(
        self, user_id: str, skill_id: str
    ) -> SkillSnapshot:
        """
        Create a new draft by copying agents from the current published version.

        Falls back to OOB skill_agents if no published version exists.
        """
        published = await self._snapshots.get_current_published(user_id, skill_id)
        if published:
            base_agents = published.agents
        else:
            oob = await self._agents.list_for_skill(skill_id)
            base_agents = [
                SkillSnapshotAgent(
                    id="", snapshot_id="",
                    skill_agent_id = a.id,
                    content        = a.content,
                    model_id       = None,
                    created_at="", modified_at="",
                )
                for a in oob
            ]
        return await self._snapshots.create_draft(user_id, skill_id, base_agents)
