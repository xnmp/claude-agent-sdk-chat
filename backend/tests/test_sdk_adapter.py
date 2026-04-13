"""Unit tests for SDK adapter — translating claude_agent_sdk types to domain events.

The adapter runs the SDK in `include_partial_messages=True` mode, so:
  - text, thinking, and tool_use content blocks are driven by `StreamEvent`
    (the raw Anthropic API streaming protocol)
  - the buffered `AssistantMessage` is used only for `model`/`usage` metadata
    and the rare synthetic `ToolResultBlock`
  - tool inputs are buffered from `input_json_delta` fragments and parsed on
    `content_block_stop`
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from claude_agent_sdk import (
    AssistantMessage,
    StreamEvent,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from backend.domain.models import (
    ModelInfoEvent,
    TextBlockStartEvent,
    TextDeltaEvent,
    ThinkingBlockStartEvent,
    ThinkingDeltaEvent,
    ToolResultEvent,
    ToolUseEvent,
)
from backend.infra.sdk_manager import (
    ClaudeSDKClientAdapter,
    _SANDBOX_SETTINGS,
    _translate_assistant_meta,
    _translate_user,
)


def _stream_event(event: dict[str, Any]) -> StreamEvent:
    return StreamEvent(uuid="", session_id="", event=event, parent_tool_use_id=None)


def _make_adapter() -> ClaudeSDKClientAdapter:
    return ClaudeSDKClientAdapter(client=MagicMock(), created_files=set())


class TestSandboxSettings:
    def test_disallows_dangerous_sandbox_bypass(self):
        # The agent must never be able to invoke Bash with
        # dangerouslyDisableSandbox: True. The SDK enforces this when
        # allowUnsandboxedCommands is False.
        assert _SANDBOX_SETTINGS["allowUnsandboxedCommands"] is False

    def test_sandbox_is_enabled(self):
        assert _SANDBOX_SETTINGS["enabled"] is True


class TestTranslateAssistantMeta:
    """The buffered AssistantMessage is now used only for metadata and tool
    results. Text/thinking/tool_use blocks should be silently skipped — they
    come from the streaming path."""

    def test_model_info_emitted_when_model_present(self):
        msg = AssistantMessage(
            content=[TextBlock(text="hi")],
            model="claude-sonnet-4-20250514",
            usage={"input_tokens": 100, "output_tokens": 20},
        )
        events = _translate_assistant_meta(msg)

        model_events = [e for e in events if isinstance(e, ModelInfoEvent)]
        assert len(model_events) == 1
        assert model_events[0].model == "claude-sonnet-4-20250514"
        assert model_events[0].usage == {"input_tokens": 100, "output_tokens": 20}

    def test_no_model_info_when_both_empty(self):
        msg = AssistantMessage(
            content=[TextBlock(text="hi")],
            model="",
        )
        events = _translate_assistant_meta(msg)

        assert all(not isinstance(e, ModelInfoEvent) for e in events)

    def test_text_blocks_are_not_translated_from_assistant_message(self):
        """Text blocks come from the stream path; emitting them here would
        duplicate the text rendered from `text_delta` events."""
        msg = AssistantMessage(
            content=[TextBlock(text="Hello world")],
            model="claude-sonnet-4-20250514",
            message_id="msg-2",
        )
        events = _translate_assistant_meta(msg)

        # Only ModelInfoEvent — no TextEvent / TextBlockStartEvent / etc.
        assert [type(e).__name__ for e in events] == ["ModelInfoEvent"]

    def test_thinking_and_tool_use_blocks_are_skipped(self):
        msg = AssistantMessage(
            content=[
                ThinkingBlock(thinking="hmm", signature="s1"),
                ToolUseBlock(id="tu-1", name="Read", input={"file_path": "/x"}),
            ],
            model="claude-sonnet-4-20250514",
        )
        events = _translate_assistant_meta(msg)

        # Only ModelInfoEvent
        assert [type(e).__name__ for e in events] == ["ModelInfoEvent"]

    def test_tool_result_block_is_still_translated(self):
        """Tool result blocks on AssistantMessages are rare but supported —
        they survive even though text/tool_use blocks are skipped."""
        msg = AssistantMessage(
            content=[ToolResultBlock(tool_use_id="tu-1", content="contents", is_error=False)],
            model="claude-sonnet-4-20250514",
        )
        events = _translate_assistant_meta(msg)

        result_events = [e for e in events if isinstance(e, ToolResultEvent)]
        assert len(result_events) == 1
        assert result_events[0].tool_use_id == "tu-1"
        assert result_events[0].content == "contents"
        assert result_events[0].is_error is False

    def test_non_string_tool_result_content_converted(self):
        msg = AssistantMessage(
            content=[ToolResultBlock(tool_use_id="tu-1", content=["chunk1", "chunk2"])],  # type: ignore[arg-type]
            model="claude-sonnet-4-20250514",
        )
        events = _translate_assistant_meta(msg)

        result_events = [e for e in events if isinstance(e, ToolResultEvent)]
        assert isinstance(result_events[0].content, str)


class TestTranslateUser:
    def test_tool_result_blocks(self):
        msg = UserMessage(
            content=[
                ToolResultBlock(tool_use_id="tu-1", content="output text", is_error=False),
                ToolResultBlock(tool_use_id="tu-2", content="error msg", is_error=True),
            ],
        )
        events = _translate_user(msg)

        assert len(events) == 2
        assert isinstance(events[0], ToolResultEvent)
        assert isinstance(events[1], ToolResultEvent)
        assert events[0].tool_use_id == "tu-1"
        assert events[0].is_error is False
        assert events[1].tool_use_id == "tu-2"
        assert events[1].is_error is True

    def test_string_content_produces_no_events(self):
        msg = UserMessage(content="plain text input")
        events = _translate_user(msg)

        assert events == []

    def test_empty_list_produces_no_events(self):
        msg = UserMessage(content=[])
        events = _translate_user(msg)

        assert events == []


class TestStreamEventHandling:
    """The streaming path is where text/thinking/tool_use are now produced."""

    def test_message_start_resets_state_and_records_message_id(self):
        adapter = _make_adapter()
        adapter._open_blocks = {99: {"type": "text"}}  # leftover from a prior message

        adapter._handle_stream_event(_stream_event({
            "type": "message_start",
            "message": {"id": "msg-streaming-1"},
        }))

        assert adapter._current_message_id == "msg-streaming-1"
        assert adapter._open_blocks == {}

    def test_text_block_start_emits_text_block_start_event(self):
        adapter = _make_adapter()
        adapter._handle_stream_event(_stream_event({
            "type": "message_start", "message": {"id": "m1"},
        }))

        events = adapter._handle_stream_event(_stream_event({
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "text", "text": ""},
        }))

        assert len(events) == 1
        assert isinstance(events[0], TextBlockStartEvent)
        assert events[0].block_index == 0
        assert events[0].message_id == "m1"

    def test_text_delta_emits_text_delta_event(self):
        adapter = _make_adapter()
        adapter._handle_stream_event(_stream_event({
            "type": "message_start", "message": {"id": "m1"},
        }))
        adapter._handle_stream_event(_stream_event({
            "type": "content_block_start", "index": 0,
            "content_block": {"type": "text", "text": ""},
        }))

        events = adapter._handle_stream_event(_stream_event({
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "Hello"},
        }))

        assert len(events) == 1
        assert isinstance(events[0], TextDeltaEvent)
        assert events[0].text == "Hello"
        assert events[0].block_index == 0

    def test_thinking_block_start_and_delta(self):
        adapter = _make_adapter()
        adapter._handle_stream_event(_stream_event({
            "type": "message_start", "message": {"id": "m1"},
        }))
        start = adapter._handle_stream_event(_stream_event({
            "type": "content_block_start", "index": 0,
            "content_block": {"type": "thinking"},
        }))
        delta = adapter._handle_stream_event(_stream_event({
            "type": "content_block_delta", "index": 0,
            "delta": {"type": "thinking_delta", "thinking": "let me reason"},
        }))

        assert isinstance(start[0], ThinkingBlockStartEvent)
        assert isinstance(delta[0], ThinkingDeltaEvent)
        assert delta[0].thinking == "let me reason"

    def test_tool_use_buffers_input_json_and_emits_on_stop(self):
        """Tool input arrives as `input_json_delta` fragments. The adapter
        buffers them and emits one ToolUseEvent (with parsed input) when the
        block stops."""
        adapter = _make_adapter()
        adapter._handle_stream_event(_stream_event({
            "type": "message_start", "message": {"id": "m1"},
        }))

        # Block start gives us id and name but NOT input
        start = adapter._handle_stream_event(_stream_event({
            "type": "content_block_start", "index": 0,
            "content_block": {"type": "tool_use", "id": "tu_1", "name": "Read", "input": {}},
        }))
        assert start == []  # nothing emitted yet — input is still streaming

        # Two input_json_delta fragments combine into '{"file_path":"/tmp/x"}'
        adapter._handle_stream_event(_stream_event({
            "type": "content_block_delta", "index": 0,
            "delta": {"type": "input_json_delta", "partial_json": '{"file_path"'},
        }))
        adapter._handle_stream_event(_stream_event({
            "type": "content_block_delta", "index": 0,
            "delta": {"type": "input_json_delta", "partial_json": ':"/tmp/x"}'},
        }))

        # content_block_stop fires the ToolUseEvent with parsed input
        events = adapter._handle_stream_event(_stream_event({
            "type": "content_block_stop", "index": 0,
        }))
        assert len(events) == 1
        assert isinstance(events[0], ToolUseEvent)
        assert events[0].id == "tu_1"
        assert events[0].name == "Read"
        assert events[0].input == {"file_path": "/tmp/x"}

    def test_tool_use_with_no_input_emits_empty_dict(self):
        adapter = _make_adapter()
        adapter._handle_stream_event(_stream_event({
            "type": "message_start", "message": {"id": "m1"},
        }))
        adapter._handle_stream_event(_stream_event({
            "type": "content_block_start", "index": 0,
            "content_block": {"type": "tool_use", "id": "tu_1", "name": "NoArgs", "input": {}},
        }))
        events = adapter._handle_stream_event(_stream_event({
            "type": "content_block_stop", "index": 0,
        }))
        assert events[0].input == {}  # type: ignore[union-attr]

    def test_tool_use_with_malformed_json_falls_back_to_empty(self):
        """If the SDK ever delivers JSON we can't parse, don't crash the stream."""
        adapter = _make_adapter()
        adapter._handle_stream_event(_stream_event({
            "type": "message_start", "message": {"id": "m1"},
        }))
        adapter._handle_stream_event(_stream_event({
            "type": "content_block_start", "index": 0,
            "content_block": {"type": "tool_use", "id": "tu_1", "name": "Read", "input": {}},
        }))
        adapter._handle_stream_event(_stream_event({
            "type": "content_block_delta", "index": 0,
            "delta": {"type": "input_json_delta", "partial_json": "{not valid"},
        }))
        events = adapter._handle_stream_event(_stream_event({
            "type": "content_block_stop", "index": 0,
        }))
        assert events[0].input == {}  # type: ignore[union-attr]

    def test_message_start_uuid_fallback_when_no_inner_id(self):
        """If the message_start payload omits message.id, fall back to the
        StreamEvent's uuid so we still have a stable identifier."""
        adapter = _make_adapter()
        adapter._handle_stream_event(StreamEvent(
            uuid="fallback-uuid", session_id="", event={"type": "message_start", "message": {}},
            parent_tool_use_id=None,
        ))
        assert adapter._current_message_id == "fallback-uuid"

    def test_signature_delta_does_not_emit_event(self):
        """Signatures are buffered but not surfaced — the UI doesn't use them."""
        adapter = _make_adapter()
        adapter._handle_stream_event(_stream_event({
            "type": "message_start", "message": {"id": "m1"},
        }))
        adapter._handle_stream_event(_stream_event({
            "type": "content_block_start", "index": 0,
            "content_block": {"type": "thinking"},
        }))
        events = adapter._handle_stream_event(_stream_event({
            "type": "content_block_delta", "index": 0,
            "delta": {"type": "signature_delta", "signature": "sig123"},
        }))
        assert events == []
