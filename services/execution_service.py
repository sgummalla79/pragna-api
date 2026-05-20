"""
ExecutionService — set up, retry, and resolve config for skill pipeline executions.

This service handles everything that happens BEFORE the SSE stream starts:
  - Concurrent run guard
  - Session agent config resolution (model UUID → provider+model strings)
  - Execution record creation

The SSE streaming itself (_stream_graph) lives in api/routes/executions.py
and is intentionally not part of this service — it has HTTP/streaming concerns
that belong in the route layer.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from repositories.agent_repository import AgentRepository
from repositories.skill_execution_repository import SkillExecution, SkillExecutionRepository
from repositories.skill_snapshot_repository import SkillSnapshot, SkillSnapshotRepository
from repositories.user_llm_model_repository import UserLLMModelRepository

log = logging.getLogger(__name__)


class ExecutionService:
    """
    Pre-flight logic for starting and retrying skill pipeline executions.

    All methods return the data the route handler needs to hand off to
    _stream_graph() — they do not start the stream themselves.
    """

    def __init__(
        self,
        agent_repo:      AgentRepository,
        snapshot_repo:   SkillSnapshotRepository,
        execution_repo:  SkillExecutionRepository,
        user_model_repo: UserLLMModelRepository,
    ) -> None:
        """Initialise with injected repository instances."""
        self._agents     = agent_repo
        self._snapshots  = snapshot_repo
        self._executions = execution_repo
        self._user_models = user_model_repo

    async def start(
        self,
        conversation_id: str,
        snapshot_id:     str,
        agent_slot_map:  dict[str, str],
    ) -> tuple[str, str, dict]:
        """
        Prepare and create a new execution, ready for _stream_graph() to run.

        Enforces the concurrent-run guard before creating the execution record.
        Raises ValueError if a run is already active for this conversation.

        Args:
            conversation_id: UUID of the conversation.
            snapshot_id:     UUID of the execution snapshot to run.
            agent_slot_map:  Mapping of agent_key → llm_slot from the skill manifest.

        Returns:
            A tuple of (execution_id, snapshot_id, session_agent_config) where:
              - execution_id is a new UUID (also used as the LangGraph thread_id)
              - session_agent_config maps agent_key → {provider, model, slot}
        """
        # Guard: only one skill may run at a time per conversation
        running = await self._executions.get_running(conversation_id)
        if running:
            raise ValueError("A skill is already running in this conversation.")

        snapshot = await self._snapshots.get_by_id(snapshot_id)
        if not snapshot:
            raise ValueError(f"Snapshot '{snapshot_id}' not found.")

        session_config = await self.build_session_config(snapshot, agent_slot_map)
        execution_id   = str(uuid.uuid4())
        await self._executions.create(execution_id, snapshot_id)

        return execution_id, snapshot_id, session_config

    async def build_session_config(
        self,
        snapshot:       SkillSnapshot,
        agent_slot_map: dict[str, str],
    ) -> dict:
        """
        Resolve each agent's model_id UUID to provider+model strings.

        For each agent in the snapshot:
          - If model_id is set, look up (provider_name, model_name) from user_llm_models.
          - If model_id is None, both provider and model are None (smart_pick will handle it).

        Returns a dict mapping agent_key → {provider, model, slot} suitable for
        passing directly into AgentState.session_agent_config.

        Args:
            snapshot:       The execution snapshot with agents loaded.
            agent_slot_map: Mapping of agent_key → slot from the skill manifest.
        """
        config: dict = {}
        for ssa in snapshot.agents:
            agent = await self._agents.get_by_id(ssa.skill_agent_id)
            if not agent:
                continue

            provider: Optional[str] = None
            model:    Optional[str] = None

            if ssa.model_id:
                resolved = await self._user_models.get_by_id_resolved(ssa.model_id)
                if resolved:
                    provider, model = resolved

            config[agent.name] = {
                "provider": provider,
                "model":    model,
                "slot":     agent_slot_map.get(agent.name, "default"),
            }

        return config

    async def reset_for_retry(
        self,
        execution_id:   str,
        agent_slot_map: dict[str, str],
    ) -> dict:
        """
        Reset an execution's status to 'running' and rebuild its session config.

        Reads the current agent model_ids from the snapshot (which may have been
        updated since the original run) and returns a fresh session_agent_config
        for the retry.

        Raises ValueError if the execution or its snapshot is not found.

        Args:
            execution_id:   UUID of the execution to retry.
            agent_slot_map: Mapping of agent_key → slot from the skill manifest.

        Returns:
            A fresh session_agent_config dict.
        """
        execution = await self._executions.get_by_id(execution_id)
        if not execution:
            raise ValueError(f"Execution '{execution_id}' not found.")

        snapshot = await self._snapshots.get_by_id(execution.snapshot_id)
        if not snapshot:
            raise ValueError(f"Snapshot '{execution.snapshot_id}' not found.")

        fresh_config = await self.build_session_config(snapshot, agent_slot_map)
        await self._executions.reset_running(execution_id)
        return fresh_config

    async def complete(self, execution_id: str, status: str) -> None:
        """
        Mark an execution as finished with the given terminal status.

        Delegates directly to the repository. Called from _stream_graph() when
        the pipeline finishes or errors.

        Args:
            execution_id: UUID of the execution to complete.
            status:       Terminal status (ExecutionStatus constant).
        """
        await self._executions.complete(execution_id, status)

    async def get_by_id(self, execution_id: str) -> Optional[SkillExecution]:
        """
        Return an execution record by UUID, or None.

        Args:
            execution_id: UUID of the execution.
        """
        return await self._executions.get_by_id(execution_id)
