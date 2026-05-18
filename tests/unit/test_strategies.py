"""
Unit tests for all four execution strategies.
LLM calls are fully mocked — no API keys needed.
"""

import pytest
from unittest.mock import patch, MagicMock, call
from pathlib import Path

from state import (
    AgentState, DiscoveryOutput, DiscoveryQuestion,
    ReviewResult, ApprovalResult,
)


# ── Shared helpers ────────────────────────────────────────────────────────────

def _fake_usage():
    return MagicMock(usage_metadata={"input_tokens": 10, "output_tokens": 20})


def _loaded_skill():
    """Minimal LoadedSkill stub for strategy tests."""
    from framework.schema import SkillManifest, StageConfig, FanoutBranch
    manifest = SkillManifest(
        id="test-skill", name="Test", description="", pipeline=["intake"],
        stages={
            "intake": StageConfig(
                id="intake", execution="intake", llm_slot="intake",
                agents={"document": "intake-document", "image": "intake-image"},
            ),
        },
    )
    skill = MagicMock()
    skill.manifest = manifest
    skill.agents = {
        "intake-document": "Extract a brief from this document.",
        "intake-image":    "Analyse this image.",
        "discovery":       "You are a discovery agent.",
        "review":          "You are a reviewer.",
        "approval":        "You are an approver.",
        "research-writer": "You are a writer.",
        "research-search": "You are a searcher.",
        "research-reasoning": "You are a reasoner.",
    }
    return skill


_DEFAULT_CFG = {"discovery": {"provider": "anthropic", "model": "claude-sonnet-4-6"}}
_DEFAULT_FLOW = {
    "intake-document": "Extract brief.", "intake-image": "Analyse image.",
    "discovery": "Discover.", "review": "Review.", "approval": "Approve.",
    "research-writer": "Write.", "research-search": "Search.",
    "research-reasoning": "Reason.",
}


def _base_state(**kwargs):
    kwargs.setdefault("session_agent_config", _DEFAULT_CFG)
    kwargs.setdefault("flow_config", _DEFAULT_FLOW)
    return AgentState(execution_id="exec-001", **kwargs)


# ── IntakeStrategy ────────────────────────────────────────────────────────────

class TestIntakeStrategy:

    def _stage(self):
        from framework.schema import StageConfig
        return StageConfig(
            id="intake", execution="intake", llm_slot="intake",
            agents={"document": "intake-document", "image": "intake-image"},
        )

    def test_brief_passthrough_no_llm(self):
        from framework.strategies.intake import IntakeStrategy
        strategy = IntakeStrategy()
        node = strategy.build_node(self._stage(), _loaded_skill())
        state = _base_state(source_type="brief", project_brief="Build a platform")

        result = node(state)

        assert result["current_stage"] == "intake"
        assert "messages" in result
        # No LLM called — no usage_records
        assert "usage_records" not in result or result.get("usage_records") == []

    def test_document_extraction_calls_llm(self):
        from framework.strategies.intake import IntakeStrategy
        strategy = IntakeStrategy()
        node = strategy.build_node(self._stage(), _loaded_skill())
        state = _base_state(source_type="document", raw_document_text="Some document content")

        mock_response = MagicMock()
        mock_response.content = "Extracted brief: Build a microservices platform"
        mock_response.usage_metadata = {"input_tokens": 50, "output_tokens": 30}

        with patch("framework.strategies.intake.get_llm_for_agent") as mock_llm_fn, \
             patch("framework.strategies.intake.invoke_with_retry") as mock_invoke, \
             patch("framework.strategies.intake.interrupt") as mock_interrupt:

            mock_llm_fn.return_value = MagicMock()
            mock_invoke.return_value = mock_response
            mock_interrupt.return_value = ""   # user sends no correction

            result = node(state)

        assert result["project_brief"] == "Extracted brief: Build a microservices platform"
        assert len(result["usage_records"]) == 1

    def test_image_rejection_sets_invalid_input(self):
        from framework.strategies.intake import IntakeStrategy, _ImageResult
        strategy = IntakeStrategy()
        node = strategy.build_node(self._stage(), _loaded_skill())

        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
            img_path = f.name

        state = _base_state(source_type="image", uploaded_image_path=img_path)

        rejection_result = _ImageResult(
            is_architecture_related=False,
            extracted_brief="",
            rejection_reason="This is a photo of a cat, not an architecture diagram.",
        )

        with patch("framework.strategies.intake.get_llm_for_agent") as mock_llm_fn, \
             patch("framework.strategies.intake.invoke_with_retry") as mock_invoke:

            mock_llm = MagicMock()
            mock_llm.with_structured_output.return_value = MagicMock()
            mock_llm_fn.return_value = mock_llm
            mock_invoke.return_value = {
                "parsed": rejection_result,
                "raw":    MagicMock(usage_metadata={"input_tokens": 20, "output_tokens": 5}),
            }

            result = node(state)

        os.unlink(img_path)
        assert result["current_stage"] == "invalid_input"


