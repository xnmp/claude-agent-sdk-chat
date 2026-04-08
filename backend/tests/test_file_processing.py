"""Unit tests for file processing — classification and prompt injection."""

from backend.routers.utils.file_processing import (
    FileMetadata,
    build_image_injection,
    build_other_injection,
    build_pdf_injection,
    build_text_injection,
    classify_file,
    MAX_INLINE_TEXT_BYTES,
)


def _meta(filename: str, size: int = 100) -> FileMetadata:
    ext = "." + filename.rsplit(".", 1)[-1] if "." in filename else ""
    return FileMetadata(id="test-id", filename=filename, path=f"/uploads/{filename}", size=size, extension=ext)


class TestClassifyFile:
    def test_text_files(self):
        for ext in [".py", ".txt", ".md", ".json", ".csv", ".ts", ".html"]:
            assert classify_file(_meta(f"file{ext}")) == "text"

    def test_image_files(self):
        for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"]:
            assert classify_file(_meta(f"file{ext}")) == "image"

    def test_pdf(self):
        assert classify_file(_meta("doc.pdf")) == "pdf"

    def test_other(self):
        for ext in [".zip", ".exe", ".bin", ".docx"]:
            assert classify_file(_meta(f"file{ext}")) == "other"

    def test_case_insensitive(self):
        assert classify_file(_meta("file.PY")) == "text"
        assert classify_file(_meta("file.PNG")) == "image"
        assert classify_file(_meta("file.PDF")) == "pdf"


class TestBuildTextInjection:
    def test_small_file_inlined(self):
        meta = _meta("code.py", size=100)
        result = build_text_injection(meta, "print('hello')")
        assert "print('hello')" in result.injection
        assert "code.py" in result.injection

    def test_large_file_shows_path(self):
        meta = _meta("big.txt", size=MAX_INLINE_TEXT_BYTES + 1)
        result = build_text_injection(meta, "x" * (MAX_INLINE_TEXT_BYTES + 1))
        assert "too large" in result.injection
        assert meta.path in result.injection


class TestBuildImageInjection:
    def test_small_image(self):
        meta = _meta("photo.png", size=1000)
        result = build_image_injection(meta)
        assert "photo.png" in result.injection
        assert meta.path in result.injection

    def test_large_image(self):
        meta = _meta("huge.png", size=10_000_000)
        result = build_image_injection(meta)
        assert "too large" in result.injection


class TestBuildPdfInjection:
    def test_with_extracted_text(self):
        meta = _meta("doc.pdf", size=5000)
        result = build_pdf_injection(meta, "Page 1 content\n\nPage 2 content")
        assert "Page 1 content" in result.injection
        assert "doc.pdf" in result.injection

    def test_extraction_failed(self):
        meta = _meta("broken.pdf", size=5000)
        result = build_pdf_injection(meta, None)
        assert "extraction failed" in result.injection
        assert meta.path in result.injection

    def test_long_text_truncated(self):
        meta = _meta("long.pdf", size=5000)
        long_text = "x" * (MAX_INLINE_TEXT_BYTES + 1000)
        result = build_pdf_injection(meta, long_text)
        assert "truncated" in result.injection


class TestBuildOtherInjection:
    def test_shows_filename_and_path(self):
        meta = _meta("archive.zip", size=50000)
        result = build_other_injection(meta)
        assert "archive.zip" in result.injection
        assert meta.path in result.injection
        assert "50000" in result.injection
