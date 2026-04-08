"""Integration tests for Postgres repositories — requires a running database.

Run with: uv run pytest -m integration
Skipped automatically when the database is not available.
"""

from __future__ import annotations

import uuid

import asyncpg
import pytest

from backend.config import DATABASE_URL
from backend.infra.db import PgConversationRepository, PgMessageRepository, PgUserRepository
from backend.domain.models import AssistantMessageContent, MessageRole

pytestmark = pytest.mark.integration


@pytest.fixture
async def pool():
    """Create a connection pool and clean up test data after each test."""
    try:
        pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)
    except (OSError, asyncpg.PostgresError):
        pytest.skip("Database not available")
    yield pool
    # Clean up any test data (users with test- prefix emails)
    await pool.execute("DELETE FROM messages WHERE conversation_id IN (SELECT id FROM conversations WHERE title LIKE 'TEST-%')")
    await pool.execute("DELETE FROM conversations WHERE title LIKE 'TEST-%'")
    await pool.execute("DELETE FROM users WHERE email LIKE 'test-%'")
    await pool.close()


@pytest.fixture
def user_repo(pool: asyncpg.Pool) -> PgUserRepository:
    return PgUserRepository(pool)


@pytest.fixture
def conv_repo(pool: asyncpg.Pool) -> PgConversationRepository:
    return PgConversationRepository(pool)


@pytest.fixture
def msg_repo(pool: asyncpg.Pool) -> PgMessageRepository:
    return PgMessageRepository(pool)


class TestPgUserRepository:
    async def test_create_and_get_by_email(self, user_repo: PgUserRepository):
        email = f"test-{uuid.uuid4().hex[:8]}@example.com"
        created = await user_repo.create(email, "Test User")

        assert created.email == email
        assert created.display_name == "Test User"
        assert created.id is not None

        found = await user_repo.get_by_email(email)
        assert found is not None
        assert found.id == created.id
        assert found.email == email

    async def test_get_by_email_returns_none_for_missing(self, user_repo: PgUserRepository):
        result = await user_repo.get_by_email(f"nonexistent-{uuid.uuid4().hex}@example.com")
        assert result is None


class TestPgConversationRepository:
    async def test_create_and_get(self, conv_repo: PgConversationRepository):
        conv = await conv_repo.create(title="TEST-create-get")

        assert conv.title == "TEST-create-get"
        assert conv.sdk_session_id is None

        found = await conv_repo.get(conv.id)
        assert found is not None
        assert found.id == conv.id
        assert found.title == "TEST-create-get"

    async def test_get_returns_none_for_missing(self, conv_repo: PgConversationRepository):
        result = await conv_repo.get(uuid.uuid4())
        assert result is None

    async def test_list_returns_newest_first(self, conv_repo: PgConversationRepository):
        c1 = await conv_repo.create(title="TEST-list-1")
        c2 = await conv_repo.create(title="TEST-list-2")

        convs = await conv_repo.list()
        ids = [c.id for c in convs]
        # c2 was created later, should appear first
        assert ids.index(c2.id) < ids.index(c1.id)

    async def test_update_title(self, conv_repo: PgConversationRepository):
        conv = await conv_repo.create(title="TEST-update-before")
        await conv_repo.update(conv.id, title="TEST-update-after")

        updated = await conv_repo.get(conv.id)
        assert updated is not None
        assert updated.title == "TEST-update-after"

    async def test_update_sdk_session_id(self, conv_repo: PgConversationRepository):
        conv = await conv_repo.create(title="TEST-session")
        await conv_repo.update(conv.id, sdk_session_id="new-session-id")

        updated = await conv_repo.get(conv.id)
        assert updated is not None
        assert updated.sdk_session_id == "new-session-id"

    async def test_delete(self, conv_repo: PgConversationRepository):
        conv = await conv_repo.create(title="TEST-delete")
        await conv_repo.delete(conv.id)

        assert await conv_repo.get(conv.id) is None

    async def test_list_respects_limit_and_offset(self, conv_repo: PgConversationRepository):
        for i in range(3):
            await conv_repo.create(title=f"TEST-paginate-{i}")

        page = await conv_repo.list(limit=2, offset=0)
        assert len(page) >= 2

        page2 = await conv_repo.list(limit=2, offset=2)
        # page2 should have different conversations than page
        page_ids = {c.id for c in page}
        page2_ids = {c.id for c in page2}
        assert page_ids.isdisjoint(page2_ids)


