"""REST endpoints for conversations — thin adapter over repositories."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..models import Conversation, Message
from ..ports import ConversationRepository, MessageRepository

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


class CreateConversationRequest(BaseModel):
    title: str | None = None


class UpdateConversationRequest(BaseModel):
    title: str


# ---------------------------------------------------------------------------
# Serialization (domain model → JSON-safe dict)
# ---------------------------------------------------------------------------


def _serialize_conversation(conv: Conversation) -> dict[str, Any]:
    return {
        "id": str(conv.id),
        "user_id": str(conv.user_id),
        "title": conv.title,
        "sdk_session_id": conv.sdk_session_id,
        "created_at": conv.created_at.isoformat(),
        "updated_at": conv.updated_at.isoformat(),
    }


def _serialize_message(msg: Message) -> dict[str, Any]:
    return {
        "id": str(msg.id),
        "conversation_id": str(msg.conversation_id),
        "role": msg.role,
        "content": msg.content,
        "created_at": msg.created_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------


def _get_conversations(request: Request) -> ConversationRepository:
    return request.app.state.conversations


def _get_messages(request: Request) -> MessageRepository:
    return request.app.state.messages


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("")
async def list_conversations(
    request: Request, limit: int = 50, offset: int = 0,
) -> dict[str, Any]:
    repo = _get_conversations(request)
    convs = await repo.list(limit=limit, offset=offset)
    return {"conversations": [_serialize_conversation(c) for c in convs]}


@router.post("")
async def create_conversation(
    request: Request, req: CreateConversationRequest,
) -> dict[str, Any]:
    repo = _get_conversations(request)
    conv = await repo.create(title=req.title)
    return _serialize_conversation(conv)


@router.get("/{conversation_id}/messages")
async def get_messages(
    request: Request, conversation_id: str, limit: int = 200, offset: int = 0,
) -> dict[str, Any]:
    conv_repo = _get_conversations(request)
    msg_repo = _get_messages(request)

    conv = await conv_repo.get(UUID(conversation_id))
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msgs = await msg_repo.list(UUID(conversation_id), limit=limit, offset=offset)
    return {"messages": [_serialize_message(m) for m in msgs]}


@router.patch("/{conversation_id}")
async def update_conversation(
    request: Request, conversation_id: str, req: UpdateConversationRequest,
) -> dict[str, str]:
    repo = _get_conversations(request)
    conv = await repo.get(UUID(conversation_id))
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await repo.update(UUID(conversation_id), title=req.title)
    return {"status": "ok"}


@router.delete("/{conversation_id}")
async def delete_conversation(
    request: Request, conversation_id: str,
) -> dict[str, str]:
    repo = _get_conversations(request)
    conv = await repo.get(UUID(conversation_id))
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await repo.delete(UUID(conversation_id))
    return {"status": "ok"}
