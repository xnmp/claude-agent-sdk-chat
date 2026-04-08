"""Unit tests for message translator — domain events to WS events.

Focuses on the non-trivial aspects: ToolUseEvent producing two WS events,
ModelInfoEvent producing none, and full turn composition.
"""

from __future__ import annotations

from backend.routers.utils.message_translator import translate_event
from backend.domain.models import (
    ModelInfoEvent,
    ToolUseEvent,
)


class TestTranslateToolUseEvent:
    def test_produces_both_tool_use_and_tool_input_events(self):
        """ToolUseEvent is the one event that fans out to two WS events."""
        event = ToolUseEvent(id="t1", name="Read", input={"file_path": "/x"}, message_id="m1")
        result = translate_event(event)

        assert len(result) == 2
        assert result[0]["type"] == "tool_use"
        assert result[1]["type"] == "tool_input"
        # tool_input references the tool_use by ID
        assert result[1]["tool_use_id"] == result[0]["id"]


class TestTranslateModelInfoEvent:
    def test_produces_no_ws_events(self):
        """ModelInfoEvent is internal — not sent to frontend."""
        result = translate_event(ModelInfoEvent(model="claude-sonnet-4-20250514", usage={"input_tokens": 10}))
        assert result == []


class TestTranslateFullTurn:
    def test_realistic_event_sequence(self, sample_sdk_events: list):
        """Translate a full turn and verify the WS event stream order."""
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
