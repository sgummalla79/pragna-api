"""
Unit tests for the _stream_graph SSE emitter in api/routes/executions.py.

The LangGraph graph is fully mocked — no DB, no LLM, no real pipeline.
Each test drives a specific event sequence and verifies the SSE output.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _parse_sse(raw: str) -> list[dict]:
    """Parse raw SSE string into list of event dicts."""
    events = []
    for line in raw.strip().split("\n"):
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return events


async def _collect(gen) -> str:
    """Consume an async generator and join all chunks."""
    chunks = []
    async for chunk in gen:
        chunks.append(chunk)
    return "".join(chunks)


def _mock_graph(events: list, final_state_values: dict, next_tasks=None):
    """
    Build a mock LangGraph graph that yields the given astream_events
    and returns the given state on aget_state.
    """
    async def _astream_events(*args, **kwargs):
        for event in events:
            yield event

    mock_state = MagicMock()
    mock_state.values = final_state_values
    mock_state.next   = next_tasks or []
    mock_state.tasks  = []

    graph = MagicMock()
    graph.astream_events = _astream_events
    graph.aget_state     = AsyncMock(return_value=mock_state)
    return graph


# ── Tests ─────────────────────────────────────────────────────────────────────

async def test_stage_start_emitted():
    from api.routes.executions import _stream_graph

    graph = _mock_graph(
        events=[{"event": "on_chain_start", "name": "intake", "data": {}}],
        final_state_values={"current_stage": "complete", "document_version": 0, "revision_count": 0},
    )

    raw    = await _collect(_stream_graph(graph, {}, {}, None, "exec-001", "conv-001"))
    events = _parse_sse(raw)

    stage_starts = [e for e in events if e["type"] == "stage_start"]
    assert len(stage_starts) == 1
    assert stage_starts[0]["stage"] == "intake"
    assert stage_starts[0]["label"] == "Intake Agent"


async def test_token_emitted_for_intake_node():
    """intake is the only stage that streams visible tokens."""
    from api.routes.executions import _stream_graph

    chunk = MagicMock()
    chunk.content = "Hello "

    graph = _mock_graph(
        events=[{
            "event": "on_chat_model_stream",
            "name":  "ChatAnthropic",
            "data":  {"chunk": chunk},
            "metadata": {"langgraph_node": "intake"},
        }],
        final_state_values={"current_stage": "complete", "document_version": 0, "revision_count": 0},
    )

    raw    = await _collect(_stream_graph(graph, {}, {}, None, "exec-001", "conv-001"))
    events = _parse_sse(raw)

    tokens = [e for e in events if e["type"] == "token"]
    assert len(tokens) == 1
    assert tokens[0]["content"] == "Hello "


async def test_token_suppressed_for_structured_output_nodes():
    """discovery, review, approval use structured output — tokens must be suppressed."""
    from api.routes.executions import _stream_graph

    for suppressed_node in ("discovery", "review", "approval"):
        chunk = MagicMock()
        chunk.content = '{"key": "value"}'

        graph = _mock_graph(
            events=[{
                "event": "on_chat_model_stream",
                "name":  "ChatAnthropic",
                "data":  {"chunk": chunk},
                "metadata": {"langgraph_node": suppressed_node},
            }],
            final_state_values={"current_stage": "complete", "document_version": 0, "revision_count": 0},
        )

        raw    = await _collect(_stream_graph(graph, {}, {}, None, "exec-001", "conv-001"))
        events = _parse_sse(raw)
        tokens = [e for e in events if e["type"] == "token"]
        assert len(tokens) == 0, f"Expected no tokens from {suppressed_node}, got {tokens}"


async def test_token_suppressed_for_research_node():
    from api.routes.executions import _stream_graph

    chunk = MagicMock()
    chunk.content = "Research output..."

    graph = _mock_graph(
        events=[{
            "event": "on_chat_model_stream",
            "name":  "ChatAnthropic",
            "data":  {"chunk": chunk},
            "metadata": {"langgraph_node": "research"},   # suppressed
        }],
        final_state_values={"current_stage": "complete", "document_version": 1, "revision_count": 0},
    )

    raw    = await _collect(_stream_graph(graph, {}, {}, None, "exec-001", "conv-001"))
    events = _parse_sse(raw)

    assert not any(e["type"] == "token" for e in events)


async def test_review_complete_emitted():
    from api.routes.executions import _stream_graph
    from state import ReviewResult

    rr = ReviewResult(passed=True, feedback="Excellent.", critical_issues=[])

    graph = _mock_graph(
        events=[{
            "event": "on_chain_end",
            "name":  "review",
            "data":  {"output": {"review_result": rr}},
        }],
        final_state_values={"current_stage": "complete", "document_version": 1, "revision_count": 0},
    )

    raw    = await _collect(_stream_graph(graph, {}, {}, None, "exec-001", "conv-001"))
    events = _parse_sse(raw)

    review_events = [e for e in events if e["type"] == "review_complete"]
    assert len(review_events) == 1
    assert review_events[0]["passed"] is True
    assert review_events[0]["feedback"] == "Excellent."


async def test_approval_complete_emitted():
    from api.routes.executions import _stream_graph
    from state import ApprovalResult

    ar = ApprovalResult(status="approved", comments="Ship it.")

    graph = _mock_graph(
        events=[{
            "event": "on_chain_end",
            "name":  "approval",
            "data":  {"output": {"approval_result": ar}},
        }],
        final_state_values={"current_stage": "complete", "document_version": 2, "revision_count": 0},
    )

    raw    = await _collect(_stream_graph(graph, {}, {}, None, "exec-001", "conv-001"))
    events = _parse_sse(raw)

    approval_events = [e for e in events if e["type"] == "approval_complete"]
    assert len(approval_events) == 1
    assert approval_events[0]["status"] == "approved"


async def test_done_emitted_on_completion():
    from api.routes.executions import _stream_graph

    graph = _mock_graph(
        events=[],
        final_state_values={"current_stage": "complete", "document_version": 3, "revision_count": 1},
    )

    raw    = await _collect(_stream_graph(graph, {}, {}, None, "exec-001", "conv-001"))
    events = _parse_sse(raw)

    done = [e for e in events if e["type"] == "done"]
    assert len(done) == 1
    assert done[0]["status"]           == "complete"
    assert done[0]["document_version"] == 3
    assert done[0]["revision_count"]   == 1


async def test_question_emitted_on_interrupt():
    from api.routes.executions import _stream_graph

    interrupt_task = MagicMock()
    interrupt_task.interrupts = [MagicMock(value=["What is the scale?", "Which cloud?"])]

    mock_state = MagicMock()
    mock_state.values = {"current_stage": "discovery", "document_version": 0, "revision_count": 0, "usage_records": []}
    mock_state.next   = ["discovery"]
    mock_state.tasks  = [interrupt_task]

    graph = MagicMock()

    async def _stream(*args, **kwargs):
        return
        yield  # make it an async generator

    graph.astream_events = _stream
    graph.aget_state     = AsyncMock(return_value=mock_state)

    raw    = await _collect(_stream_graph(graph, {}, {}, None, "exec-001", "conv-001"))
    events = _parse_sse(raw)

    questions = [e for e in events if e["type"] == "question"]
    assert len(questions) == 1
    assert "What is the scale?" in questions[0]["questions"]


async def test_confirm_understanding_emitted():
    from api.routes.executions import _stream_graph

    interrupt_task = MagicMock()
    interrupt_task.interrupts = [MagicMock(value={
        "__type": "confirm_understanding",
        "content": "I understand you want a microservices platform.",
    })]

    mock_state = MagicMock()
    mock_state.values = {"current_stage": "intake", "document_version": 0, "revision_count": 0, "usage_records": []}
    mock_state.next   = ["intake"]
    mock_state.tasks  = [interrupt_task]

    graph = MagicMock()

    async def _stream(*args, **kwargs):
        return
        yield

    graph.astream_events = _stream
    graph.aget_state     = AsyncMock(return_value=mock_state)

    raw    = await _collect(_stream_graph(graph, {}, {}, None, "exec-001", "conv-001"))
    events = _parse_sse(raw)

    confirms = [e for e in events if e["type"] == "confirm_understanding"]
    assert len(confirms) == 1
    assert "microservices" in confirms[0]["content"]


async def test_provider_error_emitted():
    from api.routes.executions import _stream_graph

    graph = MagicMock()

    async def _stream_raises(*args, **kwargs):
        raise RuntimeError("API key not configured for 'anthropic'. Open Settings → Providers.")
        yield  # async generator

    graph.astream_events = _stream_raises

    with patch("utils.user_context.connected_providers", return_value={"openai"}):
        raw = await _collect(_stream_graph(graph, {}, {}, None, "exec-001", "conv-001"))

    events = _parse_sse(raw)
    errors = [e for e in events if e["type"] == "provider_error"]
    assert len(errors) == 1
    assert errors[0]["can_smart_pick"] is True


async def test_generic_error_emitted():
    from api.routes.executions import _stream_graph

    graph = MagicMock()

    async def _stream_raises(*args, **kwargs):
        raise ValueError("Unexpected internal error")
        yield

    graph.astream_events = _stream_raises

    raw    = await _collect(_stream_graph(graph, {}, {}, None, "exec-001", "conv-001"))
    events = _parse_sse(raw)

    errors = [e for e in events if e["type"] == "error"]
    assert len(errors) == 1
    # Raw errors are converted to user-friendly messages by _friendly_error()
    assert "try again" in errors[0]["message"].lower()
