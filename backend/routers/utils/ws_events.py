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
    type: Literal["assistant_text"]
    text: str
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


WSEvent = ThinkingWS | ToolUseWS | ToolInputWS | ToolResultWS | AssistantTextWS | ResultWS | ErrorWS | SuggestionsWS | TitleUpdateWS
