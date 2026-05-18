import os
from pathlib import Path
from fastapi import APIRouter, Request

router = APIRouter()


def _read_version() -> str:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "VERSION"
        if candidate.exists():
            return candidate.read_text().strip()
    return os.getenv("APP_VERSION", "")


@router.get(
    "/api/about",
    tags=["Health"],
    summary="App version and upload limits",
    responses={200: {"description": "Version string and upload configuration"}},
)
async def about():
    from config import MAX_FILE_SIZE_MB, ALLOWED_IMAGE_EXTS, ALLOWED_DOC_EXTS
    return {
        "version":            _read_version(),
        "upload": {
            "max_file_size_mb":   MAX_FILE_SIZE_MB,
            "allowed_image_exts": ALLOWED_IMAGE_EXTS,
            "allowed_doc_exts":   ALLOWED_DOC_EXTS,
        },
    }


@router.get(
    "/health",
    tags=["Health"],
    summary="Service health check",
    responses={200: {"description": "DB and compiled skill graph status"}},
)
async def health(request: Request):
    db     = request.app.state.db
    graphs = request.app.state.graphs or {}
    try:
        await db.pool.check()
        db_status = "ready"
    except Exception:
        db_status = "unavailable"

    return {
        "status": "ok" if db_status == "ready" else "degraded",
        "db":     db_status,
        "skills": list(graphs.keys()),
    }