# ── InterruptStrategy ─────────────────────────────────────────────────────────

class TestInterruptStrategy:

    def _stage(self):
        from framework.schema import StageConfig
        return StageConfig(
            id="discovery", execution="structured_interrupt", llm_slot="discovery",
            agent="discovery", output_schema="DiscoveryOutput",
        )

    def test_asks_questions_when_not_complete(self):
        from framework.strategies.interrupt import InterruptStrategy
        strategy = InterruptStrategy()
        node = strategy.build_node(self._stage(), _loaded_skill())
        state = _base_state()

        discovery_output = DiscoveryOutput(
            next_questions=["What is the expected user load?", "Which cloud provider?"],
            updated_questions=[],
            discovery_complete=False,
            reasoning="Need more info",
        )

        with patch("framework.strategies.interrupt.get_llm_for_agent") as mock_llm_fn, \
             patch("framework.strategies.interrupt.invoke_with_retry") as mock_invoke, \
             patch("framework.strategies.interrupt.interrupt") as mock_interrupt:

            mock_llm = MagicMock()
            mock_llm.with_structured_output.return_value = MagicMock()
            mock_llm_fn.return_value = mock_llm
            mock_invoke.return_value = {
                "parsed": discovery_output,
                "raw":    MagicMock(usage_metadata={"input_tokens": 30, "output_tokens": 15}),
            }
            mock_interrupt.return_value = ["100k users", "AWS"]

            result = node(state)

        assert result["discovery_complete"] is False
        assert "messages" in result

    def test_completes_when_llm_signals_done(self):
        from framework.strategies.interrupt import InterruptStrategy
        strategy = InterruptStrategy()
        node = strategy.build_node(self._stage(), _loaded_skill())
        state = _base_state(discovery_questions=[
            DiscoveryQuestion(question="Scale?", answer="100k users", satisfied=True)
        ])

        discovery_output = DiscoveryOutput(
            next_questions=[],
            updated_questions=[DiscoveryQuestion(question="Scale?", answer="100k users", satisfied=True)],
            discovery_complete=True,
            reasoning="Have enough information",
        )

        with patch("framework.strategies.interrupt.get_llm_for_agent") as mock_llm_fn, \
             patch("framework.strategies.interrupt.invoke_with_retry") as mock_invoke:

            mock_llm = MagicMock()
            mock_llm.with_structured_output.return_value = MagicMock()
            mock_llm_fn.return_value = mock_llm
            mock_invoke.return_value = {
                "parsed": discovery_output,
                "raw":    MagicMock(usage_metadata={"input_tokens": 30, "output_tokens": 10}),
            }

            result = node(state)

        assert result["discovery_complete"] is True
        assert len(result["usage_records"]) == 1


# ── StructuredStrategy ────────────────────────────────────────────────────────

