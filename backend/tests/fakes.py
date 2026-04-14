"""In-memory fakes for all port interfaces. Used across unit tests."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from backend.domain.models import (
    ANONYMOUS_USER_ID,
    Conversation,
    Message,
    MessageContent,
    MessageRole,
    SDKEvent,
    User,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# FakeUserRepository
# ---------------------------------------------------------------------------


class FakeUserRepository:
    def __init__(self) -> None:
        self._users: dict[str, User] = {}  # keyed by email

    async def get_by_email(self, email: str) -> User | None:
        return self._users.get(email)

    async def create(self, email: str, display_name: str) -> User:
        user = User(
            id=uuid.uuid4(),
            email=email,
            display_name=display_name,
            created_at=_now(),
        )
        self._users[email] = user
        return user


# ---------------------------------------------------------------------------
# FakeConversationRepository
# ---------------------------------------------------------------------------


class FakeConversationRepository:
    def __init__(self) -> None:
        self._convs: dict[UUID, Conversation] = {}

    async def create(
        self,
        title: str | None = None,
        user_id: UUID = ANONYMOUS_USER_ID,
    ) -> Conversation:
        conv = Conversation(
            id=uuid.uuid4(),
            user_id=user_id,
            title=title,
            sdk_session_id=None,
            created_at=_now(),
            updated_at=_now(),
        )
        self._convs[conv.id] = conv
        return conv

    async def get(self, conversation_id: UUID) -> Conversation | None:
        return self._convs.get(conversation_id)

    async def list(
        self,
        user_id: UUID = ANONYMOUS_USER_ID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Conversation]:
        convs = sorted(self._convs.values(), key=lambda c: c.updated_at, reverse=True)
        return convs[offset : offset + limit]

    async def update(
        self,
        conversation_id: UUID,
        title: str | None = None,
        sdk_session_id: str | None = None,
    ) -> None:
        conv = self._convs.get(conversation_id)
        if conv is None:
            return
        # Frozen dataclass — replace with updated copy
        updates: dict[str, Any] = {"updated_at": _now()}
        if title is not None:
            updates["title"] = title
        if sdk_session_id is not None:
            updates["sdk_session_id"] = sdk_session_id
        from dataclasses import replace
        self._convs[conversation_id] = replace(conv, **updates)

    async def delete(self, conversation_id: UUID) -> None:
        self._convs.pop(conversation_id, None)


# ---------------------------------------------------------------------------
# FakeMessageRepository
# ---------------------------------------------------------------------------


class FakeMessageRepository:
    def __init__(self) -> None:
        self._messages: list[Message] = []

    async def save(
        self,
        conversation_id: UUID,
        role: MessageRole,
        content: MessageContent,
    ) -> Message:
        msg = Message(
            id=uuid.uuid4(),
            conversation_id=conversation_id,
            role=role,
            content=content,
            created_at=_now(),
        )
        self._messages.append(msg)
        return msg

    async def list(
        self,
        conversation_id: UUID,
        limit: int = 200,
        offset: int = 0,
    ) -> list[Message]:
        matching = [m for m in self._messages if m.conversation_id == conversation_id]
        matching.sort(key=lambda m: m.created_at)
        return matching[offset : offset + limit]


# ---------------------------------------------------------------------------
# FakeSDKClient / FakeSDKClientFactory
# ---------------------------------------------------------------------------


class FakeSDKClient:
    """SDK client that yields pre-configured events."""

    def __init__(self, events: list[SDKEvent] | None = None) -> None:
        self._events = events or []
        self.connected = False
        self.queries: list[str] = []
        self.interrupted = False

    async def connect(self) -> None:
        self.connected = True

    async def query(self, content: str) -> None:
        self.queries.append(content)

    async def interrupt(self) -> None:
        self.interrupted = True

    async def disconnect(self) -> None:
        self.connected = False

    async def receive_response(self) -> AsyncIterator[SDKEvent]:
        for event in self._events:
            yield event

    def submit_question_answer(self, answer: str) -> bool:
        return False


class FakeSDKClientFactory:
    """Factory that returns a pre-configured FakeSDKClient."""

    def __init__(self, client: FakeSDKClient | None = None) -> None:
        self._client = client or FakeSDKClient()
        self._created: dict[str, FakeSDKClient] = {}
        self._removed: list[str] = []

    async def create(self, session_id: str, resume: bool = False) -> FakeSDKClient:
        self._created[session_id] = self._client
        return self._client

    async def remove(self, session_id: str) -> None:
        self._removed.append(session_id)

    def has(self, session_id: str) -> bool:
        return session_id in self._created
