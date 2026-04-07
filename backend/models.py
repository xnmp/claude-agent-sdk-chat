"""Domain models — pure data, no infrastructure dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


ANONYMOUS_USER_ID = UUID("00000000-0000-0000-0000-000000000000")


@dataclass(frozen=True)
class User:
    id: UUID
    email: str
    display_name: str | None
    created_at: datetime


@dataclass(frozen=True)
class Conversation:
    id: UUID
    user_id: UUID
    title: str | None
    sdk_session_id: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class Message:
    id: UUID
    conversation_id: UUID
    role: str  # "user" | "assistant"
    content: dict[str, Any]
    created_at: datetime