class TestStructuredStrategy:

    def _review_stage(self):
        from framework.schema import StageConfig
        return StageConfig(
            id="review", execution="structured", llm_slot="reviewer",
            agent="review", output_schema="ReviewResult",
            on_pass="approval", on_fail="research",
        )

    def _approval_stage(self):
        from framework.schema import StageConfig
        return StageConfig(
            id="approval", execution="structured", llm_slot="approver",
            agent="approval", output_schema="ApprovalResult",
            on_approve="complete", on_reject="research", max_revisions=5,
        )

    def test_review_pass(self):
        from framework.strategies.structured import StructuredStrategy
        strategy = StructuredStrategy()
        node = strategy.build_node(self._review_stage(), _loaded_skill())
        state = _base_state(document_draft="# Architecture\n\nContent.", document_version=1)

        review_result = ReviewResult(passed=True, feedback="Excellent architecture document.")

        with patch("framework.strategies.structured.get_llm_for_agent") as mock_llm_fn, \
             patch("framework.strategies.structured.invoke_with_retry") as mock_invoke:

            mock_llm = MagicMock()
            mock_llm.with_structured_output.return_value = MagicMock()
            mock_llm_fn.return_value = mock_llm
            mock_invoke.return_value = {
                "parsed": review_result,
                "raw":    MagicMock(usage_metadata={"input_tokens": 200, "output_tokens": 50}),
            }

            result = node(state)

        assert result["review_result"].passed is True
        assert "PASSED" in result["messages"][0].content
        assert len(result["usage_records"]) == 1

    def test_review_fail_with_critical_issues(self):
        from framework.strategies.structured import StructuredStrategy
        strategy = StructuredStrategy()
        node = strategy.build_node(self._review_stage(), _loaded_skill())
        state = _base_state(document_draft="# Draft", document_version=1)

        review_result = ReviewResult(
            passed=False,
            feedback="Missing security considerations.",
            critical_issues=["No authentication described", "No encryption at rest"],
        )

        with patch("framework.strategies.structured.get_llm_for_agent") as mock_llm_fn, \
             patch("framework.strategies.structured.invoke_with_retry") as mock_invoke:

            mock_llm = MagicMock()
            mock_llm.with_structured_output.return_value = MagicMock()
            mock_llm_fn.return_value = mock_llm
            mock_invoke.return_value = {
                "parsed": review_result,
                "raw":    MagicMock(usage_metadata={"input_tokens": 200, "output_tokens": 60}),
            }

            result = node(state)

        assert result["review_result"].passed is False
        assert len(result["review_result"].critical_issues) == 2
        assert "FAILED" in result["messages"][0].content

    def test_approval_approved(self):
        from framework.strategies.structured import StructuredStrategy
        strategy = StructuredStrategy()
        node = strategy.build_node(self._approval_stage(), _loaded_skill())
        state = _base_state(
            document_draft="# Final Architecture",
            document_version=2,
            review_result=ReviewResult(passed=True, feedback="Good"),
            revision_count=0,
        )

        approval_result = ApprovalResult(status="approved", comments="Approved for production.")

        with patch("framework.strategies.structured.get_llm_for_agent") as mock_llm_fn, \
             patch("framework.strategies.structured.invoke_with_retry") as mock_invoke:

            mock_llm = MagicMock()
            mock_llm.with_structured_output.return_value = MagicMock()
            mock_llm_fn.return_value = mock_llm
            mock_invoke.return_value = {
                "parsed": approval_result,
                "raw":    MagicMock(usage_metadata={"input_tokens": 300, "output_tokens": 40}),
            }

            result = node(state)

        assert result["approval_result"].status == "approved"
        assert result["revision_count"] == 0   # no increment on approval

    def test_approval_rejected_increments_revision(self):
        from framework.strategies.structured import StructuredStrategy
        strategy = StructuredStrategy()
        node = strategy.build_node(self._approval_stage(), _loaded_skill())
        state = _base_state(
            document_draft="# Draft",
            document_version=1,
            revision_count=1,
        )

        approval_result = ApprovalResult(
            status="rejected",
            comments="Needs more detail on scalability.",
            required_changes=["Add load balancer design", "Describe caching layer"],
        )

        with patch("framework.strategies.structured.get_llm_for_agent") as mock_llm_fn, \
             patch("framework.strategies.structured.invoke_with_retry") as mock_invoke:

            mock_llm = MagicMock()
            mock_llm.with_structured_output.return_value = MagicMock()
            mock_llm_fn.return_value = mock_llm
            mock_invoke.return_value = {
                "parsed": approval_result,
                "raw":    MagicMock(usage_metadata={"input_tokens": 300, "output_tokens": 80}),
            }

            result = node(state)

        assert result["approval_result"].status == "rejected"
        assert result["revision_count"] == 2   # 1 + 1


