"""Unit tests for chat orchestration — ChatSession with fake dependencies."""

from __future__ import annotations

import pytest

from backend.domain.chat import ChatSession, ConversationNotFoundError
from backend.domain.models import (
    AssistantMessageContent,
    MessageRole,
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
)


async def _collect_events(session: ChatSession, content: str) -> list:
    events = []
    async for event in session.handle_user_message(content):
        events.append(event)
    return events


class TestChatSessionInitialize:
    async def test_raises_when_conversation_not_found(
        self, conv_repo: FakeConversationRepository, msg_repo: FakeMessageRepository,
        sdk_factory: FakeSDKClientFactory,
    ):
        import uuid
        session = ChatSession(
            conversation_id=uuid.uuid4(),
            conversations=conv_repo,
            messages=msg_repo,
            sdk_factory=sdk_factory,
        )
        with pytest.raises(ConversationNotFoundError):
            await session.initialize()

    async def test_succeeds_for_existing_conversation(
        self, conv_repo: FakeConversationRepository, msg_repo: FakeMessageRepository,
        sdk_factory: FakeSDKClientFactory,
    ):
        conv = await conv_repo.create(title="Test")
        session = ChatSession(
            conversation_id=conv.id,
            conversations=conv_repo,
            messages=msg_repo,
            sdk_factory=sdk_factory,
        )
        await session.initialize()  # Should not raise


class TestChatSessionHandleMessage:
    async def _make_session(
        self, conv_repo, msg_repo, sdk_factory,
    ) -> ChatSession:
        conv = await conv_repo.create()
        session = ChatSession(
            conversation_id=conv.id,
            conversations=conv_repo,
            messages=msg_repo,
            sdk_factory=sdk_factory,
        )
        await session.initialize()
        return session

    async def test_persists_user_message(
        self, conv_repo: FakeConversationRepository, msg_repo: FakeMessageRepository,
    ):
        factory = FakeSDKClientFactory(FakeSDKClient(events=[
            TextEvent(text="hi", message_id="m1"),
            ResultEvent(session_id="s1", duration_ms=100, total_cost_usd=0.001, num_turns=1, is_error=False),
        ]))
        session = await self._make_session(conv_repo, msg_repo, factory)
        await _collect_events(session, "hello")

        msgs = await msg_repo.list(session.conversation_id)
        user_msgs = [m for m in msgs if m.role == MessageRole.USER]
        assert len(user_msgs) == 1
        assert user_msgs[0].content["text"] == "hello"

    async def test_persists_assistant_turn_on_result(
        self, conv_repo: FakeConversationRepository, msg_repo: FakeMessageRepository,
        sample_sdk_events: list,
    ):
        factory = FakeSDKClientFactory(FakeSDKClient(events=sample_sdk_events))
        session = await self._make_session(conv_repo, msg_repo, factory)
        await _collect_events(session, "read the file")

        msgs = await msg_repo.list(session.conversation_id)
        assistant_msgs = [m for m in msgs if m.role == MessageRole.ASSISTANT]
        assert len(assistant_msgs) == 1
        content: AssistantMessageContent = assistant_msgs[0].content  # type: ignore[assignment]
        assert content["text"] == "The file contains a hello world program."
        assert content["duration_ms"] == 1500
        assert len(content["tool_calls"]) == 1

    async def test_yields_domain_events_in_order(
        self, conv_repo: FakeConversationRepository, msg_repo: FakeMessageRepository,
        sample_sdk_events: list,
    ):
        factory = FakeSDKClientFactory(FakeSDKClient(events=sample_sdk_events))
        session = await self._make_session(conv_repo, msg_repo, factory)
        events = await _collect_events(session, "do stuff")

        types = [type(e).__name__ for e in events]
        assert types == [
            "ModelInfoEvent", "ThinkingEvent", "ToolUseEvent",
            "ToolResultEvent", "TextEvent", "ResultEvent",
        ]

    async def test_auto_titles_conversation_from_first_message(
        self, conv_repo: FakeConversationRepository, msg_repo: FakeMessageRepository,
    ):
        factory = FakeSDKClientFactory(FakeSDKClient(events=[
            TextEvent(text="ok", message_id="m1"),
            ResultEvent(session_id="s1", duration_ms=50, total_cost_usd=0.0, num_turns=1, is_error=False),
        ]))
        session = await self._make_session(conv_repo, msg_repo, factory)
        await _collect_events(session, "What is the meaning of life?")

        conv = await conv_repo.get(session.conversation_id)
        assert conv is not None
        assert conv.title == "What is the meaning of life?"

    async def test_creates_sdk_client_lazily_on_first_message(
        self, conv_repo: FakeConversationRepository, msg_repo: FakeMessageRepository,
    ):
        client = FakeSDKClient(events=[
            ResultEvent(session_id="s1", duration_ms=10, total_cost_usd=0.0, num_turns=1, is_error=False),
        ])
        factory = FakeSDKClientFactory(client)
        session = await self._make_session(conv_repo, msg_repo, factory)

        assert not client.connected
        await _collect_events(session, "hi")
        assert client.connected
        assert client.queries == ["hi"]

    async def test_assigns_sdk_session_id_on_first_message(
        self, conv_repo: FakeConversationRepository, msg_repo: FakeMessageRepository,
    ):
        factory = FakeSDKClientFactory(FakeSDKClient(events=[
            ResultEvent(session_id="s1", duration_ms=10, total_cost_usd=0.0, num_turns=1, is_error=False),
        ]))
        session = await self._make_session(conv_repo, msg_repo, factory)
        await _collect_events(session, "test")

        conv = await conv_repo.get(session.conversation_id)
        assert conv is not None
        assert conv.sdk_session_id is not None


