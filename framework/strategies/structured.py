"""
StructuredStrategy — single LLM call with Pydantic structured output.

Used by: review, approval (any stage that calls one LLM and returns
a typed result with no interrupts).

The stage config controls:
  llm_slot  — which model to use
  agent     — which agents/*.md prompt to load
  schema    — Pydantic class name from state.py
  context   — which state fields to include in the human turn
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from langchain_core.messages import HumanMessage, SystemMessage

from framework.context import build_context
from framework.strategies.base import ExecutionStrategy, StrategyRegistry
from utils.llm_factory import get_llm_for_agent, agent_model
from utils.llm_retry import invoke_with_retry
from utils.pricing import usage_record

if TYPE_CHECKING:
    from framework.loader import LoadedSkill
    from framework.schema import StageConfig
    from state import AgentState

# Default context fields when the stage config does not specify them
_DEFAULT_CONTEXT = ["document_draft", "document_version", "discovery_questions"]


def _resolve_schema(name: str) -> type:
    """Resolve a schema class name to its Pydantic type from state.py."""
    import state as state_module
    cls = getattr(state_module, name, None)
    if cls is None:
        raise ValueError(
            f"Schema '{name}' not found in state.py. "
            "Add the Pydantic model there or check for a typo."
        )
    return cls


class StructuredStrategy(ExecutionStrategy):
    """Single LLM call → structured Pydantic output → state update."""

    @property
    def name(self) -> str:
        return "structured"

    def build_node(
        self,
        stage: "StageConfig",
        skill: "LoadedSkill",
    ) -> Callable[["AgentState"], dict]:
        if not stage.output_schema:
            raise ValueError(
                f"Stage '{stage.id}' uses execution=structured "
                "but no schema is defined in SKILL.md"
            )
        schema_cls    = _resolve_schema(stage.output_schema)
        context_fields = stage.context or _DEFAULT_CONTEXT

        def node(state: "AgentState") -> dict:
            llm = (
                get_llm_for_agent(stage.agent_key, state.session_agent_config)
                .with_structured_output(schema_cls, include_raw=True)
            )
            system_prompt = state.flow_config.get(stage.agent_key, "")
            human_content = build_context(context_fields, state)

            raw    = invoke_with_retry(llm, [
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_content),
            ])
            result = raw["parsed"]
            if result is None:
                parsing_error = raw.get("parsing_error")
                raise ValueError(
                    f"The model returned a response that could not be parsed. "
                    f"Please try again. (detail: {parsing_error})"
                )
            urec    = usage_record(
                stage.id,
                agent_model(stage.agent_key, state.session_agent_config),
                getattr(raw.get("raw"), "usage_metadata", None),
            )
            return _build_state_update(stage, state, result, urec)

        return node


def _build_state_update(
    stage: "StageConfig",
    state: "AgentState",
    result,
    urec: dict,
) -> dict:
    """Map a structured result to a state update dict based on the schema type."""
    from state import ReviewResult, ApprovalResult
    from langchain_core.messages import AIMessage
    from config import MAX_REVISIONS

    if isinstance(result, ReviewResult):
        status = "PASSED" if result.passed else "FAILED"
        return {
            "current_stage": stage.id,
            "review_result": result,
            "usage_records": [urec],
            "messages": [
                AIMessage(
                    name=stage.id,
                    content=f"[{stage.id.title()}] Review {status}. {result.feedback}",
                )
            ],
        }

    if isinstance(result, ApprovalResult):
        new_revision = state.revision_count + (
            1 if result.status == "rejected" else 0
        )
        return {
            "current_stage":  stage.id,
            "approval_result": result,
            "revision_count":  new_revision,
            "usage_records":  [urec],
            "messages": [
                AIMessage(
                    name=stage.id,
                    content=f"[{stage.id.title()}] Decision: {result.status.upper()}. {result.comments}",
                )
            ],
        }

    # Generic fallback — callers can override via subclassing
    return {
        "current_stage": stage.id,
        "usage_records": [urec],
    }


# Self-register on import
StrategyRegistry.register(StructuredStrategy())
