"""
Usage / token cost routes.

GET /api/conversations/{id}/usage  — token usage for a conversation
GET /api/usage/summary             — aggregate usage for the current user
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from utils.auth import AuthUser, get_current_user

router = APIRouter(prefix="/api")


@router.get(
    "/conversations/{conversation_id}/usage",
    tags=["Usage"],
    summary="Token usage and cost for a conversation",
    responses={
        200: {"description": "Token totals and per-model breakdown"},
        404: {"description": "Conversation not found"},
    },
)
async def conversation_usage(
    conversation_id: str,
    request:         Request,
    current_user:    AuthUser = Depends(get_current_user),
):
    db   = request.app.state.db
    conv = await db.conversations.get_by_id(conversation_id)
    if not conv or conv.user_id != current_user.sub:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    stats = await db.usage.get_by_conversation(conversation_id)
    return {
        "conversation_id": conversation_id,
        "totals": {
            "input_tokens":  stats.input_tokens,
            "output_tokens": stats.output_tokens,
            "cost_usd":      stats.cost_usd,
        },
        "breakdown": stats.breakdown,
    }


@router.get(
    "/usage/summary",
    tags=["Usage"],
    summary="Aggregate token usage across all user conversations",
    responses={200: {"description": "Summed token counts and cost across all conversations"}},
)
async def usage_summary(
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    db    = request.app.state.db
    convs = await db.conversations.list_for_user(current_user.sub)

    total_input = total_output = total_cost = 0
    for conv in convs:
        stats = await db.usage.get_by_conversation(conv.id)
        total_input  += stats.input_tokens
        total_output += stats.output_tokens
        total_cost   += stats.cost_usd

    return {
        "totals": {
            "input_tokens":      total_input,
            "output_tokens":     total_output,
            "cost_usd":          round(total_cost, 6),
            "conversation_count": len(convs),
        }
    }