class TestPgMessageRepository:
    async def test_save_and_list(
        self, conv_repo: PgConversationRepository, msg_repo: PgMessageRepository,
    ):
        conv = await conv_repo.create(title="TEST-messages")

        await msg_repo.save(conv.id, MessageRole.USER, {"text": "hello"})
        await msg_repo.save(conv.id, MessageRole.ASSISTANT, {
            "thinking": [], "tool_calls": [], "text": "hi back",
            "model": "claude", "usage": {}, "duration_ms": 50, "total_cost_usd": 0.001,
        })

        msgs = await msg_repo.list(conv.id)
        assert len(msgs) == 2
        assert msgs[0].role == MessageRole.USER
        assert msgs[0].content["text"] == "hello"
        assert msgs[1].role == MessageRole.ASSISTANT
        assert msgs[1].content["text"] == "hi back"

    async def test_messages_ordered_by_creation(
        self, conv_repo: PgConversationRepository, msg_repo: PgMessageRepository,
    ):
        conv = await conv_repo.create(title="TEST-order")

        await msg_repo.save(conv.id, MessageRole.USER, {"text": "first"})
        await msg_repo.save(conv.id, MessageRole.USER, {"text": "second"})
        await msg_repo.save(conv.id, MessageRole.USER, {"text": "third"})

        msgs = await msg_repo.list(conv.id)
        assert [m.content["text"] for m in msgs] == ["first", "second", "third"]

    async def test_delete_conversation_cascades_to_messages(
        self, conv_repo: PgConversationRepository, msg_repo: PgMessageRepository,
    ):
        conv = await conv_repo.create(title="TEST-cascade")
        await msg_repo.save(conv.id, MessageRole.USER, {"text": "will be deleted"})

        await conv_repo.delete(conv.id)

        msgs = await msg_repo.list(conv.id)
        assert msgs == []

    async def test_save_bumps_conversation_updated_at(
        self, conv_repo: PgConversationRepository, msg_repo: PgMessageRepository,
    ):
        conv = await conv_repo.create(title="TEST-timestamp")
        original_updated = conv.updated_at

        await msg_repo.save(conv.id, MessageRole.USER, {"text": "bump"})

        updated_conv = await conv_repo.get(conv.id)
        assert updated_conv is not None
        assert updated_conv.updated_at > original_updated

    async def test_list_respects_limit(
        self, conv_repo: PgConversationRepository, msg_repo: PgMessageRepository,
    ):
        conv = await conv_repo.create(title="TEST-limit")
        for i in range(5):
            await msg_repo.save(conv.id, MessageRole.USER, {"text": f"msg-{i}"})

        msgs = await msg_repo.list(conv.id, limit=3)
        assert len(msgs) == 3

    async def test_jsonb_content_round_trips(
        self, conv_repo: PgConversationRepository, msg_repo: PgMessageRepository,
    ):
        conv = await conv_repo.create(title="TEST-jsonb")
        complex_content: AssistantMessageContent = {
            "thinking": [{"thinking": "deep thought", "signature": "xyz"}],
            "tool_calls": [
                {"id": "t1", "name": "Read", "input": {"file_path": "/tmp/x"}, "result": "contents", "is_error": False},
            ],
            "text": "answer",
            "model": "claude-sonnet-4-20250514",
            "usage": {"input_tokens": 100, "output_tokens": 50},
            "duration_ms": 2000,
            "total_cost_usd": 0.005,
        }

        await msg_repo.save(conv.id, MessageRole.ASSISTANT, complex_content)
        msgs = await msg_repo.list(conv.id)

        assert msgs[0].content == complex_content
