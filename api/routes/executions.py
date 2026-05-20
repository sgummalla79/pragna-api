"""
Execution routes — skill pipeline invocation and control.

POST /api/conversations/{id}/skills/{sid}/invoke  — start pipeline (SSE)
POST /api/executions/{execution_id}/reply         — resume interrupt (SSE)
POST /api/executions/{execution_id}/retry         — retry after model update (SSE)
"""

import asyncio
import json
import logging
import uuid
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from langgraph.types import Command
from pydantic import BaseModel

from state import AgentState
from utils.auth import AuthUser, get_current_user
from framework.defaults import available_providers, smart_pick


def _pick_title_model(agent_cfg: dict | None) -> tuple[str, str]:
    from utils.user_context import _user_keys
    if agent_cfg:
        p = agent_cfg.get("provider")
        m = agent_cfg.get("model")
        if p and m:
            return p, m
    from utils.user_context import get_active_models
    connected = available_providers(_user_keys.get() or {})
    try:
        pick = smart_pick("default", connected, get_active_models())
        return pick["provider"], pick["model"]
    except ValueError:
        return "", ""

log    = logging.getLogger(__name__)
router = APIRouter()

STAGE_LABELS = {
    "intake":    "Intake Agent",
    "discovery": "Discovery Agent",
    "research":  "Research Agent",
    "review":    "Review Agent",
    "approval":  "Approver Gate",
}


def _sse(event_type: str, payload: dict) -> str:
    return f"data: {json.dumps({'type': event_type, **payload})}\n\n"


def _get(obj, key, default=None):
    if obj is None:
        return default
    if hasattr(obj, key):
        return getattr(obj, key)
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default


# ── Request models ────────────────────────────────────────────────────────────

class InvokeRequest(BaseModel):
    brief:               Optional[str] = ""
    original_message:    Optional[str] = ""
    source_type:         Optional[str] = "brief"
    uploaded_file_path:  Optional[str] = ""
    uploaded_image_path: Optional[str] = ""
    raw_document_text:   Optional[str] = ""


class ReplyRequest(BaseModel):
    answers: object   # str | list[str]


# ── User-friendly error formatter ────────────────────────────────────────────

def _friendly_error(msg: str) -> str:
    low = msg.lower()
    if "api key" in low or "authentication" in low or "unauthorized" in low or "invalid_api_key" in low:
        return "Invalid or missing API key. Please check your credentials in Settings → Providers."
    if "quota" in low or "rate limit" in low or "too many requests" in low:
        return "Rate limit reached. Please wait a moment and try again."
    if "timeout" in low or "timed out" in low:
        return "The request timed out. Please try again."
    if "context" in low and ("length" in low or "window" in low or "limit" in low):
        return "The conversation is too long for the selected model. Please start a new session."
    if "connection" in low or "network" in low or "connect" in low:
        return "A network error occurred. Please check your connection and try again."
    if "could not be parsed" in low or "parsing_error" in low:
        return "The model's response was not in the expected format. Please try again."
    if "no models are activated" in low or "go to settings" in low or "activate at least one model" in low:
        return msg
    return "Something went wrong while processing your request. Please try again."


# ── Core SSE emitter ──────────────────────────────────────────────────────────

