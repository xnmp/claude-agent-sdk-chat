"""Unit tests for message translator — domain events to WS events.

Focuses on the non-trivial aspects: ToolUseEvent producing two WS events,
ModelInfoEvent producing none, and full turn composition.
"""

from __future__ import annotations

from backend.routers.utils.message_translator import translate_event
from backend.domain.models import (
    ModelInfoEvent,
    ResultEvent,
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


class TestTranslateResultEvent:
    def test_created_files_included_in_ws_event(self):
        event = ResultEvent(
            session_id="s1", duration_ms=100, total_cost_usd=0.01,
            num_turns=1, is_error=False, created_files=["report.csv", "chart.png"],
        )
        result = translate_event(event)
        assert len(result) == 1
        assert result[0]["created_files"] == ["report.csv", "chart.png"]

    def test_empty_created_files(self):
        event = ResultEvent(
            session_id="s1", duration_ms=50, total_cost_usd=0.0,
            num_turns=1, is_error=False,
        )
        result = translate_event(event)
        assert result[0]["created_files"] == []


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
