"""Unit tests for domain models — AssistantTurn accumulation logic."""

from __future__ import annotations

from backend.domain.models import (
    AssistantTurn,
    ModelInfoEvent,
    ResultEvent,
    TextBlockStartEvent,
    TextDeltaEvent,
    TextEvent,
    ThinkingBlockStartEvent,
    ThinkingDeltaEvent,
    ThinkingEvent,
    ToolResultEvent,
    ToolUseEvent,
    normalize_assistant_content,
    text_blocks,
    thinking_blocks,
    tool_call_blocks,
)


def _kinds(blocks: list) -> list[str]:
    return [b["kind"] for b in blocks]


class TestAssistantTurnProcess:
    def test_appends_thinking_blocks_in_order(self):
        turn = AssistantTurn()
        turn.process(ThinkingEvent(thinking="step 1", signature="sig-a", message_id="m1"))
        turn.process(ThinkingEvent(thinking="step 2", signature="sig-b", message_id="m1"))

        assert _kinds(turn.blocks) == ["thinking", "thinking"]
        thoughts = thinking_blocks(turn.blocks)
        assert thoughts[0]["thinking"] == "step 1"
        assert thoughts[1]["signature"] == "sig-b"

    def test_appends_tool_use(self):
        turn = AssistantTurn()
        turn.process(ToolUseEvent(id="t1", name="Read", input={"file_path": "/x"}, message_id="m1"))

        assert _kinds(turn.blocks) == ["tool_call"]
        tools = tool_call_blocks(turn.blocks)
        assert tools[0]["name"] == "Read"
        assert tools[0]["input"] == {"file_path": "/x"}
        assert tools[0]["result"] is None

    def test_tool_result_backfills_matching_tool_call(self):
        turn = AssistantTurn()
        turn.process(ToolUseEvent(id="t1", name="Read", input={}, message_id="m1"))
        turn.process(ToolUseEvent(id="t2", name="Grep", input={}, message_id="m1"))
        turn.process(ToolResultEvent(tool_use_id="t1", content="file contents", is_error=False))

        tools = tool_call_blocks(turn.blocks)
        assert tools[0]["result"] == "file contents"
        assert tools[0]["is_error"] is False
        # t2 is unaffected
        assert tools[1]["result"] is None

    def test_tool_result_for_unknown_id_is_silent(self):
        turn = AssistantTurn()
        # Should not raise — unknown tool IDs are ignored
        turn.process(ToolResultEvent(tool_use_id="nonexistent", content="x", is_error=False))
        assert turn.blocks == []

    def test_text_blocks_are_preserved_in_order(self):
        """Multiple text blocks in one turn must all survive (regression: previously
        each TextEvent overwrote the prior one, losing the model's narrative)."""
        turn = AssistantTurn()
        turn.process(TextEvent(text="draft", message_id="m1"))
        turn.process(TextEvent(text="final answer", message_id="m2"))

        texts = text_blocks(turn.blocks)
        assert [b["text"] for b in texts] == ["draft", "final answer"]

    def test_interleaved_text_and_tool_calls_preserve_order(self):
        """A turn like text → tool → text → tool → text keeps the original sequence."""
        turn = AssistantTurn()
        turn.process(TextEvent(text="let me check", message_id="m1"))
        turn.process(ToolUseEvent(id="t1", name="Read", input={}, message_id="m1"))
        turn.process(ToolResultEvent(tool_use_id="t1", content="ok", is_error=False))
        turn.process(TextEvent(text="now editing", message_id="m2"))
        turn.process(ToolUseEvent(id="t2", name="Edit", input={}, message_id="m2"))
        turn.process(ToolResultEvent(tool_use_id="t2", content="done", is_error=False))
        turn.process(TextEvent(text="all set", message_id="m3"))

        assert _kinds(turn.blocks) == [
            "text", "tool_call", "text", "tool_call", "text",
        ]
        texts = text_blocks(turn.blocks)
        assert [b["text"] for b in texts] == ["let me check", "now editing", "all set"]
        # tool results landed on the right calls, in order
        tools = tool_call_blocks(turn.blocks)
        assert tools[0]["result"] == "ok"
        assert tools[1]["result"] == "done"

    def test_text_delta_appends_to_open_text_block(self):
        """A typical streaming sequence: start opens an empty text block;
        deltas grow it character-by-character."""
        turn = AssistantTurn()
        turn.process(TextBlockStartEvent(block_index=0, message_id="m1"))
        for chunk in ["He", "llo", ", world!"]:
            turn.process(TextDeltaEvent(text=chunk, block_index=0, message_id="m1"))

        assert _kinds(turn.blocks) == ["text"]
        assert text_blocks(turn.blocks)[0]["text"] == "Hello, world!"

    def test_text_delta_starts_a_new_block_after_a_tool_call(self):
        """Two text blocks separated by a tool call render in order, with the
        second text block growing from its own deltas without disturbing the
        first."""
        turn = AssistantTurn()
        turn.process(TextBlockStartEvent(block_index=0, message_id="m1"))
        turn.process(TextDeltaEvent(text="let me check", block_index=0, message_id="m1"))
        turn.process(ToolUseEvent(id="t1", name="Read", input={}, message_id="m1"))
        turn.process(ToolResultEvent(tool_use_id="t1", content="ok", is_error=False))
        turn.process(TextBlockStartEvent(block_index=2, message_id="m1"))
        turn.process(TextDeltaEvent(text="all done", block_index=2, message_id="m1"))

        assert _kinds(turn.blocks) == ["text", "tool_call", "text"]
        texts = text_blocks(turn.blocks)
        assert [b["text"] for b in texts] == ["let me check", "all done"]

    def test_text_delta_without_a_preceding_start_creates_a_block(self):
        """Defensive: if a delta arrives without a paired start (out-of-order
        SDK delivery, dropped frame), we still capture the text rather than
        silently losing it."""
        turn = AssistantTurn()
        turn.process(TextDeltaEvent(text="orphan", block_index=0, message_id="m1"))

        assert _kinds(turn.blocks) == ["text"]
        assert text_blocks(turn.blocks)[0]["text"] == "orphan"

    def test_thinking_delta_appends_to_open_thinking_block(self):
        turn = AssistantTurn()
        turn.process(ThinkingBlockStartEvent(block_index=0, message_id="m1"))
        for chunk in ["Let ", "me ", "think..."]:
            turn.process(ThinkingDeltaEvent(thinking=chunk, block_index=0, message_id="m1"))

        thoughts = thinking_blocks(turn.blocks)
        assert len(thoughts) == 1
        assert thoughts[0]["thinking"] == "Let me think..."

    def test_streaming_text_then_legacy_text_event_coexist(self):
        """Mixed mode: delta-driven text from streaming alongside a complete
        TextEvent (used by tests / non-streaming fallback)."""
        turn = AssistantTurn()
        turn.process(TextBlockStartEvent(block_index=0, message_id="m1"))
        turn.process(TextDeltaEvent(text="streamed", block_index=0, message_id="m1"))
        turn.process(TextEvent(text="complete", message_id="m2"))

        texts = text_blocks(turn.blocks)
        assert [b["text"] for b in texts] == ["streamed", "complete"]

    def test_model_info_preserves_existing_model_when_empty(self):
        turn = AssistantTurn()
        turn.process(ModelInfoEvent(model="claude-sonnet-4-20250514", usage={}))
        turn.process(ModelInfoEvent(model="", usage={"output_tokens": 5}))

        assert turn.model == "claude-sonnet-4-20250514"
        assert turn.usage == {"output_tokens": 5}


