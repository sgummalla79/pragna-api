"""
SkillEngine — builds a LangGraph StateGraph from a LoadedSkill.

Responsibilities (S in SOLID):
  - Build one LangGraph node per stage (delegated to strategies)
  - Wire conditional edges from the routing declarations in SKILL.md
  - Compile the graph with the provided checkpointer

The engine does not know anything about:
  - Individual skill logic  (that's in skills/<id>/)
  - Execution patterns      (that's in strategies/)
  - Prompt content          (that's in the DB)

Extending the engine:
  - New execution patterns: add a strategy, self-register on import.
    The engine just looks up strategies by name — zero code changes here.
  - New routing patterns: extend _add_edges if needed; current implementation
    covers the linear / conditional / loop / intake / gate patterns.

Design note (D in SOLID):
  SkillEngine depends on StrategyRegistry (abstraction), not on concrete
  strategy classes.  Import order determines which strategies are available.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from langgraph.graph import END, StateGraph

from framework.loader import LoadedSkill
from framework.strategies.base import StrategyRegistry

# Import strategies so they self-register before the engine runs.
# New strategies: add an import here.
import framework.strategies.structured   # noqa: F401
import framework.strategies.interrupt    # noqa: F401
import framework.strategies.fanout       # noqa: F401
import framework.strategies.intake       # noqa: F401

from state import AgentState

if TYPE_CHECKING:
    from framework.schema import StageConfig

logger = logging.getLogger(__name__)


class SkillEngine:
    """
    Builds a compiled LangGraph StateGraph from a loaded skill definition.

    Every graph starts at the first pipeline stage (intake).
    Regular chat is handled outside LangGraph — no router or chat node needed.

    Usage:
        engine = SkillEngine()
        graph  = engine.build(skill, checkpointer=db.checkpointer)
    """

    def __init__(self, registry: StrategyRegistry | None = None) -> None:
        self._registry = registry or StrategyRegistry

    def build(self, skill: LoadedSkill, checkpointer) -> StateGraph:
        graph = StateGraph(AgentState)

        # ── Skill pipeline nodes ──────────────────────────────────────────────
        for stage_id, stage_cfg in skill.manifest.stages.items():
            strategy = self._registry.get(stage_cfg.execution)
            node_fn  = strategy.build_node(stage_cfg, skill)
            graph.add_node(stage_id, node_fn)
            logger.debug("Registered node '%s' with strategy '%s'", stage_id, stage_cfg.execution)

        # ── Entry point: always the first pipeline stage ──────────────────────
        first_stage = skill.manifest.pipeline[0]
        graph.set_entry_point(first_stage)

        self._add_pipeline_edges(graph, skill)

        compiled = graph.compile(checkpointer=checkpointer)
        logger.info("Graph compiled for skill '%s' — stages: %s", skill.manifest.id, skill.manifest.pipeline)
        return compiled

    def _add_pipeline_edges(self, graph: StateGraph, skill: LoadedSkill) -> None:
        pipeline = skill.manifest.pipeline
        stages   = skill.manifest.stages

        for i, stage_id in enumerate(pipeline):
            stage          = stages[stage_id]
            next_stage     = pipeline[i + 1] if i + 1 < len(pipeline) else None
            next_or_end    = next_stage if next_stage else END

            if stage.on_pass and stage.on_fail:
                # Binary conditional routing (e.g. review)
                self._add_pass_fail_edges(graph, stage)

            elif stage.on_approve and stage.on_reject:
                # Gate routing with optional halting (e.g. approval)
                self._add_gate_edges(graph, stage)

            elif stage.execution == "structured_interrupt":
                # Loop to self until complete, then advance
                assert next_stage, (
                    f"Stage '{stage_id}' uses structured_interrupt "
                    "but has no next stage in the pipeline."
                )
                self._add_loop_edges(graph, stage, next_stage)

            elif stage.execution == "intake":
                # Intake: invalid_input → END, otherwise advance
                assert next_stage, "intake must not be the last stage."
                self._add_intake_edges(graph, stage, next_stage)

            else:
                # Linear: unconditionally go to next stage (or END)
                graph.add_edge(stage_id, next_or_end)

    @staticmethod
    def _add_pass_fail_edges(graph: StateGraph, stage: "StageConfig") -> None:
        on_pass = stage.on_pass
        on_fail = stage.on_fail

        def route(state: AgentState) -> str:
            if state.review_result and state.review_result.passed:
                return on_pass
            return on_fail

        graph.add_conditional_edges(
            stage.id, route, {on_pass: on_pass, on_fail: on_fail}
        )

    @staticmethod
    def _add_gate_edges(graph: StateGraph, stage: "StageConfig") -> None:
        from config import MAX_REVISIONS
        on_approve   = stage.on_approve
        on_reject    = stage.on_reject
        max_revisions = stage.max_revisions or MAX_REVISIONS

        def route(state: AgentState) -> str:
            if state.approval_result and state.approval_result.status == "approved":
                return "complete"
            if state.revision_count >= max_revisions:
                return "halted"
            return on_reject

        graph.add_conditional_edges(
            stage.id,
            route,
            {"complete": END, "halted": END, on_reject: on_reject},
        )

    @staticmethod
    def _add_loop_edges(
        graph: StateGraph,
        stage: "StageConfig",
        next_stage: str,
    ) -> None:
        stage_id = stage.id

        def route(state: AgentState) -> str:
            return next_stage if state.discovery_complete else stage_id

        graph.add_conditional_edges(
            stage_id, route, {stage_id: stage_id, next_stage: next_stage}
        )

    @staticmethod
    def _add_intake_edges(
        graph: StateGraph,
        stage: "StageConfig",
        next_stage: str,
    ) -> None:
        def route(state: AgentState) -> str:
            return "end" if state.current_stage == "invalid_input" else next_stage

        graph.add_conditional_edges(
            stage.id, route, {next_stage: next_stage, "end": END}
        )


