"""Unit tests for SDK adapter — translating claude_agent_sdk types to domain events.

These tests verify that the adapter layer in sdk_manager.py correctly
translates concrete SDK types into domain events, which is the boundary
where claude_agent_sdk knowledge is isolated.
"""

from __future__ import annotations

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from backend.domain.models import (
    ModelInfoEvent,
    ResultEvent,
    TextEvent,
    ThinkingEvent,
    ToolResultEvent,
    ToolUseEvent,
)
from backend.infra.sdk_manager import _translate_assistant, _translate_user


class TestTranslateAssistant:
    def test_thinking_block(self):
        msg = AssistantMessage(
            content=[ThinkingBlock(thinking="Let me think...", signature="sig-1")],
            model="claude-sonnet-4-20250514",
            message_id="msg-1",
        )
        events = _translate_assistant(msg)

        # ModelInfoEvent for model + the thinking event
        assert any(isinstance(e, ModelInfoEvent) for e in events)
        thinking = [e for e in events if isinstance(e, ThinkingEvent)]
        assert len(thinking) == 1
        assert thinking[0].thinking == "Let me think..."
        assert thinking[0].signature == "sig-1"
        assert thinking[0].message_id == "msg-1"

    def test_text_block(self):
        msg = AssistantMessage(
            content=[TextBlock(text="Hello world")],
            model="claude-sonnet-4-20250514",
            message_id="msg-2",
        )
        events = _translate_assistant(msg)

        text_events = [e for e in events if isinstance(e, TextEvent)]
        assert len(text_events) == 1
        assert text_events[0].text == "Hello world"
        assert text_events[0].message_id == "msg-2"

    def test_tool_use_block(self):
        msg = AssistantMessage(
            content=[ToolUseBlock(id="tu-1", name="Read", input={"file_path": "/tmp/x"})],
            model="claude-sonnet-4-20250514",
            message_id="msg-3",
        )
        events = _translate_assistant(msg)

        tool_events = [e for e in events if isinstance(e, ToolUseEvent)]
        assert len(tool_events) == 1
        assert tool_events[0].id == "tu-1"
        assert tool_events[0].name == "Read"
        assert tool_events[0].input == {"file_path": "/tmp/x"}

    def test_tool_result_block(self):
        msg = AssistantMessage(
            content=[ToolResultBlock(tool_use_id="tu-1", content="file contents", is_error=False)],
            model="claude-sonnet-4-20250514",
        )
        events = _translate_assistant(msg)

        result_events = [e for e in events if isinstance(e, ToolResultEvent)]
        assert len(result_events) == 1
        assert result_events[0].tool_use_id == "tu-1"
        assert result_events[0].content == "file contents"
        assert result_events[0].is_error is False

    def test_error_tool_result(self):
        msg = AssistantMessage(
            content=[ToolResultBlock(tool_use_id="tu-2", content="permission denied", is_error=True)],
            model="claude-sonnet-4-20250514",
        )
        events = _translate_assistant(msg)

        result_events = [e for e in events if isinstance(e, ToolResultEvent)]
        assert result_events[0].is_error is True

    def test_mixed_content_blocks_preserve_order(self):
        msg = AssistantMessage(
            content=[
                ThinkingBlock(thinking="hmm", signature="s1"),
                ToolUseBlock(id="tu-1", name="Grep", input={"pattern": "foo"}),
                ToolResultBlock(tool_use_id="tu-1", content="bar.py:3:foo"),
                TextBlock(text="Found it in bar.py"),
            ],
            model="claude-sonnet-4-20250514",
            message_id="msg-4",
        )
        events = _translate_assistant(msg)

        # Filter out ModelInfoEvent
        content_events = [e for e in events if not isinstance(e, ModelInfoEvent)]
        types = [type(e).__name__ for e in content_events]
        assert types == ["ThinkingEvent", "ToolUseEvent", "ToolResultEvent", "TextEvent"]

    def test_model_info_emitted_when_model_present(self):
        msg = AssistantMessage(
            content=[TextBlock(text="hi")],
            model="claude-sonnet-4-20250514",
            usage={"input_tokens": 100, "output_tokens": 20},
        )
        events = _translate_assistant(msg)

        model_events = [e for e in events if isinstance(e, ModelInfoEvent)]
        assert len(model_events) == 1
        assert model_events[0].model == "claude-sonnet-4-20250514"
        assert model_events[0].usage == {"input_tokens": 100, "output_tokens": 20}

    def test_no_model_info_when_both_empty(self):
        msg = AssistantMessage(
            content=[TextBlock(text="hi")],
            model="",
        )
        events = _translate_assistant(msg)

        model_events = [e for e in events if isinstance(e, ModelInfoEvent)]
        assert len(model_events) == 0

    def test_uses_uuid_for_message_id(self):
        msg = AssistantMessage(
            content=[TextBlock(text="hi")],
            model="claude-sonnet-4-20250514",
            uuid="uuid-abc",
            message_id="mid-xyz",
        )
        events = _translate_assistant(msg)

        text_events = [e for e in events if isinstance(e, TextEvent)]
        # uuid takes precedence over message_id
        assert text_events[0].message_id == "uuid-abc"

    def test_non_string_tool_result_content_converted(self):
        msg = AssistantMessage(
            content=[ToolResultBlock(tool_use_id="tu-1", content=["chunk1", "chunk2"])],  # type: ignore[arg-type]
            model="claude-sonnet-4-20250514",
        )
        events = _translate_assistant(msg)

        result_events = [e for e in events if isinstance(e, ToolResultEvent)]
        # Non-string content is stringified
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
