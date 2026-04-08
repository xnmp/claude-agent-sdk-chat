"""WebSocket integration tests — full FastAPI endpoint with fake dependencies.

Tests the complete pipeline: WebSocket → ChatSession → fake SDK → WS events,
without needing a real database or SDK subprocess.
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.domain.models import (
    MessageRole,
    ResultEvent,
    TextEvent,
    ThinkingEvent,
    ToolResultEvent,
    ToolUseEvent,
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
        assert saved[0].content["text"] == "hello"
        assert saved[1].role == MessageRole.ASSISTANT
        assert saved[1].content["text"] == "response"

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
