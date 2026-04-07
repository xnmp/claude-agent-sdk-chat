from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg

from .config import DATABASE_URL

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
# Users
# ---------------------------------------------------------------------------


async def get_user_by_email(email: str) -> dict[str, Any] | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, email, display_name, created_at FROM users WHERE email = $1",
        email,
    )
    return dict(row) if row else None  # type: ignore[arg-type]


async def create_user(email: str, display_name: str) -> dict[str, Any]:
    pool = get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO users (email, display_name)
        VALUES ($1, $2)
        RETURNING id, email, display_name, created_at
        """,
        email,
        display_name,
    )
    return dict(row)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------


async def create_conversation(
    title: str | None = None,
    user_id: str = "00000000-0000-0000-0000-000000000000",
) -> dict[str, Any]:
    pool = get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO conversations (user_id, title)
        VALUES ($1, $2)
        RETURNING id, user_id, title, sdk_session_id, created_at, updated_at
        """,
        uuid.UUID(user_id),
        title,
    )
    return dict(row)  # type: ignore[arg-type]


async def list_conversations(
    user_id: str = "00000000-0000-0000-0000-000000000000",
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT id, title, sdk_session_id, created_at, updated_at
        FROM conversations
        WHERE user_id = $1
        ORDER BY updated_at DESC
        LIMIT $2 OFFSET $3
        """,
        uuid.UUID(user_id),
        limit,
        offset,
    )
    return [dict(r) for r in rows]


async def get_conversation(conversation_id: str) -> dict[str, Any] | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, user_id, title, sdk_session_id, created_at, updated_at FROM conversations WHERE id = $1",
        uuid.UUID(conversation_id),
    )
    return dict(row) if row else None  # type: ignore[arg-type]


async def update_conversation(
    conversation_id: str,
    title: str | None = None,
    sdk_session_id: str | None = None,
) -> None:
    pool = get_pool()
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

    await pool.execute(
        f"UPDATE conversations SET {', '.join(sets)} WHERE id = $1",
        uuid.UUID(conversation_id),
        *args,
    )


async def delete_conversation(conversation_id: str) -> None:
    pool = get_pool()
    await pool.execute(
        "DELETE FROM conversations WHERE id = $1",
        uuid.UUID(conversation_id),
    )


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


async def save_message(
    conversation_id: str,
    role: str,
    content: dict[str, Any],
) -> dict[str, Any]:
    pool = get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO messages (conversation_id, role, content)
        VALUES ($1, $2, $3::jsonb)
        RETURNING id, conversation_id, role, content, created_at
        """,
        uuid.UUID(conversation_id),
        role,
        json.dumps(content),
    )
    # Also bump conversation.updated_at
    await pool.execute(
        "UPDATE conversations SET updated_at = NOW() WHERE id = $1",
        uuid.UUID(conversation_id),
    )
    return dict(row)  # type: ignore[arg-type]


async def get_messages(
    conversation_id: str,
    limit: int = 200,
    offset: int = 0,
) -> list[dict[str, Any]]:
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT id, conversation_id, role, content, created_at
        FROM messages
        WHERE conversation_id = $1
        ORDER BY created_at ASC
        LIMIT $2 OFFSET $3
        """,
        uuid.UUID(conversation_id),
        limit,
        offset,
    )
    return [dict(r) for r in rows]
