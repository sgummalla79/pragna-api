"""
FanoutStrategy — parallel LLM calls that merge into a single writer call.

Used by: research (run N independent research agents concurrently,
then synthesise their outputs into a document).

The stage config drives everything:
  fanout[] — parallel branches (each has llm_slot + agent)
  merge    — the writer that receives all branch outputs
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING, Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from framework.context import build_context
from framework.strategies.base import ExecutionStrategy, StrategyRegistry
from utils.llm_factory import get_llm_for_agent, agent_model
from utils.llm_retry import invoke_with_retry
from utils.pricing import usage_record

if TYPE_CHECKING:
    from framework.loader import LoadedSkill
    from framework.schema import FanoutBranch, StageConfig
    from state import AgentState

_RESEARCH_CONTEXT = ["project_brief", "discovery_questions"]
_WRITER_INIT_CONTEXT = ["project_brief", "discovery_questions"]
_WRITER_REVISION_CONTEXT = [
    "document_draft", "document_version",
    "approval_result", "review_result",
]


class FanoutStrategy(ExecutionStrategy):
    """
    Run N parallel LLM calls, collect their outputs, feed all into a merge writer.

    Thread safety: each branch call is independent.  State is read-only inside
    the node function; the only mutable object is the local `results` list which
    is assembled before any state update is returned.
    """

    @property
    def name(self) -> str:
        return "fanout_merge"

    def build_node(
        self,
        stage: "StageConfig",
        skill: "LoadedSkill",
    ) -> Callable[["AgentState"], dict]:
        if not stage.fanout or not stage.merge:
            raise ValueError(
                f"Stage '{stage.id}' uses execution=fanout_merge "
                "but is missing 'fanout' or 'merge' config in SKILL.md"
            )

        def node(state: "AgentState") -> dict:
            research_context = build_context(_RESEARCH_CONTEXT, state)

            # Look up the user's API keys from the session store — a plain thread-safe dict
            # keyed by session_id that _stream_graph populates before streaming starts.
            # This is the only mechanism guaranteed to survive LangGraph's internal
            # asyncio.create_task(context=...) boundaries and nested ThreadPoolExecutor threads.
            from utils.user_context import get_execution_keys, get_execution_mode, get_execution_active_models, set_user_context, set_active_models
            _eid             = state.execution_id
            _captured_keys   = get_execution_keys(_eid)
            _captured_mode   = get_execution_mode(_eid)
            _captured_models = get_execution_active_models(_eid)

            # ── Step 1: run all branches in parallel ──────────────────────────
            branch_outputs: list[tuple[str, str, dict]] = []  # (label, text, urec)

            def run_branch(branch: "FanoutBranch") -> tuple[str, str, dict]:
                # Re-establish user context at the start of each thread so get_user_key works.
                if _captured_keys:
                    set_user_context(_captured_keys, _captured_mode)
                if _captured_models:
                    set_active_models(_captured_models)
                llm      = get_llm_for_agent(branch.agent, state.session_agent_config)
                prompt   = state.flow_config.get(branch.agent, "")
                response = invoke_with_retry(llm, [
                    SystemMessage(content=prompt),
                    HumanMessage(content=research_context),
                ])
                urec = usage_record(
                    stage.id,
                    agent_model(branch.agent, state.session_agent_config),
                    getattr(response, "usage_metadata", None),
                )
                return branch.agent, response.content, urec

            with ThreadPoolExecutor(max_workers=len(stage.fanout)) as pool:
                futures = {pool.submit(run_branch, b): b for b in stage.fanout}
                for future in as_completed(futures):
                    label, text, urec = future.result()
                    branch_outputs.append((label, text, urec))

            # ── Step 2: merge writer synthesises all branch outputs ───────────
            merge      = stage.merge
            merge_llm  = get_llm_for_agent(merge.agent, state.session_agent_config)
            merge_prompt = state.flow_config.get(merge.agent, "")

            research_block = "\n\n---\n\n".join(
                f"## {label.replace('-', ' ').title()}\n\n{text}"
                for label, text, _ in branch_outputs
            )

            if state.document_version == 0:
                writer_context = build_context(_WRITER_INIT_CONTEXT, state)
                user_prompt    = (
                    f"{writer_context}\n\n"
                    f"## Research Outputs\n{research_block}\n\n"
                    "Using the research above, produce the complete Architecture "
                    "Recommendation Document."
                )
            else:
                writer_context = build_context(_WRITER_REVISION_CONTEXT, state)
                user_prompt    = (
                    f"{writer_context}\n\n"
                    f"## Refreshed Research\n{research_block}\n\n"
                    "Instructions:\n"
                    "1. Add ## Revision Summary listing every change.\n"
                    "2. Resolve all flagged items with [RESOLVED: <comment>].\n"
                    "3. Do not rewrite sections that were not flagged.\n"
                    "4. Output the complete updated document."
                )

            merge_response = invoke_with_retry(merge_llm, [
                SystemMessage(content=merge_prompt),
                HumanMessage(content=user_prompt),
            ])
            merge_urec = usage_record(
                stage.id,
                agent_model(merge.agent, state.session_agent_config),
                getattr(merge_response, "usage_metadata", None),
            )

            new_version = state.document_version + 1
            all_urecs   = [urec for _, _, urec in branch_outputs] + [merge_urec]

            return {
                "current_stage":    stage.id,
                "document_draft":   merge_response.content,
                "document_version": new_version,
                "review_result":    None,
                "approval_result":  None,
                "usage_records":    all_urecs,
                "messages": [
                    AIMessage(
                        name=stage.id,
                        content=(
                            f"[{stage.id.title()}] Document v{new_version} produced. "
                            f"{len(stage.fanout)} parallel research branches → writer."
                        ),
                    )
                ],
            }

        return node


# Self-register on import
StrategyRegistry.register(FanoutStrategy())
