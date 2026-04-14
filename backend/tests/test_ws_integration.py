"""WebSocket integration tests — full FastAPI endpoint with fake dependencies.

Tests the complete pipeline: WebSocket → ChatSession → fake SDK → WS events,
without needing a real database or SDK subprocess.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.domain.models import (
    MessageRole,
    ResultEvent,
    SDKEvent,
    TextEvent,
    ThinkingEvent,
    ToolResultEvent,
    ToolUseEvent,
    text_blocks,
)
from backend.domain.ports import AppState
from backend.routers import ws
from backend.tests.fakes import (
    FakeConversationRepository,
    FakeMessageRepository,
    FakeSDKClient,
    FakeSDKClientFactory,
    FakeUserRepository,
)


def _create_app(sdk_events: list) -> tuple[FastAPI, FakeConversationRepository, FakeMessageRepository]:
    """Create a minimal FastAPI app with fake dependencies."""
    app = FastAPI()
    app.include_router(ws.router)

    conv_repo = FakeConversationRepository()
    msg_repo = FakeMessageRepository()
    app.state.deps = AppState(
        users=FakeUserRepository(),
        conversations=conv_repo,
        messages=msg_repo,
        sdk_factory=FakeSDKClientFactory(FakeSDKClient(events=sdk_events)),
    )
    return app, conv_repo, msg_repo


class TestWebSocketEndpoint:
    def test_sends_error_for_unknown_conversation(self):
        app, _, _ = _create_app([])
        client = TestClient(app)
        fake_id = str(uuid.uuid4())

        with client.websocket_connect(f"/api/ws/{fake_id}") as ws_conn:
            data = ws_conn.receive_json()
            assert data["type"] == "error"
            assert "not found" in data["message"].lower()

    def test_streams_assistant_response(self):
        events = [
            TextEvent(text="Hello!", message_id="m1"),
            ResultEvent(
                session_id="s1", duration_ms=100, total_cost_usd=0.001,
                num_turns=1, is_error=False,
            ),
        ]
        app, conv_repo, msg_repo = _create_app(events)
        client = TestClient(app)

        # Create conversation synchronously via the fake
        import asyncio
        conv = asyncio.get_event_loop().run_until_complete(conv_repo.create(title="Test"))

        with client.websocket_connect(f"/api/ws/{conv.id}") as ws_conn:
            ws_conn.send_json({"type": "user_message", "content": "hi"})

            # Should receive text + result events
            messages = []
            for _ in range(2):
                messages.append(ws_conn.receive_json())

            types = [m["type"] for m in messages]
            assert "assistant_text" in types
            assert "result" in types

            text_msg = next(m for m in messages if m["type"] == "assistant_text")
            assert text_msg["text"] == "Hello!"

    def test_full_turn_with_tool_use(self):
        events = [
            ThinkingEvent(thinking="analyzing...", signature="s1", message_id="m1"),
            ToolUseEvent(id="t1", name="Read", input={"file_path": "/x"}, message_id="m1"),
            ToolResultEvent(tool_use_id="t1", content="contents", is_error=False),
            TextEvent(text="Done.", message_id="m2"),
            ResultEvent(
                session_id="s1", duration_ms=500, total_cost_usd=0.01,
                num_turns=1, is_error=False,
            ),
        ]
        app, conv_repo, msg_repo = _create_app(events)
        client = TestClient(app)

        import asyncio
        conv = asyncio.get_event_loop().run_until_complete(conv_repo.create())

        with client.websocket_connect(f"/api/ws/{conv.id}") as ws_conn:
            ws_conn.send_json({"type": "user_message", "content": "read the file"})

            messages = []
            for _ in range(6):  # thinking, tool_use, tool_input, tool_result, text, result
                messages.append(ws_conn.receive_json())

            types = [m["type"] for m in messages]
            assert types == ["thinking", "tool_use", "tool_input", "tool_result", "assistant_text", "result"]

    def test_persists_messages_to_repository(self):
        events = [
            TextEvent(text="response", message_id="m1"),
            ResultEvent(
                session_id="s1", duration_ms=50, total_cost_usd=0.0,
                num_turns=1, is_error=False,
            ),
        ]
        app, conv_repo, msg_repo = _create_app(events)
        client = TestClient(app)

        import asyncio
        conv = asyncio.get_event_loop().run_until_complete(conv_repo.create())

        with client.websocket_connect(f"/api/ws/{conv.id}") as ws_conn:
            ws_conn.send_json({"type": "user_message", "content": "hello"})

            # Drain all messages
            for _ in range(2):
                ws_conn.receive_json()

        # Verify messages were persisted
        saved = asyncio.get_event_loop().run_until_complete(msg_repo.list(conv.id))
        assert len(saved) == 2
        assert saved[0].role == MessageRole.USER
        assert saved[0].content["text"] == "hello"  # type: ignore[typeddict-item]
        assert saved[1].role == MessageRole.ASSISTANT
        blocks = saved[1].content["blocks"]  # type: ignore[typeddict-item]
        assert text_blocks(blocks)[0]["text"] == "response"

    def test_interrupt_reaches_sdk_while_stream_is_in_flight(self):
        """Regression: interrupt frames sent mid-stream must be dispatched
        concurrently, not queued behind the SDK iteration.

        The fake client yields one event, then blocks its receive loop until
        interrupt() is called. Without concurrent receive-loop handling, the
        interrupt frame would sit in the WS buffer until the stream completed,
        causing the stream to block forever — and this test would deadlock.
        """

        class BlockingUntilInterruptedClient(FakeSDKClient):
            def __init__(self, before: list[SDKEvent], after: list[SDKEvent]) -> None:
                super().__init__(events=[])
                self._before = before
                self._after = after
                self._unblock = asyncio.Event()

            async def interrupt(self) -> None:
                self.interrupted = True
                self._unblock.set()

            async def receive_response(self) -> AsyncIterator[SDKEvent]:
                for event in self._before:
                    yield event
                await self._unblock.wait()
                for event in self._after:
                    yield event

        before: list[SDKEvent] = [TextEvent(text="partial", message_id="m1")]
        after: list[SDKEvent] = [
            ResultEvent(
                session_id="s1", duration_ms=10, total_cost_usd=0.0,
                num_turns=1, is_error=False,
            ),
        ]
        fake_client = BlockingUntilInterruptedClient(before, after)

        app = FastAPI()
        app.include_router(ws.router)
        conv_repo = FakeConversationRepository()
        msg_repo = FakeMessageRepository()
        app.state.deps = AppState(
            users=FakeUserRepository(),
            conversations=conv_repo,
            messages=msg_repo,
            sdk_factory=FakeSDKClientFactory(fake_client),
        )
        client = TestClient(app)
        conv = asyncio.get_event_loop().run_until_complete(conv_repo.create())

        with client.websocket_connect(f"/api/ws/{conv.id}") as ws_conn:
            ws_conn.send_json({"type": "user_message", "content": "go"})

            # First event streams before the blocking point.
            first = ws_conn.receive_json()
            assert first["type"] == "assistant_text"
            assert first["text"] == "partial"

            # Send interrupt while the stream is blocked inside receive_response.
            # Without the fix, the server's receive loop is trapped in `async for`
            # and never reads this frame, so the test would deadlock below.
            ws_conn.send_json({"type": "interrupt"})

            # After interrupt fires, the blocked stream unblocks and emits the
            # remaining result event.
            second = ws_conn.receive_json()
            assert second["type"] == "result"

        assert fake_client.interrupted is True

    def test_title_generated_only_on_first_turn(self, monkeypatch):
        """Regression: do_title() used to fire after every result event,
        burning a small-fast-model call per turn and overwriting the title.
        It must run exactly once per conversation — on the first user turn —
        and skip on later turns and on reconnects where the DB already has
        a title.
        """
        title_calls: list[tuple[str, str]] = []

        async def fake_generate_title(user_msg: str, asst_msg: str) -> str:
            title_calls.append((user_msg, asst_msg))
            return f"Title {len(title_calls)}"

        async def fake_generate_follow_ups(user_msg: str, asst_msg: str) -> list[str]:
            # Returning a non-empty list means a `suggestions` frame is sent,
            # which gives the test a deterministic "background tasks for this
            # turn have completed" signal to wait on.
            return ["q1"]

        monkeypatch.setattr(ws, "generate_title", fake_generate_title)
        monkeypatch.setattr(ws, "generate_follow_ups", fake_generate_follow_ups)

        events = [
            TextEvent(text="reply", message_id="m1"),
            ResultEvent(
                session_id="s1", duration_ms=10, total_cost_usd=0.0,
                num_turns=1, is_error=False,
            ),
        ]
        app, conv_repo, _ = _create_app(events)
        client = TestClient(app)

        loop = asyncio.get_event_loop()
        conv = loop.run_until_complete(conv_repo.create())  # title=None

        with client.websocket_connect(f"/api/ws/{conv.id}") as ws_conn:
            # Turn 1: stream (assistant_text, result) + background (title_update, suggestions) = 4 frames
            ws_conn.send_json({"type": "user_message", "content": "first"})
            turn1 = [ws_conn.receive_json() for _ in range(4)]

            # Turn 2: stream (assistant_text, result) + background (suggestions only) = 3 frames
            ws_conn.send_json({"type": "user_message", "content": "second"})
            turn2 = [ws_conn.receive_json() for _ in range(3)]

        # generate_title was called exactly once across both turns
        assert len(title_calls) == 1
        assert title_calls[0][0] == "first"

        # Turn 1 emitted exactly one title_update; turn 2 emitted none
        turn1_types = [m["type"] for m in turn1]
        turn2_types = [m["type"] for m in turn2]
        assert turn1_types.count("title_update") == 1
        assert turn2_types.count("title_update") == 0

        # DB still holds the first-turn title (no overwrite from turn 2)
        conv_after = loop.run_until_complete(conv_repo.get(conv.id))
        assert conv_after is not None
        assert conv_after.title == "Title 1"

    def test_title_generation_skipped_on_reconnect_when_already_titled(self, monkeypatch):
        """Regression: a fresh WS to a conversation that already has a title
        in the DB must NOT regenerate it on the first turn of the new session.
        The needs_title flag derives from the DB at WS connect time.
        """
        title_calls: list[tuple[str, str]] = []

        async def fake_generate_title(user_msg: str, asst_msg: str) -> str:
            title_calls.append((user_msg, asst_msg))
            return "Should Not Run"

        async def fake_generate_follow_ups(user_msg: str, asst_msg: str) -> list[str]:
            return ["q1"]

        monkeypatch.setattr(ws, "generate_title", fake_generate_title)
        monkeypatch.setattr(ws, "generate_follow_ups", fake_generate_follow_ups)

        events = [
            TextEvent(text="reply", message_id="m1"),
            ResultEvent(
                session_id="s1", duration_ms=10, total_cost_usd=0.0,
                num_turns=1, is_error=False,
            ),
        ]
        app, conv_repo, _ = _create_app(events)
        client = TestClient(app)

        loop = asyncio.get_event_loop()
        # Pre-existing title — simulates a reconnect after the title was
        # already generated in a previous session.
        conv = loop.run_until_complete(conv_repo.create(title="Existing Title"))

        with client.websocket_connect(f"/api/ws/{conv.id}") as ws_conn:
            ws_conn.send_json({"type": "user_message", "content": "hi"})
            # stream (assistant_text, result) + background (suggestions) = 3 frames
            frames = [ws_conn.receive_json() for _ in range(3)]

        assert len(title_calls) == 0
        assert "title_update" not in [m["type"] for m in frames]

        conv_after = loop.run_until_complete(conv_repo.get(conv.id))
        assert conv_after is not None
        assert conv_after.title == "Existing Title"

    def test_manual_rename_during_first_turn_is_not_overwritten(self, monkeypatch):
        """Race protection: the user can manually rename the conversation
        between WS connect (where needs_title=True is cached) and the first
        turn firing. do_title() must re-check the DB and skip if the title
        has been set in the interim.
        """
        title_calls: list[tuple[str, str]] = []

        async def fake_generate_title(user_msg: str, asst_msg: str) -> str:
            title_calls.append((user_msg, asst_msg))
            return "Auto Title"

        async def fake_generate_follow_ups(user_msg: str, asst_msg: str) -> list[str]:
            return ["q1"]

        monkeypatch.setattr(ws, "generate_title", fake_generate_title)
        monkeypatch.setattr(ws, "generate_follow_ups", fake_generate_follow_ups)

        events = [
            TextEvent(text="reply", message_id="m1"),
            ResultEvent(
                session_id="s1", duration_ms=10, total_cost_usd=0.0,
                num_turns=1, is_error=False,
            ),
        ]
        app, conv_repo, _ = _create_app(events)
        client = TestClient(app)

        loop = asyncio.get_event_loop()
        # Conversation starts untitled — needs_title will be True at WS connect.
        conv = loop.run_until_complete(conv_repo.create())

        with client.websocket_connect(f"/api/ws/{conv.id}") as ws_conn:
            # Simulate the user manually renaming via the REST API AFTER the
            # WS connect cached needs_title=True but BEFORE the first turn fires.
            loop.run_until_complete(conv_repo.update(conv.id, title="My Title"))

            ws_conn.send_json({"type": "user_message", "content": "hi"})
            # stream (assistant_text, result) + background (suggestions only,
            # because do_title() should bail at the DB recheck) = 3 frames
            frames = [ws_conn.receive_json() for _ in range(3)]

        # do_title's DB recheck saw "My Title" and skipped before calling
        # generate_title — no LLM call, no title_update frame, no overwrite.
        assert len(title_calls) == 0
        assert "title_update" not in [m["type"] for m in frames]

        conv_after = loop.run_until_complete(conv_repo.get(conv.id))
        assert conv_after is not None
        assert conv_after.title == "My Title"

    def test_empty_message_is_ignored(self):
        events = [
            TextEvent(text="hi", message_id="m1"),
            ResultEvent(
                session_id="s1", duration_ms=10, total_cost_usd=0.0,
                num_turns=1, is_error=False,
            ),
        ]
        app, conv_repo, _ = _create_app(events)
        client = TestClient(app)

        import asyncio
        conv = asyncio.get_event_loop().run_until_complete(conv_repo.create())

        with client.websocket_connect(f"/api/ws/{conv.id}") as ws_conn:
            # Send empty/whitespace messages — should be ignored
            ws_conn.send_json({"type": "user_message", "content": ""})
            ws_conn.send_json({"type": "user_message", "content": "   "})

            # Send a real message
            ws_conn.send_json({"type": "user_message", "content": "hello"})

            # Should only get response for the real message
            messages = []
            for _ in range(2):
                messages.append(ws_conn.receive_json())
            types = [m["type"] for m in messages]
            assert "assistant_text" in types
