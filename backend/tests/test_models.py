"""Unit tests for domain models — AssistantTurn accumulation and MessageRole."""

from __future__ import annotations

from backend.models import (
    AssistantTurn,
    MessageRole,
    ModelInfoEvent,
    ResultEvent,
    TextEvent,
    ThinkingEvent,
    ToolResultEvent,
    ToolUseEvent,
)


class TestMessageRole:
    def test_values_match_db_strings(self):
        assert MessageRole.USER.value == "user"
        assert MessageRole.ASSISTANT.value == "assistant"

    def test_round_trips_from_string(self):
        assert MessageRole("user") is MessageRole.USER
        assert MessageRole("assistant") is MessageRole.ASSISTANT


class TestAssistantTurnProcess:
    def test_accumulates_thinking(self):
        turn = AssistantTurn()
        turn.process(ThinkingEvent(thinking="step 1", signature="sig-a", message_id="m1"))
        turn.process(ThinkingEvent(thinking="step 2", signature="sig-b", message_id="m1"))

        assert len(turn.thinking) == 2
        assert turn.thinking[0]["thinking"] == "step 1"
        assert turn.thinking[1]["signature"] == "sig-b"

    def test_accumulates_tool_use(self):
        turn = AssistantTurn()
        turn.process(ToolUseEvent(id="t1", name="Read", input={"file_path": "/x"}, message_id="m1"))

        assert len(turn.tool_calls) == 1
        assert turn.tool_calls[0]["name"] == "Read"
        assert turn.tool_calls[0]["input"] == {"file_path": "/x"}
        assert turn.tool_calls[0]["result"] is None

    def test_tool_result_backfills_matching_tool_call(self):
        turn = AssistantTurn()
        turn.process(ToolUseEvent(id="t1", name="Read", input={}, message_id="m1"))
        turn.process(ToolUseEvent(id="t2", name="Grep", input={}, message_id="m1"))
        turn.process(ToolResultEvent(tool_use_id="t1", content="file contents", is_error=False))

        assert turn.tool_calls[0]["result"] == "file contents"
        assert turn.tool_calls[0]["is_error"] is False
        # t2 is unaffected
        assert turn.tool_calls[1]["result"] is None

    def test_tool_result_for_unknown_id_is_silent(self):
        turn = AssistantTurn()
        # Should not raise — unknown tool IDs are ignored
        turn.process(ToolResultEvent(tool_use_id="nonexistent", content="x", is_error=False))
        assert turn.tool_calls == []

    def test_text_event_overwrites_previous(self):
        turn = AssistantTurn()
        turn.process(TextEvent(text="draft", message_id="m1"))
        turn.process(TextEvent(text="final answer", message_id="m2"))

        assert turn.text == "final answer"

    def test_model_info_updates_model_and_usage(self):
        turn = AssistantTurn()
        turn.process(ModelInfoEvent(model="claude-sonnet-4-20250514", usage={"input_tokens": 10}))

        assert turn.model == "claude-sonnet-4-20250514"
        assert turn.usage == {"input_tokens": 10}

    def test_model_info_preserves_existing_model_when_empty(self):
        turn = AssistantTurn()
        turn.process(ModelInfoEvent(model="claude-sonnet-4-20250514", usage={}))
        turn.process(ModelInfoEvent(model="", usage={"output_tokens": 5}))

        assert turn.model == "claude-sonnet-4-20250514"
        assert turn.usage == {"output_tokens": 5}

    def test_result_event_sets_duration_and_cost(self):
        turn = AssistantTurn()
        turn.process(ResultEvent(session_id="s1", duration_ms=2500, total_cost_usd=0.01, num_turns=3, is_error=False))

        assert turn.duration_ms == 2500
        assert turn.total_cost_usd == 0.01


class TestAssistantTurnToContent:
    def test_full_turn_produces_complete_content(self, sample_sdk_events: list):
        turn = AssistantTurn()
        for event in sample_sdk_events:
            turn.process(event)

        content = turn.to_content()

        assert content["model"] == "claude-sonnet-4-20250514"
        assert content["text"] == "The file contains a hello world program."
        assert content["duration_ms"] == 1500
        assert content["total_cost_usd"] == 0.003
        assert len(content["thinking"]) == 1
        assert content["thinking"][0]["thinking"] == "Let me read the file..."
        assert len(content["tool_calls"]) == 1
        assert content["tool_calls"][0]["name"] == "Read"
        assert content["tool_calls"][0]["result"] == "print('hello')"

    def test_empty_turn_produces_valid_content(self):
        content = AssistantTurn().to_content()

        assert content["text"] == ""
        assert content["thinking"] == []
        assert content["tool_calls"] == []
        assert content["model"] == ""
        assert content["duration_ms"] == 0
        assert content["total_cost_usd"] == 0.0
