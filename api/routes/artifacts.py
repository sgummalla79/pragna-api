"""
Artifact routes.

GET /api/artifacts/{artifact_id}            — get artifact content
GET /api/executions/{execution_id}/artifacts — list all artifacts for an execution
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from utils.auth import AuthUser, get_current_user

router = APIRouter()


@router.get(
    "/api/artifacts/{artifact_id}",
    tags=["Artifacts"],
    summary="Get artifact content by ID",
    responses={
        200: {"description": "Full artifact content and metadata"},
        403: {"description": "Forbidden — artifact belongs to another user"},
        404: {"description": "Artifact not found"},
    },
)
async def get_artifact(
    artifact_id:  str,
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    db       = request.app.state.db
    artifact = await db.artifacts.get_by_id(artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found.")

    # Verify access via conversation ownership
    conv = await db.conversations.get_by_id(artifact.conversation_id)
    if not conv or conv.user_id != current_user.sub:
        raise HTTPException(status_code=403, detail="Not authorised.")

    return {
        "id":              artifact.id,
        "conversation_id": artifact.conversation_id,
        "execution_id":    artifact.execution_id,
        "artifact_type":   artifact.artifact_type,
        "content":         artifact.content,
        "version":         artifact.version,
        "status":          artifact.status,
        "created_at":      artifact.created_at,
    }


@router.get(
    "/api/executions/{execution_id}/artifacts",
    tags=["Artifacts"],
    summary="List all artifacts for an execution",
    responses={200: {"description": "Artifact summaries for the execution"}},
)
async def list_artifacts(
    execution_id: str,
    request:      Request,
    current_user: AuthUser = Depends(get_current_user),
):
    db        = request.app.state.db
    artifacts = await db.artifacts.list_for_execution(execution_id)

    return {
        "execution_id": execution_id,
        "artifacts": [
            {
                "id":            a.id,
                "artifact_type": a.artifact_type,
                "version":       a.version,
                "status":        a.status,
                "created_at":    a.created_at,
            }
            for a in artifacts
        ],
    }