async def _stream_graph(
    graph,
    input_,
    config:          dict,
    db,
    execution_id:    str,
    conversation_id: str,
) -> AsyncGenerator[str, None]:
    from utils.user_context import _user_keys, get_anthropic_mode, get_active_models, register_execution_keys, unregister_execution_keys

    live_keys = _user_keys.get()
    if live_keys and execution_id:
        register_execution_keys(execution_id, live_keys, get_anthropic_mode(), get_active_models())

    config = {**config, "recursion_limit": 100}

    _stage_buffer: dict[str, str] = {}
    _current_stage: list[str]     = [None]
    _latest_artifact_id: list     = [None]

    async def _save_msg(role: str, content: str, message_type: str = "chat") -> None:
        if not db or not content.strip():
            return
        try:
            await db.messages.create(
                conversation_id = conversation_id,
                execution_id    = execution_id,
                role            = role,
                content         = content.strip(),
                message_type    = message_type,
                message_state   = "visible",
            )
        except Exception as exc:
            log.warning("Failed to save message: %s", exc)

    try:
        async for event in graph.astream_events(input_, config, version="v2"):
            name = event.get("name", "")
            kind = event["event"]

            if kind == "on_chain_start" and name in STAGE_LABELS:
                _current_stage[0] = name
                _stage_buffer[name] = ""
                yield _sse("stage_start", {"stage": name, "label": STAGE_LABELS[name]})

            elif kind == "on_chat_model_stream" and \
                    event.get("metadata", {}).get("langgraph_node") not in \
                    {"research", "discovery", "review", "approval"}:
                chunk = event["data"].get("chunk")
                raw   = getattr(chunk, "content", "") if chunk else ""
                if isinstance(raw, list):
                    text = "".join(
                        (b.get("text", "") if isinstance(b, dict) else getattr(b, "text", ""))
                        for b in raw
                        if (isinstance(b, dict) and b.get("type") == "text")
                        or (hasattr(b, "type") and getattr(b, "type") == "text")
                    )
                elif isinstance(raw, str):
                    text = raw
                else:
                    text = ""
                if text:
                    if _current_stage[0]:
                        _stage_buffer[_current_stage[0]] = _stage_buffer.get(_current_stage[0], "") + text
                    yield _sse("token", {"content": text})

            elif kind == "on_chain_end" and name in STAGE_LABELS:
                output = event.get("data", {}).get("output") or {}

                if name == "research":
                    doc_version = _get(output, "document_version", 0)
                    doc_draft   = _get(output, "document_draft", "")
                    if doc_draft and db:
                        try:
                            artifact = await db.artifacts.create(
                                conversation_id = conversation_id,
                                execution_id    = execution_id,
                                content         = doc_draft,
                                version         = doc_version,
                                status          = "pending_review",
                            )
                            _latest_artifact_id[0] = artifact.id
                            await _save_msg("assistant", f"Document v{doc_version} submitted for review.", "chat")
                            yield _sse("document_ready", {
                                "version":      doc_version,
                                "artifact_id":  artifact.id,
                                "execution_id": execution_id,
                            })
                        except Exception as exc:
                            log.error("Failed to persist artifact: %s", exc)
                            yield _sse("document_ready", {
                                "version":      doc_version,
                                "execution_id": execution_id,
                            })

                elif name == "review":
                    rr = _get(output, "review_result")
                    feedback = _get(rr, "feedback", "")
                    issues   = _get(rr, "critical_issues", [])
                    content  = feedback
                    if issues:
                        content += "\n\n**Critical issues:**\n" + "\n".join(f"- {i}" for i in issues)
                    await _save_msg("assistant", content, "chat")
                    yield _sse("review_complete", {
                        "passed":          _get(rr, "passed",          False),
                        "feedback":        feedback,
                        "critical_issues": issues,
                    })

                elif name == "approval":
                    ar = _get(output, "approval_result")
                    status   = _get(ar, "status", "rejected")
                    comments = _get(ar, "comments", "")
                    changes  = _get(ar, "required_changes", [])
                    content  = comments
                    if changes:
                        content += "\n\n**Required changes:**\n" + "\n".join(f"- {c}" for c in changes)
                    await _save_msg("assistant", content, "chat")
                    if status == "approved" and _latest_artifact_id[0] and db:
                        try:
                            await db.messages.create(
                                conversation_id = conversation_id,
                                execution_id    = execution_id,
                                role            = "assistant",
                                content         = "",
                                message_type    = "artifact_ref",
                                message_state   = "visible",
                                artifact_id     = _latest_artifact_id[0],
                            )
                        except Exception as exc:
                            log.warning("Failed to save artifact_ref message: %s", exc)
                    yield _sse("approval_complete", {
                        "status":           status,
                        "comments":         comments,
                        "required_changes": changes,
                        "artifact_id":      _latest_artifact_id[0],
                        "document_version": _get(output, "document_version", None),
                    })

                else:
                    buffered = _stage_buffer.pop(name, "")
                    await _save_msg("assistant", buffered, "chat")
                    yield _sse("stage_end", {"stage": name})

        # ── Stream ended — check interrupt vs complete ─────────────────────
        state = await graph.aget_state(config)

        if db:
            state_values  = state.values or {}
            usage_records = state_values.get("usage_records", [])
            session_cfg   = state_values.get("session_agent_config", {})
            for rec in usage_records:
                try:
                    agent_key = rec.get("agent", "")
                    agent_cfg = session_cfg.get(agent_key, {})
                    provider  = agent_cfg.get("provider") or "unknown"
                    model     = rec.get("model") or agent_cfg.get("model") or "unknown"
                    await db.usage.record(
                        conversation_id = conversation_id,
                        provider        = provider,
                        model           = model,
                        input_tokens    = rec.get("input_tokens", 0),
                        output_tokens   = rec.get("output_tokens", 0),
                    )
                except Exception as exc:
                    log.warning("Failed to save usage record: %s | rec=%s", exc, rec)

        if state.next:
            interrupt_value = None
            for task in state.tasks:
                if task.interrupts:
                    interrupt_value = task.interrupts[0].value
                    break

            if (
                isinstance(interrupt_value, dict)
                and interrupt_value.get("__type") == "confirm_understanding"
            ):
                confirm_content = interrupt_value["content"]
                await _save_msg("assistant", confirm_content, "chat")
                yield _sse("confirm_understanding", {
                    "content":      confirm_content,
                    "execution_id": execution_id,
                })
            else:
                questions = (
                    interrupt_value if isinstance(interrupt_value, list)
                    else ([interrupt_value] if interrupt_value else [])
                )
                yield _sse("question", {
                    "questions":    questions,
                    "execution_id": execution_id,
                })
        else:
            values        = state.values
            current_stage = values.get("current_stage", "complete")
            final_status  = current_stage if current_stage in ("complete", "halted", "invalid_input") else "complete"

            if db:
                try:
                    await db.skill_executions.complete(execution_id, final_status)
                except Exception:
                    pass
                # Note: db.skill_executions is the repo; services.executions.complete
                # would also work but repo call is fine in _stream_graph which has db access.

                try:
                    latest = await db.artifacts.get_latest(execution_id)
                    if latest:
                        ar = values.get("approval_result")
                        if ar and hasattr(ar, "status") and ar.status == "approved":
                            await db.artifacts.update_status(latest.id, "approved")
                        elif current_stage == "halted":
                            await db.artifacts.update_status(latest.id, "approval_rejected")
                except Exception:
                    pass

            yield _sse("done", {
                "status":           final_status,
                "document_version": values.get("document_version", 0),
                "revision_count":   values.get("revision_count",   0),
            })

    except Exception as exc:
        import traceback
        msg     = str(exc)
        msg_low = msg.lower()
        log.error("_stream_graph error: %s\n%s", msg, traceback.format_exc())

        from utils.user_context import connected_providers
        connected = connected_providers()

        if "API key not configured for" in msg or "No LLM providers are configured" in msg:
            yield _sse("provider_error", {
                "message":        msg,
                "can_smart_pick": bool(connected),
            })
        elif any(p in msg_low for p in (
            "no longer available", "model not found", "does not exist",
            "model is not available", "not_found", "deprecated",
        )):
            yield _sse("provider_error", {
                "message": (
                    "The selected model is unavailable or has been deprecated. "
                    "Please choose a different model in Settings → Agents, or use Smart Config."
                ),
                "can_smart_pick": bool(connected),
            })
        else:
            friendly = _friendly_error(msg)
            await _save_msg("assistant", friendly, "error")
            yield _sse("error", {"message": friendly})

        if db:
            try:
                await db.skill_executions.complete(execution_id, "error")
            except Exception:
                pass
    finally:
        if execution_id:
            unregister_execution_keys(execution_id)


