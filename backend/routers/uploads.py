"""REST endpoint for file uploads."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

import fitz  # pymupdf
from fastapi import APIRouter, UploadFile, HTTPException

from ..config import AGENT_CWD
from .utils.file_processing import (
    FileMetadata,
    PromptAttachment,
    build_image_injection,
    build_other_injection,
    build_pdf_injection,
    build_text_injection,
    classify_file,
)

router = APIRouter()

UPLOADS_DIR = os.path.join(AGENT_CWD, "uploads")

# In-memory store: attachment_id → (FileMetadata, PromptAttachment)
_attachments: dict[str, tuple[FileMetadata, PromptAttachment]] = {}


def get_attachment(attachment_id: str) -> tuple[FileMetadata, PromptAttachment] | None:
    return _attachments.get(attachment_id)


def _extract_pdf_text(path: str) -> str | None:
    try:
        doc = fitz.open(path)
        pages: list[str] = []
        for page in doc:
            pages.append(str(page.get_text()))
        doc.close()
        return "\n\n".join(pages)
    except Exception:
        return None


@router.post("/api/upload/{conversation_id}")
async def upload_file(conversation_id: str, file: UploadFile) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(400, "No filename")

    # Sanitize filename
    safe_name = Path(file.filename).name
    if not safe_name or safe_name.startswith("."):
        raise HTTPException(400, "Invalid filename")

    # Create upload directory
    conv_dir = os.path.join(UPLOADS_DIR, conversation_id)
    os.makedirs(conv_dir, exist_ok=True)

    # Save file
    attachment_id = str(uuid.uuid4())
    file_path = os.path.join(conv_dir, f"{attachment_id}_{safe_name}")
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    ext = os.path.splitext(safe_name)[1].lower()
    meta = FileMetadata(
        id=attachment_id,
        filename=safe_name,
        path=file_path,
        size=len(content),
        extension=ext,
    )

    # Process file based on type
    file_type = classify_file(meta)
    if file_type == "text":
        try:
            text_content = content.decode("utf-8", errors="replace")
        except Exception:
            text_content = content.decode("latin-1")
        attachment = build_text_injection(meta, text_content)
    elif file_type == "image":
        attachment = build_image_injection(meta)
    elif file_type == "pdf":
        extracted = _extract_pdf_text(file_path)
        attachment = build_pdf_injection(meta, extracted)
    else:
        attachment = build_other_injection(meta)

    _attachments[attachment_id] = (meta, attachment)

    return {
        "id": attachment_id,
        "filename": safe_name,
        "size": len(content),
        "type": file_type,
    }
