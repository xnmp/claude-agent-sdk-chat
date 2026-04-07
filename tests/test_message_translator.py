"""Unit tests for message translator — domain events to WS events."""

from __future__ import annotations

from backend.message_translator import translate_event
from backend.models import (
    ModelInfoEvent,
    ResultEvent,
    TextEvent,
    ThinkingEvent,
    ToolResultEvent,
    ToolUseEvent,
)


class TestTranslateThinkingEvent:
    def test_produces_thinking_ws_event(self):
        event = ThinkingEvent(thinking="analyzing...", signature="sig1", message_id="m1")
        result = translate_event(event)

        assert len(result) == 1
        assert result[0]["type"] == "thinking"
        assert result[0]["thinking"] == "analyzing..."
        assert result[0]["message_id"] == "m1"


class TestTranslateToolUseEvent:
    def test_produces_two_ws_events(self):
        event = ToolUseEvent(id="t1", name="Read", input={"file_path": "/x"}, message_id="m1")
        result = translate_event(event)

        assert len(result) == 2
        assert result[0]["type"] == "tool_use"
        assert result[0]["id"] == "t1"
        assert result[0]["name"] == "Read"
        assert result[1]["type"] == "tool_input"
        assert result[1]["tool_use_id"] == "t1"
        assert result[1]["input"] == {"file_path": "/x"}


class TestTranslateToolResultEvent:
    def test_produces_tool_result_ws_event(self):
        event = ToolResultEvent(tool_use_id="t1", content="file contents", is_error=False)
        result = translate_event(event)

        assert len(result) == 1
        assert result[0]["type"] == "tool_result"
        assert result[0]["tool_use_id"] == "t1"
        assert result[0]["content"] == "file contents"
        assert result[0]["is_error"] is False

    def test_error_result(self):
        event = ToolResultEvent(tool_use_id="t1", content="permission denied", is_error=True)
        result = translate_event(event)

        assert result[0]["is_error"] is True
        assert result[0]["content"] == "permission denied"


class TestTranslateTextEvent:
    def test_produces_assistant_text_ws_event(self):
        event = TextEvent(text="Here is the answer.", message_id="m2")
        result = translate_event(event)

        assert len(result) == 1
        assert result[0]["type"] == "assistant_text"
        assert result[0]["text"] == "Here is the answer."
        assert result[0]["message_id"] == "m2"


class TestTranslateModelInfoEvent:
    def test_produces_no_ws_events(self):
        event = ModelInfoEvent(model="claude-sonnet-4-20250514", usage={"input_tokens": 10})
        result = translate_event(event)

        assert result == []


class TestTranslateResultEvent:
    def test_produces_result_ws_event_with_all_fields(self):
        event = ResultEvent(
            session_id="sess-1",
            duration_ms=3000,
            total_cost_usd=0.05,
            num_turns=2,
            is_error=False,
        )
        result = translate_event(event)

        assert len(result) == 1
        assert result[0]["type"] == "result"
        assert result[0]["session_id"] == "sess-1"
        assert result[0]["duration_ms"] == 3000
        assert result[0]["total_cost_usd"] == 0.05
        assert result[0]["num_turns"] == 2
        assert result[0]["is_error"] is False

    def test_error_result(self):
        event = ResultEvent(
            session_id="sess-1",
            duration_ms=100,
            total_cost_usd=0.0,
            num_turns=0,
            is_error=True,
        )
        result = translate_event(event)

        assert result[0]["is_error"] is True


class TestTranslateFullTurn:
    def test_realistic_event_sequence(self, sample_sdk_events: list):
        """Translate a full turn and verify the WS event stream."""
        all_ws_events = []
        for event in sample_sdk_events:
            all_ws_events.extend(translate_event(event))

        types = [e["type"] for e in all_ws_events]
        assert types == [
            "thinking",
            "tool_use",
            "tool_input",
            "tool_result",
            "assistant_text",
            "result",
        ]
