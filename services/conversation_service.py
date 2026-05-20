"""
ConversationService — add skills to conversations and manage execution snapshots.

Coordinates between SkillSnapshotRepository, AgentRepository, and
ConversationRepository to enforce snapshot creation rules when a user
adds a skill to a conversation.
"""

from __future__ import annotations

import logging
from typing import Optional

from repositories.agent_repository import AgentRepository
from repositories.conversation_repository import ConversationRepository
from repositories.skill_repository import SkillRepository
from repositories.skill_snapshot_repository import (
    SkillSnapshot,
    SkillSnapshotAgent,
    SkillSnapshotRepository,
)

log = logging.getLogger(__name__)


class ConversationService:
    """
    Business logic for adding skills to conversations.

    When a skill is added, an execution snapshot is created — a frozen copy of
    the current published agent prompts. Content cannot change after this point;
    only model_id (for provider fallback) can be updated.
    """

    def __init__(
        self,
        conversation_repo: ConversationRepository,
        skill_repo:        SkillRepository,
        agent_repo:        AgentRepository,
        snapshot_repo:     SkillSnapshotRepository,
    ) -> None:
        """Initialise with injected repository instances."""
        self._conversations = conversation_repo
        self._skills        = skill_repo
        self._agents        = agent_repo
        self._snapshots     = snapshot_repo

    async def add_skill(
        self,
        user_id:         str,
        conversation_id: str,
        skill_name:      str,
    ) -> SkillSnapshot:
        """
        Add a skill to a conversation by creating an execution snapshot.

        Business rules enforced here:
          1. Skill must be installed (any snapshot exists for user+skill).
          2. No execution snapshot may already exist for this conversation+skill.
          3. Content is copied from the current published version, or from OOB
             agents if no published version exists.

        Raises ValueError if the skill is not found, not installed, or already added.

        Args:
            user_id:         The user's Auth0 sub.
            conversation_id: UUID of the conversation to add the skill to.
            skill_name:      Machine name of the skill (e.g. 'architect').

        Returns:
            The newly created execution snapshot with agents loaded.
        """
        skill = await self._skills.get_by_name(skill_name)
        if not skill:
            raise ValueError(f"Skill '{skill_name}' not found.")

        if not await self._snapshots.is_installed(user_id, skill.id):
            raise ValueError(f"Skill '{skill_name}' is not installed for this user.")

        existing = await self._snapshots.get_execution_snapshot(conversation_id, skill.id)
        if existing:
            raise ValueError(f"Skill '{skill_name}' is already added to this conversation.")

        base_agents = await self._resolve_base_agents(user_id, skill.id)
        return await self._snapshots.create_execution_snapshot(
            user_id         = user_id,
            skill_id        = skill.id,
            conversation_id = conversation_id,
            base_agents     = base_agents,
        )

    async def get_skill_config(
        self, snapshot_id: str
    ) -> Optional[SkillSnapshot]:
        """
        Return an execution snapshot with its agent model config.

        Args:
            snapshot_id: UUID of the execution snapshot.
        """
        return await self._snapshots.get_by_id(snapshot_id)

    async def update_agent_model(
        self,
        snapshot_id:    str,
        skill_agent_id: str,
        model_id:       Optional[str],
    ) -> None:
        """
        Update the model_id for a single agent within an execution snapshot.

        This is the only mutation allowed on execution snapshots. Used when
        the originally configured model becomes unavailable and the user selects
        a fallback.

        Args:
            snapshot_id:    UUID of the execution snapshot.
            skill_agent_id: UUID of the skill_agents row to update.
            model_id:       New user_llm_models.id UUID, or None to clear.
        """
        await self._snapshots.update_agent_model(snapshot_id, skill_agent_id, model_id)

    async def list_skills_for_conversation(
        self, conversation_id: str
    ) -> list[SkillSnapshot]:
        """
        Return all execution snapshots for a conversation.

        Args:
            conversation_id: UUID of the conversation.
        """
        return await self._snapshots.list_for_conversation(conversation_id)

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _resolve_base_agents(
        self, user_id: str, skill_id: str
    ) -> list[SkillSnapshotAgent]:
        """
        Return the agent list to use as the base for a new execution snapshot.

        Prefers the current published version's agents. Falls back to OOB
        skill_agents if no published version exists.
        """
        published = await self._snapshots.get_current_published(user_id, skill_id)
        if published:
            return published.agents

        oob = await self._agents.list_for_skill(skill_id)
        return [
            SkillSnapshotAgent(
                id="", snapshot_id="",
                skill_agent_id = a.id,
                content        = a.content,
                model_id       = None,
                created_at="", modified_at="",
            )
            for a in oob
        ]
