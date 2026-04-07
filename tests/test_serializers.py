"""Unit tests for JSON serialization of domain models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from backend.models import (
    ANONYMOUS_USER_ID,
    Conversation,
    Message,
    MessageRole,
    User,
)
from backend.serializers import serialize_conversation, serialize_message, serialize_user


def _ts() -> datetime:
    return datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


class TestSerializeUser:
    def test_converts_uuid_and_datetime(self):
        user = User(id=uuid.uuid4(), email="test@example.com", display_name="Test", created_at=_ts())
        result = serialize_user(user)

        assert result["id"] == str(user.id)
        assert result["email"] == "test@example.com"
        assert result["display_name"] == "Test"
        assert result["created_at"] == "2025-06-15T12:00:00+00:00"

    def test_null_display_name(self):
        user = User(id=uuid.uuid4(), email="x@x.com", display_name=None, created_at=_ts())
        result = serialize_user(user)

        assert result["display_name"] is None


class TestSerializeConversation:
    def test_converts_all_fields(self):
        cid = uuid.uuid4()
        conv = Conversation(
            id=cid, user_id=ANONYMOUS_USER_ID, title="My Chat",
            sdk_session_id="sess-1", created_at=_ts(), updated_at=_ts(),
        )
        result = serialize_conversation(conv)

        assert result["id"] == str(cid)
        assert result["user_id"] == str(ANONYMOUS_USER_ID)
        assert result["title"] == "My Chat"
        assert result["sdk_session_id"] == "sess-1"
        assert isinstance(result["created_at"], str)
        assert isinstance(result["updated_at"], str)

    def test_null_title_and_session(self):
        conv = Conversation(
            id=uuid.uuid4(), user_id=ANONYMOUS_USER_ID, title=None,
            sdk_session_id=None, created_at=_ts(), updated_at=_ts(),
        )
        result = serialize_conversation(conv)

        assert result["title"] is None
        assert result["sdk_session_id"] is None


class TestSerializeMessage:
    def test_user_message(self):
        msg = Message(
            id=uuid.uuid4(), conversation_id=uuid.uuid4(),
            role=MessageRole.USER, content={"text": "hello"},
            created_at=_ts(),
        )
        result = serialize_message(msg)

        assert result["role"] == "user"
        assert result["content"] == {"text": "hello"}
        assert isinstance(result["id"], str)
        assert isinstance(result["conversation_id"], str)

    def test_assistant_message(self):
        msg = Message(
            id=uuid.uuid4(), conversation_id=uuid.uuid4(),
            role=MessageRole.ASSISTANT,
            content={
                "thinking": [], "tool_calls": [], "text": "response",
                "model": "claude", "usage": {}, "duration_ms": 100, "total_cost_usd": 0.01,
            },
            created_at=_ts(),
        )
        result = serialize_message(msg)

        assert result["role"] == "assistant"
        assert result["content"]["text"] == "response"
        assert result["content"]["duration_ms"] == 100
