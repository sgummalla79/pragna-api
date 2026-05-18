"""
Local filesystem storage for uploaded documents.

Files are saved to UPLOAD_DIR with a UUID filename to avoid collisions.
The original filename is preserved as a prefix so the directory stays human-readable.
"""

import uuid
from pathlib import Path

from config import UPLOAD_DIR


def save_upload(original_filename: str, content: bytes) -> str:
    """
    Write the file to UPLOAD_DIR and return its absolute path.
    Creates the directory if it does not exist.
    """
    upload_dir = Path(UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    suffix     = Path(original_filename).suffix.lower()
    stem       = Path(original_filename).stem[:40]          # cap long names
    safe_name  = f"{stem}_{uuid.uuid4().hex}{suffix}"

    dest = upload_dir / safe_name
    dest.write_bytes(content)
    return str(dest.resolve())