class TestAssistantTurnToContent:
    def test_full_turn_produces_complete_content(self, sample_sdk_events: list):
        turn = AssistantTurn()
        for event in sample_sdk_events:
            turn.process(event)

        content = turn.to_content()

        assert content["model"] == "claude-sonnet-4-20250514"
        assert content["duration_ms"] == 1500
        assert content["total_cost_usd"] == 0.003

        # Sample sequence: ThinkingEvent → ToolUseEvent → ToolResultEvent → TextEvent
        # Result: thinking block, tool_call block (with result filled), text block
        assert _kinds(content["blocks"]) == ["thinking", "tool_call", "text"]
        assert thinking_blocks(content["blocks"])[0]["thinking"] == "Let me read the file..."
        tool = tool_call_blocks(content["blocks"])[0]
        assert tool["name"] == "Read"
        assert tool["result"] == "print('hello')"
        assert text_blocks(content["blocks"])[0]["text"] == "The file contains a hello world program."

    def test_empty_turn_produces_valid_content(self):
        content = AssistantTurn().to_content()

        assert content["blocks"] == []
        assert content["model"] == ""
        assert content["duration_ms"] == 0
        assert content["total_cost_usd"] == 0.0


class TestNormalizeAssistantContent:
    def test_passes_through_new_shape(self):
        raw = {
            "blocks": [
                {"kind": "text", "text": "hi"},
            ],
            "model": "claude",
            "usage": {"input_tokens": 1},
            "duration_ms": 100,
            "total_cost_usd": 0.001,
            "created_files": [],
        }
        normalized = normalize_assistant_content(raw)

        assert normalized["blocks"] == [{"kind": "text", "text": "hi"}]
        assert normalized["model"] == "claude"

    def test_legacy_shape_reconstructs_blocks_in_render_order(self):
        """Legacy rows lose interleaving info — reconstruct as thinking → tools → text,
        which matches how the legacy UI displayed them."""
        raw = {
            "thinking": [{"thinking": "hmm", "signature": "s"}],
            "tool_calls": [
                {"id": "t1", "name": "Read", "input": {"file_path": "/x"},
                 "result": "contents", "is_error": False},
            ],
            "text": "the answer",
            "model": "claude-sonnet-4-20250514",
            "usage": {"output_tokens": 50},
            "duration_ms": 1500,
            "total_cost_usd": 0.003,
        }
        normalized = normalize_assistant_content(raw)

        assert _kinds(normalized["blocks"]) == ["thinking", "tool_call", "text"]
        assert thinking_blocks(normalized["blocks"])[0]["thinking"] == "hmm"
        tool = tool_call_blocks(normalized["blocks"])[0]
        assert tool["name"] == "Read"
        assert tool["result"] == "contents"
        assert text_blocks(normalized["blocks"])[0]["text"] == "the answer"
        assert normalized["model"] == "claude-sonnet-4-20250514"
        assert normalized["duration_ms"] == 1500

    def test_legacy_with_empty_text_omits_text_block(self):
        raw = {
            "thinking": [],
            "tool_calls": [{"id": "t1", "name": "Bash", "input": {},
                            "result": "ok", "is_error": False}],
            "text": "",
            "model": "", "usage": {}, "duration_ms": 0, "total_cost_usd": 0.0,
        }
        normalized = normalize_assistant_content(raw)

        assert _kinds(normalized["blocks"]) == ["tool_call"]

    def test_legacy_empty_turn_yields_empty_blocks(self):
        raw = {
            "thinking": [], "tool_calls": [], "text": "",
            "model": "", "usage": {}, "duration_ms": 0, "total_cost_usd": 0.0,
        }
        normalized = normalize_assistant_content(raw)

        assert normalized["blocks"] == []
