"""Unit tests for JSON serialization — focus on type transformations, not field passthrough."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from backend.domain.models import (
    ANONYMOUS_USER_ID,
    Conversation,
    Message,
    MessageRole,
    User,
)
from backend.routers.utils.serializers import serialize_conversation, serialize_message, serialize_user


def _ts() -> datetime:
    return datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


class TestSerializeUser:
    def test_converts_uuid_to_string(self):
        uid = uuid.uuid4()
        result = serialize_user(User(id=uid, email="x@x.com", display_name=None, created_at=_ts()))
        assert result["id"] == str(uid)
        assert isinstance(result["id"], str)

    def test_converts_datetime_to_iso_string(self):
        result = serialize_user(User(id=uuid.uuid4(), email="x@x.com", display_name=None, created_at=_ts()))
        assert result["created_at"] == "2025-06-15T12:00:00+00:00"


class TestSerializeConversation:
    def test_converts_uuid_and_datetime_fields(self):
        cid = uuid.uuid4()
        conv = Conversation(
            id=cid, user_id=ANONYMOUS_USER_ID, title="Chat",
            sdk_session_id=None, created_at=_ts(), updated_at=_ts(),
        )
        result = serialize_conversation(conv)

        assert result["id"] == str(cid)
        assert result["user_id"] == str(ANONYMOUS_USER_ID)
        assert isinstance(result["created_at"], str)
        assert isinstance(result["updated_at"], str)


class TestSerializeMessage:
    def test_role_enum_serialized_as_string(self):
        msg = Message(
            id=uuid.uuid4(), conversation_id=uuid.uuid4(),
            role=MessageRole.ASSISTANT, content={"text": "hi"},
            created_at=_ts(),
        )
        result = serialize_message(msg)
        assert result["role"] == "assistant"
        assert isinstance(result["role"], str)
