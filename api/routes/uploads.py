"""
File upload route — accepts document or image, extracts text, returns paths.

POST /api/uploads

Frontend flow:
  1. Upload file here → get back {source_type, raw_text, uploaded_file_path,
                                   uploaded_image_path}
  2. Create conversation
  3. Add skill
  4. Invoke skill with the returned fields as the body
"""

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from config import MAX_FILE_SIZE_MB
from utils.auth import AuthUser, get_current_user
from utils.file_storage import save_upload

IMAGE_EXTENSIONS    = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md"}
ALL_ACCEPTED        = DOCUMENT_EXTENSIONS | IMAGE_EXTENSIONS

router = APIRouter(prefix="/api/uploads")


@router.post(
    "",
    tags=["Uploads"],
    summary="Upload a document or image for pipeline intake",
    description="Documents: text is extracted immediately. Images: stored for vision processing at pipeline time. Returns fields to pass directly to the skill invoke endpoint.",
    responses={
        200: {"description": "Upload result with source_type and file paths"},
        413: {"description": "File exceeds size limit"},
        415: {"description": "Unsupported file type"},
        422: {"description": "Text extraction failed"},
    },
)
async def upload_file(
    request:      Request,
    file:         UploadFile = File(...),
    current_user: AuthUser   = Depends(get_current_user),
):
    """
    Accept a document or image.
    - Documents: extract text immediately, return raw_text.
    - Images: save to disk, return path (intake node uses vision at pipeline time).

    Returns the fields needed to pass directly to the skill invoke endpoint.
    """
    suffix = Path(file.filename or "").suffix.lower()

    if suffix not in ALL_ACCEPTED:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported file type '{suffix}'. "
                f"Documents: {', '.join(sorted(DOCUMENT_EXTENSIONS))}  "
                f"Images: {', '.join(sorted(IMAGE_EXTENSIONS))}"
            ),
        )

    is_image  = suffix in IMAGE_EXTENSIONS
    max_bytes = MAX_FILE_SIZE_MB * 1024 * 1024
    content   = await file.read()

    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {MAX_FILE_SIZE_MB} MB limit.",
        )

    saved_path = save_upload(file.filename, content)

    if is_image:
        return {
            "source_type":         "image",
            "uploaded_image_path": saved_path,
            "uploaded_file_path":  "",
            "raw_document_text":   "",
            "filename":            file.filename,
        }

    # Document — extract text now
    from utils.file_parser import extract_text
    try:
        raw_text = extract_text(file.filename, content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return {
        "source_type":         "document",
        "uploaded_file_path":  saved_path,
        "uploaded_image_path": "",
        "raw_document_text":   raw_text,
        "filename":            file.filename,
    }
