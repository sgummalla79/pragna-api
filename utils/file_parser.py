"""
Extracts plain text from uploaded files.
Supported formats: PDF, DOCX, TXT, MD

PDF extraction is capped at MAX_PDF_PAGES pages (configurable in config.py).
"""

import io
from pathlib import Path

from config import MAX_PDF_PAGES


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md"}


def extract_text(filename: str, content: bytes) -> str:
    suffix = Path(filename).suffix.lower()

    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{suffix}'. "
            f"Accepted: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    if suffix == ".pdf":
        return _extract_pdf(content)
    if suffix in (".docx", ".doc"):
        return _extract_docx(content)
    if suffix in (".txt", ".md"):
        return content.decode("utf-8", errors="ignore")

    raise ValueError(f"Unhandled extension: {suffix}")


def _extract_pdf(content: bytes) -> str:
    from pypdf import PdfReader

    reader     = PdfReader(io.BytesIO(content))
    total      = len(reader.pages)
    capped     = total > MAX_PDF_PAGES
    pages      = reader.pages[:MAX_PDF_PAGES]

    extracted  = [page.extract_text() or "" for page in pages]
    text       = "\n\n".join(p.strip() for p in extracted if p.strip())

    if not text:
        raise ValueError(
            "No extractable text found in the PDF. "
            "It may be a scanned image — please provide a text-based PDF."
        )

    if capped:
        text += (
            f"\n\n---\n[Note: This document has {total} pages. "
            f"Only the first {MAX_PDF_PAGES} pages were processed.]"
        )

    return text


def _extract_docx(content: bytes) -> str:
    from docx import Document

    doc        = Document(io.BytesIO(content))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]

    if not paragraphs:
        raise ValueError("No text content found in the Word document.")

    return "\n\n".join(paragraphs)
