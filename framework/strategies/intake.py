"""
IntakeStrategy — handles all session input types under one pipeline stage.

Used by: intake (the only stage that deals with file I/O and vision).

Two execution paths, both producing a project_brief + confirmation interrupt:
  brief    → pass through directly, no LLM call
  uploaded → extract brief via LLM (document text or Claude Vision for images),
             then pause for user confirmation

The source_type (brief / document / image) is an input-format detail
encapsulated here.  The rest of the pipeline never sees it.
"""

from __future__ import annotations

import base64
from pathlib import Path
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
    from state import AgentState

_MEDIA_TYPES = {
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".gif":  "image/gif",
    ".webp": "image/webp",
}


class _ImageResult(BaseModel):
    is_architecture_related: bool
    extracted_brief:         str
    rejection_reason:        str


def _extract_answers(raw) -> str:
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    return (raw or "").strip()


class IntakeStrategy(ExecutionStrategy):
    """
    Handles brief / document / image inputs and produces a project_brief.

    The stage config's 'agents' dict maps input types to agent file stems:
        agents:
          document: intake-document
          image:    intake-image
    """

    @property
    def name(self) -> str:
        return "intake"

    def build_node(
        self,
        stage: "StageConfig",
        skill: "LoadedSkill",
    ) -> Callable[["AgentState"], dict]:
        agent_map = stage.agents or {}

        def node(state: "AgentState") -> dict:
            from datetime import datetime, timezone
            base = {
                "current_stage": stage.id,
                "created_at":    datetime.now(timezone.utc).isoformat(),
            }

            # ── Plain text brief — pass through, or ask if empty ─────────────
            if state.source_type == "brief":
                brief = state.project_brief.strip()
                if not brief:
                    # User invoked the skill without a brief — ask for one
                    brief = _extract_answers(interrupt({
                        "__type":  "confirm_understanding",
                        "content": (
                            "Please describe the project or system you'd like to architect.\n\n"
                            "Include any relevant details — domain, purpose, expected scale, "
                            "tech stack preferences, or constraints you have in mind."
                        ),
                    }))
                return {
                    **base,
                    "project_brief": brief,
                    "messages": [
                        HumanMessage(content=f"Project brief:\n\n{brief}")
                    ],
                }

            # ── Uploaded content — extract brief then confirm ─────────────────
            brief, urec, rejection = _extract_from_upload(
                state, stage, agent_map
            )

            if rejection:
                return {
                    **base,
                    "current_stage": "invalid_input",
                    "usage_records": [urec],
                    "messages": [
                        HumanMessage(content=f"[{state.source_type.capitalize()} uploaded]"),
                        AIMessage(
                            name=stage.id,
                            content=(
                                f"Unable to use this upload for an architecture session.\n\n"
                                f"**Reason:** {rejection}\n\n"
                                "Please upload an architecture diagram, design document, "
                                "or a text description of the project."
                            ),
                        ),
                    ],
                }

            # Pause for user to verify and optionally correct
            correction = _extract_answers(interrupt({
                "__type":  "confirm_understanding",
                "content": brief,
            }))
            if correction:
                brief += f"\n\n**User correction:** {correction}"

            return {
                **base,
                "project_brief": brief,
                "usage_records": [urec],
                "messages": [
                    HumanMessage(content=f"[{state.source_type.capitalize()} uploaded]"),
                    AIMessage(name=stage.id, content=brief),
                ],
            }

        return node


def _extract_from_upload(
    state: "AgentState",
    stage: "StageConfig",
    agent_map: dict[str, str],
) -> tuple[str | None, dict, str]:
    """
    Extract a project brief from any uploaded content.
    Returns (brief_or_None, usage_record, rejection_reason).
    """
    if state.source_type == "image" and state.uploaded_image_path:
        return _extract_from_image(state, stage, agent_map)
    return _extract_from_document(state, stage, agent_map)


def _extract_from_image(
    state: "AgentState",
    stage: "StageConfig",
    agent_map: dict[str, str],
) -> tuple[str | None, dict, str]:
    image_path = state.uploaded_image_path
    suffix     = Path(image_path).suffix.lower()
    media_type = _MEDIA_TYPES.get(suffix, "image/jpeg")

    with open(image_path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode("utf-8")

    agent_key = agent_map.get("image", "intake-image")
    prompt    = state.flow_config.get(agent_key, "")

    llm = (
        get_llm_for_agent(stage.agent_key, state.session_agent_config)
        .with_structured_output(_ImageResult, include_raw=True)
    )
    raw    = invoke_with_retry(llm, [
        SystemMessage(content=prompt),
        HumanMessage(content=[
            {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}"}},
            {"type": "text",      "text": "Analyse this image and return your structured assessment."},
        ]),
    ])
    result: _ImageResult = raw["parsed"]
    urec = usage_record(
        stage.id,
        agent_model(stage.agent_key, state.session_agent_config),
        getattr(raw.get("raw"), "usage_metadata", None),
    )
    if not result.is_architecture_related:
        return None, urec, result.rejection_reason
    return result.extracted_brief, urec, ""


def _extract_from_document(
    state: "AgentState",
    stage: "StageConfig",
    agent_map: dict[str, str],
) -> tuple[str, dict, str]:
    agent_key = agent_map.get("document", "intake-document")
    prompt    = state.flow_config.get(agent_key, "")
    llm       = get_llm_for_agent(stage.agent_key, state.session_agent_config)

    response = invoke_with_retry(llm, [
        SystemMessage(content=prompt),
        HumanMessage(
            content=(
                f"Extract a structured Project Brief from this document.\n\n"
                f"---\n{state.raw_document_text}\n---"
            )
        ),
    ])
    urec = usage_record(
        stage.id,
        agent_model(stage.agent_key, state.session_agent_config),
        getattr(response, "usage_metadata", None),
    )
    return response.content, urec, ""


# Self-register on import
StrategyRegistry.register(IntakeStrategy())
