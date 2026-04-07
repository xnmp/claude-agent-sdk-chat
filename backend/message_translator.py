"""Translates SDK message types to WebSocket JSON and DB-ready structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)


@dataclass
class TurnAccumulator:
    """Accumulates SDK messages into a single assistant turn for DB persistence."""

    thinking: list[dict[str, str]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    text: str = ""
    model: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
    total_cost_usd: float = 0.0

    def to_content(self) -> dict[str, Any]:
        return {
            "thinking": self.thinking,
            "tool_calls": self.tool_calls,
            "text": self.text,
            "model": self.model,
            "usage": self.usage,
            "duration_ms": self.duration_ms,
            "total_cost_usd": self.total_cost_usd,
        }


def translate_assistant_message(
    msg: AssistantMessage,
    accumulator: TurnAccumulator,
) -> list[dict[str, Any]]:
    """Convert an AssistantMessage's content blocks into WS JSON messages.

    Also updates the accumulator for later DB persistence.
    """
    ws_messages: list[dict[str, Any]] = []
    message_id = msg.uuid or msg.message_id or ""
    accumulator.model = msg.model or accumulator.model

    if msg.usage:
        accumulator.usage = msg.usage

    for block in msg.content:
        if isinstance(block, ThinkingBlock):
            accumulator.thinking.append(
                {"thinking": block.thinking, "signature": block.signature}
            )
            ws_messages.append(
                {
                    "type": "thinking",
                    "thinking": block.thinking,
                    "message_id": message_id,
                }
            )
        elif isinstance(block, ToolUseBlock):
            tool_entry: dict[str, Any] = {
                "id": block.id,
                "name": block.name,
                "input": block.input,
                "result": None,
                "is_error": None,
            }
            accumulator.tool_calls.append(tool_entry)
            ws_messages.append(
                {
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "message_id": message_id,
                }
            )
            ws_messages.append(
                {
                    "type": "tool_input",
                    "tool_use_id": block.id,
                    "input": block.input,
                }
            )
        elif isinstance(block, ToolResultBlock):
            # Fill in the result for the matching tool call
            for tc in accumulator.tool_calls:
                if tc["id"] == block.tool_use_id:
                    tc["result"] = block.content
                    tc["is_error"] = block.is_error
                    break
            ws_messages.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.tool_use_id,
                    "content": block.content if isinstance(block.content, str) else str(block.content),
                    "is_error": block.is_error or False,
                }
            )
        elif isinstance(block, TextBlock):
            accumulator.text = block.text
            ws_messages.append(
                {
                    "type": "assistant_text",
                    "text": block.text,
                    "message_id": message_id,
                }
            )

    return ws_messages


def translate_user_message(msg: UserMessage) -> list[dict[str, Any]]:
    """Translate SDK UserMessage (typically tool results) to WS JSON."""
    ws_messages: list[dict[str, Any]] = []

    if isinstance(msg.content, list):
        for block in msg.content:
            if isinstance(block, ToolResultBlock):
                ws_messages.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.tool_use_id,
                        "content": block.content if isinstance(block.content, str) else str(block.content),
                        "is_error": block.is_error or False,
                    }
                )

    return ws_messages


def translate_result_message(msg: ResultMessage) -> dict[str, Any]:
    """Translate SDK ResultMessage to WS JSON."""
    return {
        "type": "result",
        "session_id": msg.session_id,
        "duration_ms": msg.duration_ms,
        "total_cost_usd": msg.total_cost_usd,
        "num_turns": msg.num_turns,
        "is_error": msg.is_error,
    }