class TestChatSessionCost:
    async def _make_session(self, conv_repo, msg_repo, sdk_factory):
        conv = await conv_repo.create()
        session = ChatSession(
            conversation_id=conv.id,
            conversations=conv_repo,
            messages=msg_repo,
            sdk_factory=sdk_factory,
        )
        await session.initialize()
        return session

    async def test_converts_cumulative_cost_to_per_message(
        self, conv_repo: FakeConversationRepository, msg_repo: FakeMessageRepository,
    ):
        """SDK reports cumulative session cost; we should store per-message cost."""
        client = FakeSDKClient(events=[
            TextEvent(text="hi", message_id="m1"),
            ResultEvent(session_id="s1", duration_ms=100, total_cost_usd=0.10, num_turns=1, is_error=False),
        ])
        factory = FakeSDKClientFactory(client)
        session = await self._make_session(conv_repo, msg_repo, factory)

        # First message: cumulative 0.10
        await _collect_events(session, "hello")

        # Second message: cumulative 0.13 (per-message should be 0.03)
        client._events = [
            TextEvent(text="bye", message_id="m2"),
            ResultEvent(session_id="s1", duration_ms=50, total_cost_usd=0.13, num_turns=2, is_error=False),
        ]
        await _collect_events(session, "goodbye")

        msgs = await msg_repo.list(session.conversation_id)
        assistant_msgs = [m for m in msgs if m.role == MessageRole.ASSISTANT]
        assert len(assistant_msgs) == 2
        cost_0: AssistantMessageContent = assistant_msgs[0].content  # type: ignore[assignment]
        cost_1: AssistantMessageContent = assistant_msgs[1].content  # type: ignore[assignment]
        assert cost_0["total_cost_usd"] == pytest.approx(0.10)
        assert cost_1["total_cost_usd"] == pytest.approx(0.03)

    async def test_yielded_result_event_has_per_message_cost(
        self, conv_repo: FakeConversationRepository, msg_repo: FakeMessageRepository,
    ):
        """The ResultEvent yielded to callers should use per-message cost."""
        client = FakeSDKClient(events=[
            TextEvent(text="hi", message_id="m1"),
            ResultEvent(session_id="s1", duration_ms=100, total_cost_usd=0.10, num_turns=1, is_error=False),
        ])
        factory = FakeSDKClientFactory(client)
        session = await self._make_session(conv_repo, msg_repo, factory)
        await _collect_events(session, "hello")

        # Second message
        client._events = [
            TextEvent(text="bye", message_id="m2"),
            ResultEvent(session_id="s1", duration_ms=50, total_cost_usd=0.13, num_turns=2, is_error=False),
        ]
        events = await _collect_events(session, "goodbye")

        result_events = [e for e in events if isinstance(e, ResultEvent)]
        assert len(result_events) == 1
        assert result_events[0].total_cost_usd == pytest.approx(0.03)


class TestChatSessionInterrupt:
    async def test_interrupt_calls_client(
        self, conv_repo: FakeConversationRepository, msg_repo: FakeMessageRepository,
    ):
        client = FakeSDKClient(events=[
            ResultEvent(session_id="s1", duration_ms=10, total_cost_usd=0.0, num_turns=1, is_error=False),
        ])
        factory = FakeSDKClientFactory(client)
        conv = await conv_repo.create()
        session = ChatSession(
            conversation_id=conv.id,
            conversations=conv_repo,
            messages=msg_repo,
            sdk_factory=factory,
        )
        await session.initialize()
        await _collect_events(session, "start")

        await session.handle_interrupt()
        assert client.interrupted

    async def test_interrupt_before_client_created_is_noop(
        self, conv_repo: FakeConversationRepository, msg_repo: FakeMessageRepository,
        sdk_factory: FakeSDKClientFactory,
    ):
        conv = await conv_repo.create()
        session = ChatSession(
            conversation_id=conv.id,
            conversations=conv_repo,
            messages=msg_repo,
            sdk_factory=sdk_factory,
        )
        await session.initialize()
        # Should not raise even though no client exists
        await session.handle_interrupt()


class TestChatSessionCleanup:
    async def test_cleanup_removes_sdk_client(
        self, conv_repo: FakeConversationRepository, msg_repo: FakeMessageRepository,
    ):
        factory = FakeSDKClientFactory(FakeSDKClient(events=[
            ResultEvent(session_id="s1", duration_ms=10, total_cost_usd=0.0, num_turns=1, is_error=False),
        ]))
        conv = await conv_repo.create()
        session = ChatSession(
            conversation_id=conv.id,
            conversations=conv_repo,
            messages=msg_repo,
            sdk_factory=factory,
        )
        await session.initialize()
        await _collect_events(session, "hi")
        await session.cleanup()

        assert len(factory._removed) == 1
