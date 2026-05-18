"""
InterruptStrategy — structured LLM call + LangGraph interrupt loop.

Used by: discovery (any stage that asks the user questions and loops
until a completion condition is met).

Flow per invocation:
  1. Call LLM with structured output
  2. If complete → return final state update
  3. If not complete → interrupt(questions), resume with answers, update state
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.types import interrupt
from pydantic import BaseModel

from framework.strategies.base import ExecutionStrategy, StrategyRegistry
from utils.llm_factory import get_llm_for_agent, agent_model
from utils.llm_retry import invoke_with_retry
from utils.pricing import usage_record

if TYPE_CHECKING:
    from framework.loader import LoadedSkill
    from framework.schema import StageConfig
    from state import AgentState, DiscoveryQuestion

_WINDOW = 30  # messages to include in context


def _resolve_schema(name: str) -> type:
    import state as state_module
    cls = getattr(state_module, name, None)
    if cls is None:
        raise ValueError(f"Schema '{name}' not found in state.py.")
    return cls


def _extract_answers(raw) -> list[str]:
    """Normalize the interrupt resume value to a list of strings."""
    if isinstance(raw, list):
        return [str(a).strip() for a in raw]
    return [str(raw).strip()]


class InterruptStrategy(ExecutionStrategy):
    """
    Structured LLM call with interrupt loop.

    The stage continues calling itself (via LangGraph's interrupt mechanism)
    until the LLM signals completion or the question cap is reached.
    """

    @property
    def name(self) -> str:
        return "structured_interrupt"

    def build_node(
        self,
        stage: "StageConfig",
        skill: "LoadedSkill",
    ) -> Callable[["AgentState"], dict]:
        if not stage.output_schema:
            raise ValueError(
                f"Stage '{stage.id}' uses execution=structured_interrupt "
                "but no schema is defined in SKILL.md"
            )
        schema_cls = _resolve_schema(stage.output_schema)

        def node(state: "AgentState") -> dict:
            from config import MAX_DISCOVERY_QUESTIONS

            # Windowed message history — Anthropic requires at least one
            # non-system message; always ensure list ends with HumanMessage
            windowed = list(
                state.messages[-_WINDOW:]
                if len(state.messages) > _WINDOW
                else state.messages
            )
            if not windowed or isinstance(windowed[-1], AIMessage):
                windowed.append(
                    HumanMessage(content="Please begin the discovery session.")
                )

            llm = (
                get_llm_for_agent(stage.agent_key, state.session_agent_config)
                .with_structured_output(schema_cls, include_raw=True)
            )
            system_prompt = state.flow_config.get(stage.agent_key, "")

            raw    = invoke_with_retry(llm, [SystemMessage(content=system_prompt), *windowed])
            result = raw["parsed"]
            if result is None:
                parsing_error = raw.get("parsing_error")
                raise ValueError(
                    f"The model returned a response that could not be parsed. "
                    f"Please try again. (detail: {parsing_error})"
                )
            urec   = usage_record(
                stage.id,
                agent_model(stage.agent_key, state.session_agent_config),
                getattr(raw.get("raw"), "usage_metadata", None),
            )

            # Check completion conditions
            answered_count = sum(1 for q in result.updated_questions if q.answer)
            cap_reached    = answered_count >= MAX_DISCOVERY_QUESTIONS

            if result.discovery_complete or cap_reached or not result.next_questions:
                return {
                    "current_stage":       stage.id,
                    "discovery_questions": result.updated_questions,
                    "discovery_complete":  True,
                    "usage_records":       [urec],
                }

            # Pause for user answers
            answers = _extract_answers(interrupt(result.next_questions))

            # Reconcile answers back into question objects
            answered_map = dict(zip(result.next_questions, answers))
            for q in result.updated_questions:
                if q.question in answered_map and not q.answer:
                    q.answer    = answered_map[q.question]
                    q.satisfied = bool(q.answer.strip())

            qa_lines = "\n".join(
                f"Q{i+1}: {q}\nA{i+1}: {a}"
                for i, (q, a) in enumerate(zip(result.next_questions, answers))
            )

            return {
                "current_stage":       stage.id,
                "discovery_questions": result.updated_questions,
                "discovery_complete":  False,
                "usage_records":       [urec],
                "messages": [
                    AIMessage(
                        name=stage.id,
                        content="\n".join(
                            f"{i+1}. {q}"
                            for i, q in enumerate(result.next_questions)
                        ),
                    ),
                    HumanMessage(content=qa_lines),
                ],
            }

        return node


# Self-register on import
StrategyRegistry.register(InterruptStrategy())
