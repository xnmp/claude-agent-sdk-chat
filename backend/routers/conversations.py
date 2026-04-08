"""REST endpoints for conversations — thin adapter over repositories."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..domain.ports import AppState
from ..serializers import serialize_conversation, serialize_message

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


class CreateConversationRequest(BaseModel):
    title: str | None = None


class UpdateConversationRequest(BaseModel):
    title: str


def _deps(request: Request) -> AppState:
    return request.app.state.deps


@router.get("")
async def list_conversations(
    request: Request, limit: int = 50, offset: int = 0,
) -> dict[str, Any]:
    deps = _deps(request)
    convs = await deps.conversations.list(limit=limit, offset=offset)
    return {"conversations": [serialize_conversation(c) for c in convs]}


@router.post("")
async def create_conversation(
    request: Request, req: CreateConversationRequest,
) -> dict[str, Any]:
    deps = _deps(request)
    conv = await deps.conversations.create(title=req.title)
    return serialize_conversation(conv)


@router.get("/{conversation_id}/messages")
async def get_messages(
    request: Request, conversation_id: str, limit: int = 200, offset: int = 0,
) -> dict[str, Any]:
    deps = _deps(request)
    cid = UUID(conversation_id)

    conv = await deps.conversations.get(cid)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msgs = await deps.messages.list(cid, limit=limit, offset=offset)
    return {"messages": [serialize_message(m) for m in msgs]}


@router.patch("/{conversation_id}")
async def update_conversation(
    request: Request, conversation_id: str, req: UpdateConversationRequest,
) -> dict[str, str]:
    deps = _deps(request)
    cid = UUID(conversation_id)

    conv = await deps.conversations.get(cid)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await deps.conversations.update(cid, title=req.title)
    return {"status": "ok"}


@router.delete("/{conversation_id}")
async def delete_conversation(
    request: Request, conversation_id: str,
) -> dict[str, str]:
    deps = _deps(request)
    cid = UUID(conversation_id)

    conv = await deps.conversations.get(cid)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await deps.conversations.delete(cid)
    return {"status": "ok"}
