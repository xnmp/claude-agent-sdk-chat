"""Domain models — pure data, no infrastructure dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal
from typing_extensions import TypedDict
from uuid import UUID


ANONYMOUS_USER_ID = UUID("00000000-0000-0000-0000-000000000000")


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


# ---------------------------------------------------------------------------
# Message content types (stored in DB as JSONB)
# ---------------------------------------------------------------------------


class ThinkingEntry(TypedDict):
    thinking: str
    signature: str


class ToolCallEntry(TypedDict):
    id: str
    name: str
    input: dict[str, Any]
    result: str | None
    is_error: bool | None


class UserMessageContent(TypedDict):
    text: str


class AssistantMessageContent(TypedDict):
    thinking: list[ThinkingEntry]
    tool_calls: list[ToolCallEntry]
    text: str
    model: str
    usage: dict[str, Any]
    duration_ms: int
    total_cost_usd: float


MessageContent = UserMessageContent | AssistantMessageContent


# ---------------------------------------------------------------------------
# Domain entities (persisted)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class User:
    id: UUID
    email: str
    display_name: str | None
    created_at: datetime


@dataclass(frozen=True)
class Conversation:
    id: UUID
    user_id: UUID
    title: str | None
    sdk_session_id: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class Message:
    id: UUID
    conversation_id: UUID
    role: MessageRole
    content: MessageContent
    created_at: datetime


# ---------------------------------------------------------------------------
# SDK domain events (yielded by SDKClient.receive_response)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ThinkingEvent:
    thinking: str
    signature: str
    message_id: str


@dataclass(frozen=True)
class ToolUseEvent:
    id: str
    name: str
    input: dict[str, Any]
    message_id: str


@dataclass(frozen=True)
class ToolResultEvent:
    tool_use_id: str
    content: str
    is_error: bool


@dataclass(frozen=True)
class TextEvent:
    text: str
    message_id: str


@dataclass(frozen=True)
class ModelInfoEvent:
    """Carries model/usage metadata — not sent to WS, only used by AssistantTurn."""
    model: str
    usage: dict[str, Any]


@dataclass(frozen=True)
class ResultEvent:
    session_id: str
    duration_ms: int
    total_cost_usd: float
    num_turns: int
    is_error: bool


SDKEvent = ThinkingEvent | ToolUseEvent | ToolResultEvent | TextEvent | ModelInfoEvent | ResultEvent


# ---------------------------------------------------------------------------
# WebSocket protocol events (sent to frontend)
# ---------------------------------------------------------------------------


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


class ErrorWS(TypedDict):
    type: Literal["error"]
    message: str


WSEvent = ThinkingWS | ToolUseWS | ToolInputWS | ToolResultWS | AssistantTextWS | ResultWS | ErrorWS


# ---------------------------------------------------------------------------
# Assistant turn accumulator (mutable, used during streaming)
# ---------------------------------------------------------------------------


@dataclass
class AssistantTurn:
    """Accumulates SDK events into a single assistant turn for DB persistence."""

    thinking: list[ThinkingEntry] = field(default_factory=list)
    tool_calls: list[ToolCallEntry] = field(default_factory=list)
    text: str = ""
    model: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
    total_cost_usd: float = 0.0

    def process(self, event: SDKEvent) -> None:
        """Update accumulator state from an SDK event."""
        match event:
            case ThinkingEvent(thinking=t, signature=s):
                self.thinking.append(ThinkingEntry(thinking=t, signature=s))
            case ToolUseEvent(id=tool_id, name=name, input=inp):
                self.tool_calls.append(
                    ToolCallEntry(id=tool_id, name=name, input=inp, result=None, is_error=None)
                )
            case ToolResultEvent(tool_use_id=tid, content=c, is_error=e):
                for tc in self.tool_calls:
                    if tc["id"] == tid:
                        tc["result"] = c
                        tc["is_error"] = e
                        break
            case TextEvent(text=t):
                self.text = t
            case ModelInfoEvent(model=m, usage=u):
                self.model = m or self.model
                if u:
                    self.usage = u
            case ResultEvent(duration_ms=d, total_cost_usd=c):
                self.duration_ms = d
                self.total_cost_usd = c

    def to_content(self) -> AssistantMessageContent:
        return AssistantMessageContent(
            thinking=self.thinking,
            tool_calls=self.tool_calls,
            text=self.text,
            model=self.model,
            usage=self.usage,
            duration_ms=self.duration_ms,
            total_cost_usd=self.total_cost_usd,
        )
