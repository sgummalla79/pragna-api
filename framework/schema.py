"""
Skill manifest schema — typed representation of a parsed SKILL.md.

All skill definitions are validated against these Pydantic models at load time.
Type errors surface immediately on startup, not at runtime during a session.

Design note (O in SOLID):
  Adding a new execution strategy requires no changes here — strategies
  register themselves in framework/strategies/base.py.  The Literal for
  `execution` is kept permissive (str) so new strategies don't force a
  schema change; the engine validates against the strategy registry instead.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field, model_validator


class FanoutBranch(BaseModel):
    """One parallel branch inside a fanout_merge stage."""

    llm_slot: str = Field(..., description="Agent config slot for this branch.")
    agent:    str = Field(..., description="Stem of agents/<agent>.md — the prompt file.")


class StageConfig(BaseModel):
    """
    Complete, validated configuration for one pipeline stage.

    Routing semantics:
      on_pass / on_fail    — used by stages with a binary pass/fail result (review)
      on_approve / on_reject — used by gate stages (approval)
      max_revisions        — halt after N rejections instead of looping forever
      Stages with none of the above route linearly to the next stage in the pipeline.
    """

    id:            str
    execution:     str   = Field(..., description="Execution strategy name.")
    llm_slot:      str   = Field(..., description="Key in session_agent_config.")
    agent:         Optional[str]            = None
    output_schema:        Optional[str]            = None
    context:       Optional[list[str]]      = None
    interrupt:     Optional[str]            = None
    on_pass:       Optional[str]            = None
    on_fail:       Optional[str]            = None
    on_approve:    Optional[str]            = None
    on_reject:     Optional[str]            = None
    max_revisions: Optional[int]            = None
    # Fan-out branches (fanout_merge strategy only)
    fanout:        Optional[list[FanoutBranch]] = None
    merge:         Optional[FanoutBranch]       = None
    # Intake-specific: multiple agents for different input types
    agents:        Optional[dict[str, str]] = None

    @property
    def agent_key(self) -> str:
        """
        Key used in state.flow_config and as the agent_key in the DB.
        Defaults to the stage id when no explicit agent name is given.
        """
        return self.agent or self.id

    @model_validator(mode="after")
    def fanout_requires_merge(self) -> "StageConfig":
        if self.fanout and not self.merge:
            raise ValueError(
                f"Stage '{self.id}': execution=fanout_merge requires a 'merge' config."
            )
        return self

    @model_validator(mode="after")
    def routing_symmetry(self) -> "StageConfig":
        if bool(self.on_pass) ^ bool(self.on_fail):
            raise ValueError(
                f"Stage '{self.id}': 'on_pass' and 'on_fail' must both be set or both omitted."
            )
        if bool(self.on_approve) ^ bool(self.on_reject):
            raise ValueError(
                f"Stage '{self.id}': 'on_approve' and 'on_reject' must both be set or both omitted."
            )
        return self


class SkillManifest(BaseModel):
    """
    Parsed, validated representation of a SKILL.md file.

    This is the single source of truth for a skill's identity and pipeline
    structure.  Prompt content lives separately in agents/*.md so it can be
    versioned independently in the database.
    """

    id:           str
    name:         str
    description:  str
    icon:         str        = "⚡"
    version:      int        = 1
    pipeline:     list[str]              = Field(..., min_length=1)
    stages:       dict[str, StageConfig] = Field(default_factory=dict)
    agent_labels: dict[str, str]         = Field(default_factory=dict)

    @property
    def ordered_agent_keys(self) -> list[str]:
        """All agent keys in pipeline order — used for ordered UI display."""
        keys: list[str] = []
        for stage_id in self.pipeline:
            stage = self.stages[stage_id]
            if stage.execution == "fanout_merge":
                for branch in (stage.fanout or []):
                    if branch.agent not in keys:
                        keys.append(branch.agent)
                if stage.merge and stage.merge.agent not in keys:
                    keys.append(stage.merge.agent)
            elif stage.execution == "intake":
                for key in (stage.agents or {}).values():
                    if key not in keys:
                        keys.append(key)
            else:
                key = stage.agent_key
                if key not in keys:
                    keys.append(key)
        return keys

    @property
    def agent_slot_map(self) -> dict[str, str]:
        """Maps agent_key → llm_slot for all agents in this skill."""
        slot_map: dict[str, str] = {}
        for stage in self.stages.values():
            if stage.execution == "fanout_merge":
                for branch in (stage.fanout or []):
                    slot_map[branch.agent] = branch.llm_slot
                if stage.merge:
                    slot_map[stage.merge.agent] = stage.merge.llm_slot
            elif stage.agents:
                for key in stage.agents.values():
                    slot_map[key] = stage.llm_slot
            else:
                slot_map[stage.agent_key] = stage.llm_slot
        return slot_map

    @model_validator(mode="after")
    def pipeline_stages_consistent(self) -> "SkillManifest":
        missing = [s for s in self.pipeline if s not in self.stages]
        if missing:
            raise ValueError(
                f"Pipeline references stages not defined in SKILL.md: {missing}"
            )
        return self
