"""File processing — categorize uploads and build prompt injections.

Pure domain logic: no framework imports, no disk I/O.
Callers provide file content; this module decides how to present it to the model.
"""

from __future__ import annotations

from dataclasses import dataclass

TEXT_EXTENSIONS = {
    ".txt", ".md", ".csv", ".json", ".xml", ".yaml", ".yml", ".toml",
    ".py", ".js", ".ts", ".html", ".css", ".sql", ".sh", ".bash",
    ".rs", ".go", ".java", ".c", ".cpp", ".h", ".hpp", ".rb", ".php",
    ".svelte", ".vue", ".jsx", ".tsx", ".env", ".ini", ".cfg", ".conf",
    ".log", ".r", ".m", ".swift",
}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}

MAX_INLINE_TEXT_BYTES = 50_000  # 50KB
MAX_INLINE_IMAGE_BYTES = 5_000_000  # 5MB


@dataclass
class FileMetadata:
    id: str
    filename: str
    path: str
    size: int
    extension: str


@dataclass
class PromptAttachment:
    """How a file should be presented in the prompt."""
    filename: str
    injection: str  # text to prepend/append to the user message


def classify_file(meta: FileMetadata) -> str:
    """Return 'text', 'image', 'pdf', or 'other'."""
    ext = meta.extension.lower()
    if ext in TEXT_EXTENSIONS:
        return "text"
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext == ".pdf":
        return "pdf"
    return "other"


def build_text_injection(meta: FileMetadata, content: str) -> PromptAttachment:
    """Build prompt injection for a text file."""
    if meta.size <= MAX_INLINE_TEXT_BYTES:
        return PromptAttachment(
            filename=meta.filename,
            injection=f"\n\n--- File: {meta.filename} ---\n{content}\n--- End of {meta.filename} ---",
        )
    return PromptAttachment(
        filename=meta.filename,
        injection=f"\n\n[File too large for inline display. Available at: {meta.path}]",
    )


def build_image_injection(meta: FileMetadata) -> PromptAttachment:
    """Build prompt injection for an image file."""
    if meta.size <= MAX_INLINE_IMAGE_BYTES:
        return PromptAttachment(
            filename=meta.filename,
            injection=f"\n\n[Image attached: {meta.filename} — available at: {meta.path}]",
        )
    return PromptAttachment(
        filename=meta.filename,
        injection=f"\n\n[Image too large for inline display. Available at: {meta.path}]",
    )


def build_pdf_injection(meta: FileMetadata, extracted_text: str | None) -> PromptAttachment:
    """Build prompt injection for a PDF file."""
    if extracted_text:
        truncated = extracted_text[:MAX_INLINE_TEXT_BYTES]
        suffix = "... [truncated]" if len(extracted_text) > MAX_INLINE_TEXT_BYTES else ""
        return PromptAttachment(
            filename=meta.filename,
            injection=f"\n\n--- PDF: {meta.filename} ---\n{truncated}{suffix}\n--- End of {meta.filename} ---",
        )
    return PromptAttachment(
        filename=meta.filename,
        injection=f"\n\n[PDF text extraction failed. File available at: {meta.path}]",
    )


def build_other_injection(meta: FileMetadata) -> PromptAttachment:
    """Build prompt injection for an unrecognized file type."""
    return PromptAttachment(
        filename=meta.filename,
        injection=f"\n\n[File attached: {meta.filename} ({meta.size} bytes) — available at: {meta.path}]",
    )
