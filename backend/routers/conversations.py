from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import db

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


class CreateConversationRequest(BaseModel):
    title: str | None = None


class UpdateConversationRequest(BaseModel):
    title: str


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Convert UUID and datetime fields to JSON-safe types."""
    out: dict[str, Any] = {}
    for k, v in row.items():
        if hasattr(v, "hex"):  # UUID
            out[k] = str(v)
        elif hasattr(v, "isoformat"):  # datetime
            out[k] = v.isoformat()
        elif isinstance(v, str):
            # asyncpg returns JSONB as string; parse it
            if k == "content":
                try:
                    out[k] = json.loads(v)
                except (json.JSONDecodeError, TypeError):
                    out[k] = v
            else:
                out[k] = v
        else:
            out[k] = v
    return out


@router.get("")
async def list_conversations(limit: int = 50, offset: int = 0) -> dict[str, Any]:
    rows = await db.list_conversations(limit=limit, offset=offset)
    return {"conversations": [_serialize_row(r) for r in rows]}


@router.post("")
async def create_conversation(req: CreateConversationRequest) -> dict[str, Any]:
    row = await db.create_conversation(title=req.title)
    return _serialize_row(row)


@router.get("/{conversation_id}/messages")
async def get_messages(
    conversation_id: str, limit: int = 200, offset: int = 0
) -> dict[str, Any]:
    conv = await db.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    rows = await db.get_messages(conversation_id, limit=limit, offset=offset)
    return {"messages": [_serialize_row(r) for r in rows]}


@router.patch("/{conversation_id}")
async def update_conversation(
    conversation_id: str, req: UpdateConversationRequest
) -> dict[str, str]:
    conv = await db.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await db.update_conversation(conversation_id, title=req.title)
    return {"status": "ok"}


@router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: str) -> dict[str, str]:
    conv = await db.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await db.delete_conversation(conversation_id)
    return {"status": "ok"}