# ── FanoutStrategy ────────────────────────────────────────────────────────────

class TestFanoutStrategy:

    def _stage(self):
        from framework.schema import StageConfig, FanoutBranch
        return StageConfig(
            id="research", execution="fanout_merge", llm_slot="researcher_search",
            fanout=[
                FanoutBranch(llm_slot="researcher_search",    agent="research-search"),
                FanoutBranch(llm_slot="researcher_reasoning", agent="research-reasoning"),
            ],
            merge=FanoutBranch(llm_slot="researcher_writer", agent="research-writer"),
        )

    def test_initial_document_production(self):
        from framework.strategies.fanout import FanoutStrategy
        strategy = FanoutStrategy()
        node = strategy.build_node(self._stage(), _loaded_skill())
        state = _base_state(
            project_brief="Build a microservices platform",
            document_version=0,
            session_agent_config={
                "research-search":    {"provider": "perplexity", "model": "sonar-pro"},
                "research-reasoning": {"provider": "google",     "model": "gemini-2.5-pro"},
                "research-writer":    {"provider": "anthropic",  "model": "claude-sonnet-4-6"},
            },
        )

        branch_response = MagicMock()
        branch_response.content = "Research findings about microservices."
        branch_response.usage_metadata = {"input_tokens": 100, "output_tokens": 200}

        writer_response = MagicMock()
        writer_response.content = "# Architecture Recommendation Document\n\nFull content here."
        writer_response.usage_metadata = {"input_tokens": 500, "output_tokens": 1000}

        with patch("framework.strategies.fanout.get_llm_for_agent") as mock_llm_fn, \
             patch("framework.strategies.fanout.invoke_with_retry") as mock_invoke, \
             patch("utils.user_context.get_execution_keys", return_value={}), \
             patch("utils.user_context.get_execution_mode", return_value="direct"):

            mock_llm_fn.return_value = MagicMock()
            # First two calls are branches, third is writer
            mock_invoke.side_effect = [branch_response, branch_response, writer_response]

            result = node(state)

        assert result["document_version"] == 1
        assert "Architecture Recommendation Document" in result["document_draft"]
        assert result["review_result"] is None     # cleared for fresh review
        assert result["approval_result"] is None   # cleared
        assert len(result["usage_records"]) == 3   # 2 branches + 1 writer

    def test_revision_document_production(self):
        from framework.strategies.fanout import FanoutStrategy
        strategy = FanoutStrategy()
        node = strategy.build_node(self._stage(), _loaded_skill())
        state = _base_state(
            project_brief="Build a platform",
            document_draft="# v1 Document",
            document_version=1,   # already has a version → revision mode
            approval_result=ApprovalResult(
                status="rejected", comments="Add scalability section",
                required_changes=["Add load balancer"],
            ),
            session_agent_config={
                "research-search":    {"provider": "perplexity", "model": "sonar-pro"},
                "research-reasoning": {"provider": "google",     "model": "gemini-2.5-pro"},
                "research-writer":    {"provider": "anthropic",  "model": "claude-sonnet-4-6"},
            },
        )

        branch_response = MagicMock()
        branch_response.content = "Updated research."
        branch_response.usage_metadata = {"input_tokens": 100, "output_tokens": 150}

        writer_response = MagicMock()
        writer_response.content = "# Architecture v2\n\n## Revision Summary\n- Added load balancer"
        writer_response.usage_metadata = {"input_tokens": 600, "output_tokens": 1200}

        with patch("framework.strategies.fanout.get_llm_for_agent") as mock_llm_fn, \
             patch("framework.strategies.fanout.invoke_with_retry") as mock_invoke, \
             patch("utils.user_context.get_execution_keys", return_value={}), \
             patch("utils.user_context.get_execution_mode", return_value="direct"):

            mock_llm_fn.return_value = MagicMock()
            mock_invoke.side_effect = [branch_response, branch_response, writer_response]

            result = node(state)

        assert result["document_version"] == 2
        assert "Revision Summary" in result["document_draft"]
