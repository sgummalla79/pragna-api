"""
Unit tests for AgentState — field defaults, reducer behaviour, structured outputs.
"""

import pytest
from langchain_core.messages import HumanMessage, AIMessage
from state import AgentState, DiscoveryQuestion, ReviewResult, ApprovalResult


def test_default_fields():
    s = AgentState()
    assert s.execution_id          == ""
    assert s.conversation_id       == ""
    assert s.conversation_skill_id == ""
    assert s.current_stage         == "intake"
    assert s.revision_count        == 0
    assert s.source_type           == "brief"
    assert s.discovery_complete    is False
    assert s.document_version      == 0
    assert s.review_result         is None
    assert s.approval_result       is None
    assert s.messages              == []
    assert s.usage_records         == []
    assert s.flow_config           == {}
    assert s.session_agent_config  == {}


def test_messages_append_via_reducer():
    s = AgentState()
    m1 = HumanMessage(content="hello")
    m2 = AIMessage(content="world")
    # Simulate LangGraph reducer: new state is a merge of old + update
    merged = AgentState(**{**s.model_dump(), "messages": [m1]})
    assert len(merged.messages) == 1
    merged2 = AgentState(**{**merged.model_dump(), "messages": [m1, m2]})
    assert len(merged2.messages) == 2


def test_usage_records_append_via_reducer():
    s = AgentState()
    rec = {"agent": "research", "model": "claude-sonnet-4-6", "cost_usd": 0.001}
    merged = AgentState(**{**s.model_dump(), "usage_records": [rec]})
    assert len(merged.usage_records) == 1
    assert merged.usage_records[0]["agent"] == "research"


def test_discovery_question_model():
    q = DiscoveryQuestion(question="What is the scale?")
    assert q.answer    is None
    assert q.satisfied is False

    q2 = DiscoveryQuestion(question="Scale?", answer="100k users", satisfied=True)
    assert q2.satisfied is True


def test_review_result_model():
    rr = ReviewResult(passed=True, feedback="Looks great", critical_issues=[])
    assert rr.passed is True
    assert rr.critical_issues == []

    rr2 = ReviewResult(passed=False, feedback="Issues found", critical_issues=["Missing auth"])
    assert len(rr2.critical_issues) == 1


def test_approval_result_model():
    ar = ApprovalResult(status="approved", comments="All good")
    assert ar.status == "approved"
    assert ar.required_changes == []

    ar2 = ApprovalResult(status="rejected", comments="Fix auth", required_changes=["Add JWT"])
    assert ar2.status == "rejected"
    assert len(ar2.required_changes) == 1


def test_session_agent_config_structure():
    cfg = {
        "discovery":       {"provider": "anthropic", "model": "claude-sonnet-4-6"},
        "research-writer": {"provider": "anthropic", "model": "claude-sonnet-4-6"},
    }
    s = AgentState(session_agent_config=cfg)
    assert s.session_agent_config["discovery"]["provider"] == "anthropic"
