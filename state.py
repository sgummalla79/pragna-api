from __future__ import annotations

import operator
from typing import Annotated, Literal, Optional

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, ConfigDict, Field


# ── Discovery ─────────────────────────────────────────────────────────────────

class DiscoveryQuestion(BaseModel):
    question:  str
    answer:    Optional[str] = None
    satisfied: bool = False


class DiscoveryOutput(BaseModel):
    next_questions:     list[str]             = Field(default_factory=list)
    updated_questions:  list[DiscoveryQuestion] = Field(default_factory=list)
    discovery_complete: bool                  = False
    reasoning:          str                   = ""


# ── Review ────────────────────────────────────────────────────────────────────

class ReviewResult(BaseModel):
    passed:          bool
    feedback:        str
    critical_issues: list[str] = Field(default_factory=list)


# ── Approval ──────────────────────────────────────────────────────────────────

class ApprovalResult(BaseModel):
    status:           Literal["approved", "rejected"]
    comments:         str
    required_changes: list[str] = Field(default_factory=list)


# ── Main graph state ──────────────────────────────────────────────────────────

class AgentState(BaseModel):
    # ── Execution identity ────────────────────────────────────────────────────
    execution_id:          str = ""   # = conversation_skill_executions.id = LangGraph thread_id
    conversation_id:       str = ""   # for mid-execution model failure handling
    conversation_skill_id: str = ""   # FK to snapshot — for model updates on retry

    # ── Stage tracking ────────────────────────────────────────────────────────
    current_stage: Literal[
        "intake", "discovery", "research", "review", "approval",
        "complete", "halted", "invalid_input",
    ] = "intake"
    revision_count: int = 0

    # ── Stage 1 — Intake ─────────────────────────────────────────────────────
    source_type:         Literal["brief", "document", "image"] = "brief"
    uploaded_file_path:  str = ""
    uploaded_image_path: str = ""
    raw_document_text:   str = ""
    project_brief:       str = ""

    # ── Stage 2 — Discovery ──────────────────────────────────────────────────
    discovery_questions: list[DiscoveryQuestion] = Field(default_factory=list)
    discovery_complete:  bool = False

    # ── Stage 3 — Research ───────────────────────────────────────────────────
    document_draft:   str = ""
    document_version: int = 0

    # ── Stage 4 — Review ─────────────────────────────────────────────────────
    review_result: Optional[ReviewResult] = None

    # ── Stage 5 — Approval ───────────────────────────────────────────────────
    approval_result: Optional[ApprovalResult] = None

    # ── Pipeline config (frozen at execution start, never mutated by nodes) ──
    flow_id:              str  = ""
    flow_config:          dict = Field(default_factory=dict)  # {agent_key: prompt_content}
    session_agent_config: dict = Field(default_factory=dict)  # {agent_key: {provider, model}}

    # ── Accumulators (append-only via LangGraph reducers) ─────────────────────
    messages:      Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)
    usage_records: Annotated[list[dict], operator.add]        = Field(default_factory=list)

    model_config = ConfigDict(arbitrary_types_allowed=True)