# ── Invoke skill pipeline ─────────────────────────────────────────────────────

@router.post(
    "/conversations/{conversation_id}/skills/{conversation_skill_id}/invoke",
    tags=["Executions"],
    summary="Start skill pipeline (SSE stream)",
    description="Streams SSE events: stage_start, token, stage_end, document_ready, review_complete, approval_complete, confirm_understanding, question, done, error, provider_error",
    responses={
        200: {"description": "Server-Sent Events stream", "content": {"text/event-stream": {}}},
        400: {"description": "Skill snapshot has no agents"},
        404: {"description": "Conversation or skill snapshot not found"},
        409: {"description": "A skill is already running in this conversation"},
    },
)
async def invoke_skill(
    conversation_id:       str,
    conversation_skill_id: str,
    body:                  InvokeRequest,
    request:               Request,
    current_user:          AuthUser = Depends(get_current_user),
):
    db       = request.app.state.db
    services = request.app.state.services
    conv     = await db.conversations.get_by_id(conversation_id)
    if not conv or conv.user_id != current_user.sub:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    snapshot = await db.skill_snapshots.get_by_id(conversation_skill_id)
    if not snapshot or snapshot.type != "execution" or snapshot.conversation_id != conversation_id:
        raise HTTPException(status_code=404, detail="Skill snapshot not found.")

    if not snapshot.agents:
        raise HTTPException(status_code=400, detail="Skill snapshot has no agents.")

    skill = await db.skills.get_by_id(snapshot.skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found.")

    registry_entry = request.app.state.skill_registry.get(skill.name)
    agent_slot_map = registry_entry.manifest.agent_slot_map if registry_entry else {}

    try:
        execution_id, _, session_agent_config = await services.executions.start(
            conversation_id = conversation_id,
            snapshot_id     = conversation_skill_id,
            agent_slot_map  = agent_slot_map,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    # Build flow_config (agent_key → prompt content) from the snapshot agents
    flow_config: dict = {}
    for ssa in snapshot.agents:
        agent = await db.agents.get_by_id(ssa.skill_agent_id)
        if agent:
            flow_config[agent.name] = ssa.content

    config = {"configurable": {"thread_id": execution_id}}

    user_content = body.original_message or body.brief
    if user_content:
        from repositories.constants import MessageRole, MessageType, MessageState
        await db.messages.create(
            conversation_id = conversation_id,
            execution_id    = execution_id,
            role            = MessageRole.USER,
            content         = user_content,
            message_type    = MessageType.CHAT,
            message_state   = MessageState.VISIBLE,
        )

    await db.conversations.touch(conversation_id)

    from utils.user_context import set_active_models
    active_models_raw = await db.user_llm_models.get_active(current_user.sub)
    active_models = [{"provider": m.provider_key, "model_id": m.model_name} for m in active_models_raw]
    set_active_models(active_models)

    if not conv.title and (body.brief or body.raw_document_text):
        from utils.user_context import _user_keys, get_anthropic_mode
        from api.routes.conversations import _auto_title
        title_text              = body.brief or body.raw_document_text or ""
        first_agent             = next(iter(session_agent_config.values()), {}) if session_agent_config else {}
        t_provider, t_model     = _pick_title_model(first_agent)
        asyncio.create_task(_auto_title(
            db, conversation_id, title_text, t_provider, t_model,
            _user_keys.get() or {}, get_anthropic_mode(),
        ))

    graph = request.app.state.graphs.get(skill.name, request.app.state.graph)

    initial_state = AgentState(
        execution_id          = execution_id,
        conversation_id       = conversation_id,
        conversation_skill_id = conversation_skill_id,
        flow_id               = skill.name,
        flow_config           = flow_config,
        session_agent_config  = session_agent_config,
        source_type           = body.source_type or "brief",
        project_brief         = body.brief or "",
        uploaded_file_path    = body.uploaded_file_path or "",
        uploaded_image_path   = body.uploaded_image_path or "",
        raw_document_text     = body.raw_document_text or "",
    )

    return StreamingResponse(
        _stream_graph(graph, initial_state, config, db, execution_id, conversation_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
            "X-Execution-Id":    execution_id,
        },
    )


# ── Resume interrupt ──────────────────────────────────────────────────────────

@router.post(
    "/executions/{execution_id}/reply",
    tags=["Executions"],
    summary="Resume pipeline after interrupt (SSE stream)",
    description="Resume after confirm_understanding or question interrupt. Streams same events as invoke.",
    responses={
        200: {"description": "Server-Sent Events stream", "content": {"text/event-stream": {}}},
        403: {"description": "Forbidden — execution belongs to another user"},
        404: {"description": "Execution not found"},
    },
)
async def reply(
    execution_id: str,
    body:         ReplyRequest,
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    db        = request.app.state.db
    services  = request.app.state.services
    execution = await services.executions.get_by_id(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found.")

    snapshot = await db.skill_snapshots.get_by_id(execution.snapshot_id)
    conv     = await db.conversations.get_by_id(snapshot.conversation_id) if snapshot else None
    if not conv or conv.user_id != current_user.sub:
        raise HTTPException(status_code=403, detail="Not authorised.")

    skill = await db.skills.get_by_id(snapshot.skill_id) if snapshot else None
    graph = request.app.state.graphs.get(skill.name, request.app.state.graph) if skill else request.app.state.graph

    config = {"configurable": {"thread_id": execution_id}}
    await db.conversations.touch(conv.id)

    answers = body.answers
    if isinstance(answers, list):
        user_content = "\n\n".join(str(a) for a in answers if a)
    else:
        user_content = str(answers or "")
    if user_content.strip():
        from repositories.constants import MessageRole, MessageType, MessageState
        await db.messages.create(
            conversation_id = conv.id,
            execution_id    = execution_id,
            role            = MessageRole.USER,
            content         = user_content.strip(),
            message_type    = MessageType.CHAT,
            message_state   = MessageState.VISIBLE,
        )

    if not conv.title:
        state = await graph.aget_state(config)
        interrupt_value = None
        for task in (state.tasks or []):
            if task.interrupts:
                interrupt_value = task.interrupts[0].value
                break

        if (
            isinstance(interrupt_value, dict)
            and interrupt_value.get("__type") == "confirm_understanding"
        ):
            title_text = body.answers if isinstance(body.answers, str) else ""
            if title_text.strip():
                from utils.user_context import _user_keys, get_anthropic_mode
                from api.routes.conversations import _auto_title
                t_provider, t_model = _pick_title_model(None)
                if t_provider:
                    asyncio.create_task(_auto_title(
                        db, conv.id, title_text.strip(),
                        t_provider, t_model,
                        _user_keys.get() or {}, get_anthropic_mode(),
                    ))

    from utils.user_context import set_active_models
    active_models_raw = await db.user_llm_models.get_active(current_user.sub)
    active_models = [{"provider": m.provider_key, "model_id": m.model_name} for m in active_models_raw]
    set_active_models(active_models)

    return StreamingResponse(
        _stream_graph(graph, Command(resume=body.answers), config, db, execution_id, conv.id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Retry ─────────────────────────────────────────────────────────────────────

@router.post(
    "/executions/{execution_id}/retry",
    tags=["Executions"],
    summary="Retry from last checkpoint (SSE stream)",
    description="Re-streams from the last LangGraph checkpoint with the current model config.",
    responses={
        200: {"description": "Server-Sent Events stream", "content": {"text/event-stream": {}}},
        403: {"description": "Forbidden — execution belongs to another user"},
        404: {"description": "Execution not found"},
        409: {"description": "A skill is already running"},
    },
)
async def retry(
    execution_id: str,
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    db       = request.app.state.db
    services = request.app.state.services

    execution = await services.executions.get_by_id(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found.")

    snapshot = await db.skill_snapshots.get_by_id(execution.snapshot_id)
    conv     = await db.conversations.get_by_id(snapshot.conversation_id) if snapshot else None
    if not conv or conv.user_id != current_user.sub:
        raise HTTPException(status_code=403, detail="Not authorised.")

    skill = await db.skills.get_by_id(snapshot.skill_id) if snapshot else None
    graph = request.app.state.graphs.get(skill.name, request.app.state.graph) if skill else request.app.state.graph

    registry_entry = request.app.state.skill_registry.get(skill.name) if skill else None
    agent_slot_map = registry_entry.manifest.agent_slot_map if registry_entry else {}

    config    = {"configurable": {"thread_id": execution_id}}
    fresh_cfg = await services.executions.reset_for_retry(execution_id, agent_slot_map)
    await graph.aupdate_state(config, {"session_agent_config": fresh_cfg})

    await db.conversations.touch(conv.id)

    from utils.user_context import set_active_models
    active_models_raw = await db.user_llm_models.get_active(current_user.sub)
    active_models = [{"provider": m.provider_key, "model_id": m.model_name} for m in active_models_raw]
    set_active_models(active_models)

    return StreamingResponse(
        _stream_graph(graph, None, config, db, execution_id, conv.id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
