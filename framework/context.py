"""
ContextBuilder — assembles the human-turn content for an LLM call.

Each stage declares which state fields it needs (via SKILL.md  context: [...]
or the strategy's default list).  ContextBuilder formats those fields
consistently so stages don't need custom prompt-assembly code.

Adding a new state field:
  1. Add a handler to _FIELD_FORMATTERS below.
  2. Reference the field name in the relevant stage's  context:  list.
  No other code changes needed (Open/Closed Principle).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from state import AgentState

# ── Field formatters ──────────────────────────────────────────────────────────
# Each formatter receives the raw field value and returns a markdown string.
# Add new formatters here to support new context fields.

_FIELD_FORMATTERS: dict[str, Callable] = {
    "project_brief": lambda v: f"## Project Brief\n{v}",

    "document_draft": lambda v: f"## Document Under Review\n{v}",

    "document_version": lambda v: f"_Document version: {v}_",

    "discovery_questions": lambda qs: (
        "## Discovery Answers\n"
        + "\n".join(
            f"- **{q.question}**: {q.answer}"
            for q in qs if q.answer
        )
        if any(q.answer for q in qs) else ""
    ),

    "review_result": lambda r: (
        f"## Technical Review Result\n"
        f"**Status:** {'PASSED' if r.passed else 'FAILED'}\n\n"
        f"{r.feedback}\n\n"
        + (
            "**Critical issues:**\n" + "\n".join(f"- {i}" for i in r.critical_issues)
            if r.critical_issues else ""
        )
    ) if r else "",

    "approval_result": lambda r: (
        f"## Previous Approver Feedback\n{r.comments}\n\n"
        + (
            "**Required changes:**\n" + "\n".join(f"- {c}" for c in r.required_changes)
            if r.required_changes else ""
        )
    ) if r else "",

    "revision_count": lambda v: f"_Revision {v} of this document._" if v else "",
}


# ── Public API ────────────────────────────────────────────────────────────────

def build_context(fields: list[str], state: "AgentState") -> str:
    """
    Assemble a human-turn message from named state fields.

    Skips fields that are None, empty, or produce empty formatted output.
    Returns the sections joined by double newlines.
    """
    parts = []
    for field_name in fields:
        value = getattr(state, field_name, None)
        if value is None:
            continue
        formatter = _FIELD_FORMATTERS.get(field_name)
        if formatter:
            formatted = formatter(value)
        else:
            # Generic fallback: title-case heading + value
            heading = field_name.replace("_", " ").title()
            formatted = f"## {heading}\n{value}"
        if formatted and formatted.strip():
            parts.append(formatted.strip())
    return "\n\n".join(parts)
