"""
Unit tests for utils/file_parser.py and utils/file_storage.py.

file_parser: txt/md need no mocking (pure bytes). pdf/docx mock the
third-party reader so no real document is required.

file_storage: uses pytest's tmp_path fixture — a real temp dir, no mocking.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


# ── file_parser.py ────────────────────────────────────────────────────────────

class TestExtractText:

    def test_txt_returns_decoded_content(self):
        from utils.file_parser import extract_text
        content = "Hello, world!\nLine two.".encode("utf-8")
        result  = extract_text("brief.txt", content)
        assert result == "Hello, world!\nLine two."

    def test_md_returns_decoded_content(self):
        from utils.file_parser import extract_text
        content = "# Title\n\nSome **markdown** content.".encode("utf-8")
        result  = extract_text("notes.md", content)
        assert "Title" in result
        assert "markdown" in result

    def test_txt_handles_non_utf8_gracefully(self):
        from utils.file_parser import extract_text
        content = b"Hello \xff world"   # invalid utf-8 byte
        result  = extract_text("file.txt", content)
        assert "Hello" in result        # bad bytes ignored, not crash

    def test_unsupported_extension_raises(self):
        from utils.file_parser import extract_text
        with pytest.raises(ValueError, match="Unsupported file type '.xlsx'"):
            extract_text("data.xlsx", b"some bytes")

    def test_unsupported_extension_png_raises(self):
        from utils.file_parser import extract_text
        with pytest.raises(ValueError):
            extract_text("photo.png", b"\x89PNG")

    def test_pdf_extraction(self):
        from utils.file_parser import extract_text

        mock_page1 = MagicMock()
        mock_page1.extract_text.return_value = "Page one content."
        mock_page2 = MagicMock()
        mock_page2.extract_text.return_value = "Page two content."

        mock_reader = MagicMock()
        mock_reader.pages = [mock_page1, mock_page2]

        with patch("pypdf.PdfReader", return_value=mock_reader):
            result = extract_text("document.pdf", b"%PDF-fake")

        assert "Page one content." in result
        assert "Page two content." in result

    def test_pdf_empty_raises(self):
        from utils.file_parser import extract_text

        mock_page = MagicMock()
        mock_page.extract_text.return_value = ""

        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]

        with patch("pypdf.PdfReader", return_value=mock_reader):
            with pytest.raises(ValueError, match="No extractable text"):
                extract_text("empty.pdf", b"%PDF-fake")

    def test_pdf_page_cap_adds_note(self):
        from utils.file_parser import extract_text
        from config import MAX_PDF_PAGES

        total_pages = MAX_PDF_PAGES + 5
        pages = []
        for i in range(total_pages):
            p = MagicMock()
            p.extract_text.return_value = f"Content of page {i+1}."
            pages.append(p)

        mock_reader = MagicMock()
        mock_reader.pages = pages

        with patch("pypdf.PdfReader", return_value=mock_reader):
            result = extract_text("long.pdf", b"%PDF-fake")

        assert f"Only the first {MAX_PDF_PAGES} pages" in result
        assert f"has {total_pages} pages" in result

    def test_docx_extraction(self):
        from utils.file_parser import extract_text

        para1 = MagicMock()
        para1.text = "First paragraph."
        para2 = MagicMock()
        para2.text = "Second paragraph."
        para3 = MagicMock()
        para3.text = ""   # empty paragraph — should be skipped

        mock_doc = MagicMock()
        mock_doc.paragraphs = [para1, para2, para3]

        with patch("docx.Document", return_value=mock_doc):
            result = extract_text("report.docx", b"PK-fake-docx")

        assert "First paragraph." in result
        assert "Second paragraph." in result

    def test_docx_empty_raises(self):
        from utils.file_parser import extract_text

        mock_doc = MagicMock()
        mock_doc.paragraphs = []

        with patch("docx.Document", return_value=mock_doc):
            with pytest.raises(ValueError, match="No text content"):
                extract_text("empty.docx", b"PK-fake")

    def test_doc_extension_treated_as_docx(self):
        from utils.file_parser import extract_text

        para = MagicMock()
        para.text = "Legacy Word content."
        mock_doc = MagicMock()
        mock_doc.paragraphs = [para]

        with patch("docx.Document", return_value=mock_doc):
            result = extract_text("old.doc", b"PK-fake")

        assert "Legacy Word content." in result


# ── file_storage.py ───────────────────────────────────────────────────────────

class TestSaveUpload:

    def test_saves_file_and_returns_path(self, tmp_path):
        from utils.file_storage import save_upload

        with patch("utils.file_storage.UPLOAD_DIR", str(tmp_path)):
            saved = save_upload("architecture.pdf", b"%PDF-content")

        p = Path(saved)
        assert p.exists()
        assert p.read_bytes() == b"%PDF-content"
        assert p.suffix == ".pdf"

    def test_creates_upload_dir_if_missing(self, tmp_path):
        from utils.file_storage import save_upload
        nested = str(tmp_path / "uploads" / "new")

        with patch("utils.file_storage.UPLOAD_DIR", nested):
            saved = save_upload("doc.txt", b"content")

        assert Path(saved).exists()

    def test_filename_includes_original_stem(self, tmp_path):
        from utils.file_storage import save_upload

        with patch("utils.file_storage.UPLOAD_DIR", str(tmp_path)):
            saved = save_upload("my_architecture_design.pdf", b"bytes")

        filename = Path(saved).name
        assert "my_architecture_design" in filename

    def test_long_filename_is_capped(self, tmp_path):
        from utils.file_storage import save_upload
        long_name = "a" * 200 + ".txt"

        with patch("utils.file_storage.UPLOAD_DIR", str(tmp_path)):
            saved = save_upload(long_name, b"data")

        # stem is capped at 40 chars + _ + uuid_hex(32) + .txt ≤ 80 chars approx
        filename = Path(saved).name
        assert len(filename) < 120

    def test_each_upload_gets_unique_name(self, tmp_path):
        from utils.file_storage import save_upload

        with patch("utils.file_storage.UPLOAD_DIR", str(tmp_path)):
            path1 = save_upload("file.txt", b"v1")
            path2 = save_upload("file.txt", b"v2")

        assert path1 != path2
        assert Path(path1).read_bytes() == b"v1"
        assert Path(path2).read_bytes() == b"v2"
