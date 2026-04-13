"""WebSocket protocol events — transport-layer types sent to the frontend."""

from __future__ import annotations

from typing import Any, Literal
from typing_extensions import TypedDict


class ThinkingWS(TypedDict):
    type: Literal["thinking"]
    thinking: str
    message_id: str


class ToolUseWS(TypedDict):
    type: Literal["tool_use"]
    id: str
    name: str
    message_id: str


class ToolInputWS(TypedDict):
    type: Literal["tool_input"]
    tool_use_id: str
    input: dict[str, Any]


class ToolResultWS(TypedDict):
    type: Literal["tool_result"]
    tool_use_id: str
    content: str
    is_error: bool


class AssistantTextWS(TypedDict):
    """Final, complete text block — used by tests/fakes and as a non-streaming
    fallback. The streaming production path uses TextBlockStartWS + TextDeltaWS
    instead."""
    type: Literal["assistant_text"]
    text: str
    message_id: str


class TextBlockStartWS(TypedDict):
    """Marks the start of a streaming text block. The frontend opens an empty
    text block; subsequent TextDeltaWS messages grow it."""
    type: Literal["text_block_start"]
    block_index: int
    message_id: str


class TextDeltaWS(TypedDict):
    """An incremental text fragment for the most recently opened text block."""
    type: Literal["text_delta"]
    text: str
    block_index: int
    message_id: str


class ThinkingBlockStartWS(TypedDict):
    """Marks the start of a streaming thinking block."""
    type: Literal["thinking_block_start"]
    block_index: int
    message_id: str


class ThinkingDeltaWS(TypedDict):
    """An incremental thinking fragment for the most recently opened thinking block."""
    type: Literal["thinking_delta"]
    thinking: str
    block_index: int
    message_id: str


class ResultWS(TypedDict):
    type: Literal["result"]
    session_id: str
    duration_ms: int
    total_cost_usd: float
    num_turns: int
    is_error: bool
    created_files: list[str]


class ErrorWS(TypedDict):
    type: Literal["error"]
    message: str


class SuggestionsWS(TypedDict):
    type: Literal["suggestions"]
    questions: list[str]


class TitleUpdateWS(TypedDict):
    type: Literal["title_update"]
    title: str


WSEvent = (
    ThinkingWS
    | ToolUseWS
    | ToolInputWS
    | ToolResultWS
    | AssistantTextWS
    | TextBlockStartWS
    | TextDeltaWS
    | ThinkingBlockStartWS
    | ThinkingDeltaWS
    | ResultWS
    | ErrorWS
    | SuggestionsWS
    | TitleUpdateWS
)
