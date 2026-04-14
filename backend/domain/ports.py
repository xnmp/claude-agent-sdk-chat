"""Port interfaces — abstract boundaries the domain depends on.

Concrete implementations live in infrastructure modules (db.py, sdk_manager.py).
Domain logic (chat.py, routers) depends only on these protocols.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from .models import (
    ANONYMOUS_USER_ID,
    Conversation,
    Message,
    MessageContent,
    MessageRole,
    SDKEvent,
    User,
)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


class UserRepository(Protocol):
    async def get_by_email(self, email: str) -> User | None: ...
    async def create(self, email: str, display_name: str) -> User: ...


class ConversationRepository(Protocol):
    async def create(
        self, title: str | None = None, user_id: UUID = ANONYMOUS_USER_ID,
    ) -> Conversation: ...

    async def get(self, conversation_id: UUID) -> Conversation | None: ...

    async def list(
        self, user_id: UUID = ANONYMOUS_USER_ID, limit: int = 50, offset: int = 0,
    ) -> list[Conversation]: ...

    async def update(
        self,
        conversation_id: UUID,
        title: str | None = None,
        sdk_session_id: str | None = None,
    ) -> None: ...

    async def delete(self, conversation_id: UUID) -> None: ...


class MessageRepository(Protocol):
    async def save(
        self, conversation_id: UUID, role: MessageRole, content: MessageContent,
    ) -> Message: ...

    async def list(
        self, conversation_id: UUID, limit: int = 200, offset: int = 0,
    ) -> list[Message]: ...


# ---------------------------------------------------------------------------
# SDK client
# ---------------------------------------------------------------------------


class SDKClient(Protocol):
    """Abstract interface for an AI agent client."""

    async def connect(self) -> None: ...
    async def query(self, content: str) -> None: ...
    async def interrupt(self) -> None: ...
    async def disconnect(self) -> None: ...
    def receive_response(self) -> AsyncIterator[SDKEvent]: ...
    def submit_question_answer(self, answer: str) -> bool: ...


class SDKClientFactory(Protocol):
    """Creates and manages SDKClient instances keyed by session ID."""

    async def create(self, session_id: str, resume: bool = False) -> SDKClient: ...
    async def remove(self, session_id: str) -> None: ...
    def has(self, session_id: str) -> bool: ...


# ---------------------------------------------------------------------------
# Typed application state (dependency container)
# ---------------------------------------------------------------------------


@dataclass
class AppState:
    users: UserRepository
    conversations: ConversationRepository
    messages: MessageRepository
    sdk_factory: SDKClientFactory
