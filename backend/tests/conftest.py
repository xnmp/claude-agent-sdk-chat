"""Shared fixtures for backend tests."""

from __future__ import annotations

import pytest

from backend.domain.models import (
    ModelInfoEvent,
    ResultEvent,
    TextEvent,
    ThinkingEvent,
    ToolResultEvent,
    ToolUseEvent,
)
from backend.tests.fakes import (
    FakeConversationRepository,
    FakeMessageRepository,
    FakeSDKClient,
    FakeSDKClientFactory,
    FakeUserRepository,
)


@pytest.fixture
def user_repo() -> FakeUserRepository:
    return FakeUserRepository()


@pytest.fixture
def conv_repo() -> FakeConversationRepository:
    return FakeConversationRepository()


@pytest.fixture
def msg_repo() -> FakeMessageRepository:
    return FakeMessageRepository()


@pytest.fixture
def sample_sdk_events() -> list:
    """A realistic sequence of SDK events for a single turn."""
    return [
        ModelInfoEvent(model="claude-sonnet-4-20250514", usage={"input_tokens": 50, "output_tokens": 30}),
        ThinkingEvent(thinking="Let me read the file...", signature="sig123", message_id="msg-1"),
        ToolUseEvent(id="tool-1", name="Read", input={"file_path": "/tmp/test.py"}, message_id="msg-1"),
        ToolResultEvent(tool_use_id="tool-1", content="print('hello')", is_error=False),
        TextEvent(text="The file contains a hello world program.", message_id="msg-2"),
        ResultEvent(session_id="sess-1", duration_ms=1500, total_cost_usd=0.003, num_turns=1, is_error=False),
    ]


@pytest.fixture
def fake_sdk_client(sample_sdk_events: list) -> FakeSDKClient:
    return FakeSDKClient(events=sample_sdk_events)


@pytest.fixture
def sdk_factory(fake_sdk_client: FakeSDKClient) -> FakeSDKClientFactory:
    return FakeSDKClientFactory(client=fake_sdk_client)
