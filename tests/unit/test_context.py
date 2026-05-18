"""
Unit tests for framework/context.py — build_context field formatters.
"""

import pytest
from framework.context import build_context
from state import AgentState, DiscoveryQuestion, ReviewResult, ApprovalResult


def test_project_brief():
    s = AgentState(project_brief="Build a microservices platform")
    result = build_context(["project_brief"], s)
    assert "## Project Brief" in result
    assert "microservices" in result


def test_document_draft():
    s = AgentState(document_draft="# Architecture\n\nContent here")
    result = build_context(["document_draft"], s)
    assert "## Document Under Review" in result
    assert "Architecture" in result


def test_document_version():
    s = AgentState(document_version=3)
    result = build_context(["document_version"], s)
    assert "version: 3" in result


def test_discovery_questions_only_shows_answered():
    s = AgentState(discovery_questions=[
        DiscoveryQuestion(question="Scale?",   answer="100k users", satisfied=True),
        DiscoveryQuestion(question="Region?",  answer=None),                       # unanswered — excluded
        DiscoveryQuestion(question="Auth?",    answer="JWT",         satisfied=True),
    ])
    result = build_context(["discovery_questions"], s)
    assert "Scale?" in result
    assert "100k users" in result
    assert "Auth?" in result
    assert "Region?" not in result


def test_empty_discovery_questions_produces_no_output():
    s = AgentState(discovery_questions=[
        DiscoveryQuestion(question="Scale?", answer=None),
    ])
    result = build_context(["discovery_questions"], s)
    assert result == ""


def test_review_result_passed():
    s = AgentState(review_result=ReviewResult(passed=True, feedback="Excellent work"))
    result = build_context(["review_result"], s)
    assert "PASSED" in result
    assert "Excellent work" in result


def test_review_result_failed_with_issues():
    s = AgentState(review_result=ReviewResult(
        passed=False, feedback="Needs work", critical_issues=["Missing auth", "No error handling"]
    ))
    result = build_context(["review_result"], s)
    assert "FAILED" in result
    assert "Missing auth" in result


def test_approval_result():
    s = AgentState(approval_result=ApprovalResult(
        status="rejected", comments="Good start", required_changes=["Add monitoring"]
    ))
    result = build_context(["approval_result"], s)
    assert "Good start" in result
    assert "monitoring" in result


def test_none_fields_skipped():
    s = AgentState()
    result = build_context(["review_result", "approval_result"], s)
    assert result == ""


def test_multiple_fields_joined():
    s = AgentState(project_brief="brief text", document_version=2)
    result = build_context(["project_brief", "document_version"], s)
    assert "## Project Brief" in result
    assert "version: 2" in result
    assert "\n\n" in result   # sections separated by double newline
