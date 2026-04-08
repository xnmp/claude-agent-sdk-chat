"""JSON serialization for domain models — shared across transports."""

from __future__ import annotations

from typing import Any

from .domain.models import Conversation, Message, User


def serialize_user(user: User) -> dict[str, Any]:
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "created_at": user.created_at.isoformat(),
    }


def serialize_conversation(conv: Conversation) -> dict[str, Any]:
    return {
        "id": str(conv.id),
        "user_id": str(conv.user_id),
        "title": conv.title,
        "sdk_session_id": conv.sdk_session_id,
        "created_at": conv.created_at.isoformat(),
        "updated_at": conv.updated_at.isoformat(),
    }


def serialize_message(msg: Message) -> dict[str, Any]:
    return {
        "id": str(msg.id),
        "conversation_id": str(msg.conversation_id),
        "role": msg.role.value,
        "content": msg.content,
        "created_at": msg.created_at.isoformat(),
    }
