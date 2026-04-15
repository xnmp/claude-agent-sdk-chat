"""Unit tests for SDK adapter — translating claude_agent_sdk types to domain events.

The adapter runs the SDK in `include_partial_messages=True` mode. Normally:

- text, thinking, and tool_use content blocks are driven by `StreamEvent`
  (the raw Anthropic API streaming protocol)
- the buffered `AssistantMessage` is used mainly for `model`/`usage` metadata

But on some models the stream goes silent after a thinking block's deltas
and the final assistant content only arrives on the buffered
`AssistantMessage`. The adapter reconciles: for each buffered content block
it checks whether the stream path already emitted equivalent events (via
per-message flags) and, if not, emits the block directly as a `TextEvent` /
`ThinkingEvent` / `ToolUseEvent`.

Start events (`TextBlockStartEvent` / `ThinkingBlockStartEvent`) are deferred
until the first corresponding delta arrives so empty text/thinking blocks
(start immediately followed by stop, no deltas) don't leak empty bubbles
into the UI.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

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
    TextEvent,
    ThinkingBlockStartEvent,
    ThinkingDeltaEvent,
    ThinkingEvent,
    ToolResultEvent,
    ToolUseEvent,
)
from backend.infra.sdk_adapter import ClaudeSDKClientAdapter, _translate_user
from backend.infra.sdk_manager import _SANDBOX_SETTINGS


def _stream_event(event: dict[str, Any]) -> StreamEvent:
    return StreamEvent(uuid="", session_id="", event=event, parent_tool_use_id=None)


def _make_adapter() -> ClaudeSDKClientAdapter:
    return ClaudeSDKClientAdapter(client=MagicMock(), created_files=set())


def _start_message(adapter: ClaudeSDKClientAdapter, message_id: str = "m1") -> None:
    """Helper — drive the adapter through a message_start event."""
    adapter._handle_stream_event(_stream_event({
        "type": "message_start", "message": {"id": message_id},
    }))


class TestSandboxSettings:
    def test_disallows_dangerous_sandbox_bypass(self):
        # The agent must never be able to invoke Bash with
        # dangerouslyDisableSandbox: True. The SDK enforces this when
        # allowUnsandboxedCommands is False.
        assert _SANDBOX_SETTINGS["allowUnsandboxedCommands"] is False

    def test_sandbox_is_enabled(self):
        assert _SANDBOX_SETTINGS["enabled"] is True


class TestTranslateAssistantMeta:
    """Buffered AssistantMessage translation.

    The adapter reconciles each block in ``msg.content`` against what the
    stream path already produced for the current message. Blocks that the
    stream covered are skipped (they'd duplicate); blocks it didn't cover
    are emitted so the assistant's output still reaches the UI.
    """

    def test_model_info_emitted_when_model_present(self):
        adapter = _make_adapter()
        msg = AssistantMessage(
            content=[],
            model="claude-sonnet-4-20250514",
            usage={"input_tokens": 100, "output_tokens": 20},
        )
        events = adapter._translate_assistant_meta(msg)

        model_events = [e for e in events if isinstance(e, ModelInfoEvent)]
        assert len(model_events) == 1
        assert model_events[0].model == "claude-sonnet-4-20250514"
        assert model_events[0].usage == {"input_tokens": 100, "output_tokens": 20}

    def test_no_model_info_when_both_empty(self):
        adapter = _make_adapter()
        msg = AssistantMessage(content=[], model="")
        events = adapter._translate_assistant_meta(msg)

        assert all(not isinstance(e, ModelInfoEvent) for e in events)

    def test_text_block_skipped_when_stream_already_produced_text(self):
        """Happy path: stream delivered text deltas, buffered TextBlock is
        a duplicate and should be suppressed."""
        adapter = _make_adapter()
        _start_message(adapter)
        # Simulate the stream having emitted a text delta for this message
        adapter._handle_stream_event(_stream_event({
            "type": "content_block_start", "index": 0,
            "content_block": {"type": "text", "text": ""},
        }))
        adapter._handle_stream_event(_stream_event({
            "type": "content_block_delta", "index": 0,
            "delta": {"type": "text_delta", "text": "Hello world"},
        }))

        msg = AssistantMessage(
            content=[TextBlock(text="Hello world")],
            model="claude-sonnet-4-20250514",
        )
        events = adapter._translate_assistant_meta(msg)

        # Only ModelInfoEvent — no TextEvent, because the stream already
        # produced the text and the accumulator would double-count.
        assert [type(e).__name__ for e in events] == ["ModelInfoEvent"]

    def test_text_block_emitted_when_stream_produced_no_text(self):
        """Broken-stream path: no text deltas arrived, so the buffered
        TextBlock must be forwarded or the user never sees the answer."""
        adapter = _make_adapter()
        _start_message(adapter)
        # Stream only produced thinking; no text deltas
        adapter._handle_stream_event(_stream_event({
            "type": "content_block_start", "index": 0,
            "content_block": {"type": "thinking"},
        }))
        adapter._handle_stream_event(_stream_event({
            "type": "content_block_delta", "index": 0,
            "delta": {"type": "thinking_delta", "thinking": "reasoning..."},
        }))

        msg = AssistantMessage(
            content=[TextBlock(text="final answer")],
            model="claude-sonnet-4-20250514",
        )
        events = adapter._translate_assistant_meta(msg)

        text_events = [e for e in events if isinstance(e, TextEvent)]
        assert len(text_events) == 1
        assert text_events[0].text == "final answer"
        assert text_events[0].message_id == "m1"

    def test_thinking_block_skipped_when_stream_produced_thinking(self):
        adapter = _make_adapter()
        _start_message(adapter)
        adapter._handle_stream_event(_stream_event({
            "type": "content_block_start", "index": 0,
            "content_block": {"type": "thinking"},
        }))
        adapter._handle_stream_event(_stream_event({
            "type": "content_block_delta", "index": 0,
            "delta": {"type": "thinking_delta", "thinking": "streamed reasoning"},
        }))

        msg = AssistantMessage(
            content=[ThinkingBlock(thinking="buffered paraphrase", signature="sig")],
            model="m",
        )
        events = adapter._translate_assistant_meta(msg)

        assert not any(isinstance(e, ThinkingEvent) for e in events)

    def test_thinking_block_emitted_when_stream_produced_no_thinking(self):
        adapter = _make_adapter()
        _start_message(adapter)

        msg = AssistantMessage(
            content=[ThinkingBlock(thinking="buffered-only", signature="sig1")],
            model="m",
        )
        events = adapter._translate_assistant_meta(msg)

        thinking_events = [e for e in events if isinstance(e, ThinkingEvent)]
        assert len(thinking_events) == 1
        assert thinking_events[0].thinking == "buffered-only"
        assert thinking_events[0].signature == "sig1"

    def test_tool_use_block_skipped_when_stream_already_emitted_same_id(self):
        """Happy path: tool_use came through stream events, buffered block
        is a duplicate keyed by id."""
        adapter = _make_adapter()
        _start_message(adapter)
        # Drive a full stream tool_use through to completion
        adapter._handle_stream_event(_stream_event({
            "type": "content_block_start", "index": 0,
            "content_block": {"type": "tool_use", "id": "tu-1", "name": "Read", "input": {}},
        }))
        adapter._handle_stream_event(_stream_event({
            "type": "content_block_delta", "index": 0,
            "delta": {"type": "input_json_delta", "partial_json": '{"file_path":"/x"}'},
        }))
        adapter._handle_stream_event(_stream_event({
            "type": "content_block_stop", "index": 0,
        }))

        msg = AssistantMessage(
            content=[ToolUseBlock(id="tu-1", name="Read", input={"file_path": "/x"})],
            model="m",
        )
        events = adapter._translate_assistant_meta(msg)

        assert not any(isinstance(e, ToolUseEvent) for e in events)

    def test_tool_use_not_duplicated_when_buffered_arrives_before_stream_stop(self):
        """Ordering-bug regression: if the buffered AssistantMessage arrives
        *before* the stream's content_block_stop, we must emit only once.
        Previously reconciliation emitted on AssistantMessage and then
        _on_block_stop emitted a second ToolUseEvent unconditionally,
        causing duplicate tool-call bubbles in the UI."""
        adapter = _make_adapter()
        _start_message(adapter)
        adapter._handle_stream_event(_stream_event({
            "type": "content_block_start", "index": 0,
            "content_block": {"type": "tool_use", "id": "tu-1", "name": "Read", "input": {}},
        }))
        adapter._handle_stream_event(_stream_event({
            "type": "content_block_delta", "index": 0,
            "delta": {"type": "input_json_delta", "partial_json": '{"file_path":"/a"}'},
        }))

        # Buffered AssistantMessage arrives BEFORE the stream's stop.
        msg = AssistantMessage(
            content=[ToolUseBlock(id="tu-1", name="Read", input={"file_path": "/a"})],
            model="m",
        )
        buffered_events = adapter._translate_assistant_meta(msg)
        tool_events = [e for e in buffered_events if isinstance(e, ToolUseEvent)]
        assert len(tool_events) == 1

        # Late stream stop must not emit a second ToolUseEvent.
        stop_events = adapter._handle_stream_event(_stream_event({
            "type": "content_block_stop", "index": 0,
        }))
        assert not any(isinstance(e, ToolUseEvent) for e in stop_events)

    def test_tool_use_block_emitted_when_stream_did_not_see_it(self):
        """Broken-stream path: a tool_use only exists on the buffered
        AssistantMessage. Must be emitted so its downstream
        ToolResultBlock (delivered later on a UserMessage) can match against
        it by id."""
        adapter = _make_adapter()
        _start_message(adapter)
        # Stream only had thinking, no tool_use
        adapter._handle_stream_event(_stream_event({
            "type": "content_block_start", "index": 0,
            "content_block": {"type": "thinking"},
        }))
        adapter._handle_stream_event(_stream_event({
            "type": "content_block_delta", "index": 0,
            "delta": {"type": "thinking_delta", "thinking": "I should use Read"},
        }))

        msg = AssistantMessage(
            content=[ToolUseBlock(id="tu-1", name="Read", input={"file_path": "/a"})],
            model="m",
        )
        events = adapter._translate_assistant_meta(msg)

        tool_events = [e for e in events if isinstance(e, ToolUseEvent)]
        assert len(tool_events) == 1
        assert tool_events[0].id == "tu-1"
        assert tool_events[0].name == "Read"
        assert tool_events[0].input == {"file_path": "/a"}
        # And subsequent buffered messages in the same turn must not
        # re-emit the same tool_use.
        again = adapter._translate_assistant_meta(msg)
        assert not any(isinstance(e, ToolUseEvent) for e in again)

    def test_tool_result_block_is_still_translated(self):
        """Tool result blocks on AssistantMessages are rare but supported."""
        adapter = _make_adapter()
        msg = AssistantMessage(
            content=[ToolResultBlock(tool_use_id="tu-1", content="contents", is_error=False)],
            model="claude-sonnet-4-20250514",
        )
        events = adapter._translate_assistant_meta(msg)

        result_events = [e for e in events if isinstance(e, ToolResultEvent)]
        assert len(result_events) == 1
        assert result_events[0].tool_use_id == "tu-1"
        assert result_events[0].content == "contents"
        assert result_events[0].is_error is False

    def test_non_string_tool_result_content_converted(self):
        adapter = _make_adapter()
        msg = AssistantMessage(
            content=[ToolResultBlock(tool_use_id="tu-1", content=["chunk1", "chunk2"])],  # type: ignore[arg-type]
            model="claude-sonnet-4-20250514",
        )
        events = adapter._translate_assistant_meta(msg)

        result_events = [e for e in events if isinstance(e, ToolResultEvent)]
        assert isinstance(result_events[0].content, str)

    def test_broken_turn_splits_across_two_assistant_messages(self):
        """Reproduces the observed sonnet-4-6 pattern:
           stream: text@0 (empty) + thinking@1 (deltas, no stop) → dies.
           buffered: AssistantMessage#1 [ThinkingBlock], then
                     AssistantMessage#2 [TextBlock].
           Expected: no empty text bubble from the empty text@0, buffered
                     ThinkingBlock suppressed (stream had thinking), buffered
                     TextBlock emitted as the final answer.
        """
        adapter = _make_adapter()
        _start_message(adapter)

        # Stream: empty text@0 — start then immediate stop, no deltas.
        start_events = adapter._handle_stream_event(_stream_event({
            "type": "content_block_start", "index": 0,
            "content_block": {"type": "text", "text": ""},
        }))
        stop_events = adapter._handle_stream_event(_stream_event({
            "type": "content_block_stop", "index": 0,
        }))
        # Deferred start: neither start nor stop should produce events for
        # an empty text block.
        assert start_events == []
        assert stop_events == []

        # Stream: thinking@1 with deltas, but no stop ever arrives.
        adapter._handle_stream_event(_stream_event({
            "type": "content_block_start", "index": 1,
            "content_block": {"type": "thinking"},
        }))
        adapter._handle_stream_event(_stream_event({
            "type": "content_block_delta", "index": 1,
            "delta": {"type": "thinking_delta", "thinking": "reasoning"},
        }))

        # Buffered AssistantMessage #1 — just the thinking.
        msg1 = AssistantMessage(
            content=[ThinkingBlock(thinking="rewritten reasoning", signature="s")],
            model="claude-sonnet-4-6",
        )
        events1 = adapter._translate_assistant_meta(msg1)
        # ThinkingBlock suppressed because stream already had thinking deltas.
        assert not any(isinstance(e, ThinkingEvent) for e in events1)

        # Buffered AssistantMessage #2 — the real text answer, never streamed.
        msg2 = AssistantMessage(
            content=[TextBlock(text="What 3 bash commands would you like me to run?")],
            model="claude-sonnet-4-6",
        )
        events2 = adapter._translate_assistant_meta(msg2)
        text_events = [e for e in events2 if isinstance(e, TextEvent)]
        assert len(text_events) == 1
        assert text_events[0].text == "What 3 bash commands would you like me to run?"

    def test_reconciliation_state_resets_on_new_message_start(self):
        """Reconciliation flags are per-message_id. A new message_start
        resets them so a later turn's buffered content isn't skipped just
        because an earlier turn had streamed content."""
        adapter = _make_adapter()
        _start_message(adapter, "m1")
        adapter._handle_stream_event(_stream_event({
            "type": "content_block_start", "index": 0,
            "content_block": {"type": "text", "text": ""},
        }))
        adapter._handle_stream_event(_stream_event({
            "type": "content_block_delta", "index": 0,
            "delta": {"type": "text_delta", "text": "turn 1"},
        }))

        # New message — flags reset
        _start_message(adapter, "m2")

        msg = AssistantMessage(
            content=[TextBlock(text="turn 2 final")],
            model="m",
        )
        events = adapter._translate_assistant_meta(msg)

        text_events = [e for e in events if isinstance(e, TextEvent)]
        assert len(text_events) == 1
        assert text_events[0].text == "turn 2 final"
        assert text_events[0].message_id == "m2"


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

    def test_text_block_start_is_deferred_until_first_delta(self):
        """``content_block_start`` for text must NOT emit a
        ``TextBlockStartEvent`` immediately — deferred so empty text blocks
        (start+stop with no deltas) don't leak an empty bubble."""
        adapter = _make_adapter()
        _start_message(adapter)

        events = adapter._handle_stream_event(_stream_event({
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "text", "text": ""},
        }))

        assert events == []

    def test_first_text_delta_emits_start_plus_delta(self):
        """Deferred start event fires on the first delta, followed by the
        delta itself, so downstream sees the same sequence as before."""
        adapter = _make_adapter()
        _start_message(adapter)
        adapter._handle_stream_event(_stream_event({
            "type": "content_block_start", "index": 0,
            "content_block": {"type": "text", "text": ""},
        }))

        events = adapter._handle_stream_event(_stream_event({
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "Hello"},
        }))

        assert len(events) == 2
        assert isinstance(events[0], TextBlockStartEvent)
        assert events[0].block_index == 0
        assert events[0].message_id == "m1"
        assert isinstance(events[1], TextDeltaEvent)
        assert events[1].text == "Hello"
        assert events[1].block_index == 0

    def test_subsequent_text_deltas_do_not_re_emit_start(self):
        adapter = _make_adapter()
        _start_message(adapter)
        adapter._handle_stream_event(_stream_event({
            "type": "content_block_start", "index": 0,
            "content_block": {"type": "text", "text": ""},
        }))
        adapter._handle_stream_event(_stream_event({
            "type": "content_block_delta", "index": 0,
            "delta": {"type": "text_delta", "text": "A"},
        }))
        events = adapter._handle_stream_event(_stream_event({
            "type": "content_block_delta", "index": 0,
            "delta": {"type": "text_delta", "text": "B"},
        }))

        assert len(events) == 1
        assert isinstance(events[0], TextDeltaEvent)
        assert events[0].text == "B"

    def test_empty_text_block_emits_nothing(self):
        """content_block_start immediately followed by content_block_stop
        with no deltas in between must not produce any events."""
        adapter = _make_adapter()
        _start_message(adapter)
        adapter._handle_stream_event(_stream_event({
            "type": "content_block_start", "index": 0,
            "content_block": {"type": "text", "text": ""},
        }))
        events = adapter._handle_stream_event(_stream_event({
            "type": "content_block_stop", "index": 0,
        }))

        assert events == []
        # And the stream path should NOT have registered "text content" for
        # the reconciliation flag — so if a buffered TextBlock arrives, it
        # still gets emitted.
        assert adapter._streamed_text_had_content is False

    def test_thinking_block_start_and_delta(self):
        adapter = _make_adapter()
        _start_message(adapter)
        start = adapter._handle_stream_event(_stream_event({
            "type": "content_block_start", "index": 0,
            "content_block": {"type": "thinking"},
        }))
        # Deferred — no event yet
        assert start == []

        delta = adapter._handle_stream_event(_stream_event({
            "type": "content_block_delta", "index": 0,
            "delta": {"type": "thinking_delta", "thinking": "let me reason"},
        }))

        # First delta fires start + delta in sequence.
        assert len(delta) == 2
        assert isinstance(delta[0], ThinkingBlockStartEvent)
        assert isinstance(delta[1], ThinkingDeltaEvent)
        assert delta[1].thinking == "let me reason"

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
