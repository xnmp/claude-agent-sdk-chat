"""asyncpg implementations of repository protocols."""

from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg

from .config import DATABASE_URL
from .models import ANONYMOUS_USER_ID, Conversation, Message, MessageContent, MessageRole, User


# ---------------------------------------------------------------------------
# Connection pool lifecycle (called from app.py lifespan)
# ---------------------------------------------------------------------------

_pool: asyncpg.Pool | None = None


async def init_pool() -> asyncpg.Pool:
    global _pool
    _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    assert _pool is not None, "Database pool not initialized"
    return _pool


# ---------------------------------------------------------------------------
# Row → domain model helpers
# ---------------------------------------------------------------------------


def _row_to_user(row: asyncpg.Record) -> User:
    return User(
        id=row["id"],
        email=row["email"],
        display_name=row["display_name"],
        created_at=row["created_at"],
    )


def _row_to_conversation(row: asyncpg.Record) -> Conversation:
    return Conversation(
        id=row["id"],
        user_id=row.get("user_id", ANONYMOUS_USER_ID),
        title=row["title"],
        sdk_session_id=row["sdk_session_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_message(row: asyncpg.Record) -> Message:
    raw_content = row["content"]
    content = json.loads(raw_content) if isinstance(raw_content, str) else raw_content
    return Message(
        id=row["id"],
        conversation_id=row["conversation_id"],
        role=MessageRole(row["role"]),
        content=content,
        created_at=row["created_at"],
    )


# ---------------------------------------------------------------------------
# UserRepository implementation
# ---------------------------------------------------------------------------


class PgUserRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get_by_email(self, email: str) -> User | None:
        row = await self._pool.fetchrow(
            "SELECT id, email, display_name, created_at FROM users WHERE email = $1",
            email,
        )
        return _row_to_user(row) if row else None

    async def create(self, email: str, display_name: str) -> User:
        row = await self._pool.fetchrow(
            """
            INSERT INTO users (email, display_name)
            VALUES ($1, $2)
            RETURNING id, email, display_name, created_at
            """,
            email,
            display_name,
        )
        return _row_to_user(row)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# ConversationRepository implementation
# ---------------------------------------------------------------------------


class PgConversationRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(
        self,
        title: str | None = None,
        user_id: uuid.UUID = ANONYMOUS_USER_ID,
    ) -> Conversation:
        row = await self._pool.fetchrow(
            """
            INSERT INTO conversations (user_id, title)
            VALUES ($1, $2)
            RETURNING id, user_id, title, sdk_session_id, created_at, updated_at
            """,
            user_id,
            title,
        )
        return _row_to_conversation(row)  # type: ignore[arg-type]

    async def get(self, conversation_id: uuid.UUID) -> Conversation | None:
        row = await self._pool.fetchrow(
            "SELECT id, user_id, title, sdk_session_id, created_at, updated_at "
            "FROM conversations WHERE id = $1",
            conversation_id,
        )
        return _row_to_conversation(row) if row else None

    async def list(
        self,
        user_id: uuid.UUID = ANONYMOUS_USER_ID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Conversation]:
        rows = await self._pool.fetch(
            """
            SELECT id, user_id, title, sdk_session_id, created_at, updated_at
            FROM conversations
            WHERE user_id = $1
            ORDER BY updated_at DESC
            LIMIT $2 OFFSET $3
            """,
            user_id,
            limit,
            offset,
        )
        return [_row_to_conversation(r) for r in rows]

    async def update(
        self,
        conversation_id: uuid.UUID,
        title: str | None = None,
        sdk_session_id: str | None = None,
    ) -> None:
        sets: list[str] = ["updated_at = NOW()"]
        args: list[Any] = []
        idx = 1

        if title is not None:
            idx += 1
            sets.append(f"title = ${idx}")
            args.append(title)
        if sdk_session_id is not None:
            idx += 1
            sets.append(f"sdk_session_id = ${idx}")
            args.append(sdk_session_id)

        await self._pool.execute(
            f"UPDATE conversations SET {', '.join(sets)} WHERE id = $1",
            conversation_id,
            *args,
        )

    async def delete(self, conversation_id: uuid.UUID) -> None:
        await self._pool.execute(
            "DELETE FROM conversations WHERE id = $1",
            conversation_id,
        )


# ---------------------------------------------------------------------------
# MessageRepository implementation
# ---------------------------------------------------------------------------


class PgMessageRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def save(
        self,
        conversation_id: uuid.UUID,
        role: MessageRole,
        content: MessageContent,
    ) -> Message:
        row = await self._pool.fetchrow(
            """
            INSERT INTO messages (conversation_id, role, content)
            VALUES ($1, $2, $3::jsonb)
            RETURNING id, conversation_id, role, content, created_at
            """,
            conversation_id,
            role.value,
            json.dumps(content),
        )
        # Also bump conversation.updated_at
        await self._pool.execute(
            "UPDATE conversations SET updated_at = NOW() WHERE id = $1",
            conversation_id,
        )
        return _row_to_message(row)  # type: ignore[arg-type]

    async def list(
        self,
        conversation_id: uuid.UUID,
        limit: int = 200,
        offset: int = 0,
    ) -> list[Message]:
        rows = await self._pool.fetch(
            """
            SELECT id, conversation_id, role, content, created_at
            FROM messages
            WHERE conversation_id = $1
            ORDER BY created_at ASC
            LIMIT $2 OFFSET $3
            """,
            conversation_id,
            limit,
            offset,
        )
        return [_row_to_message(r) for r in rows]
