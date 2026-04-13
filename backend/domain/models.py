"""Domain models — pure data, no infrastructure dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal, cast
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


class TextBlockEntry(TypedDict):
    """A run of model-generated prose."""
    kind: Literal["text"]
    text: str


class ThinkingBlockEntry(TypedDict):
    """An extended-thinking block."""
    kind: Literal["thinking"]
    thinking: str
    signature: str


class ToolCallBlockEntry(TypedDict):
    """A tool invocation, including its (eventual) result."""
    kind: Literal["tool_call"]
    id: str
    name: str
    input: dict[str, Any]
    result: str | None
    is_error: bool | None


# Ordered union of block types that make up an assistant turn.
BlockEntry = TextBlockEntry | ThinkingBlockEntry | ToolCallBlockEntry


# -- Narrowing helpers ------------------------------------------------------
#
# pyrefly cannot fully discriminate a TypedDict union by its `kind` literal
# at the call site, so consumers (tests, UI serializers, background-task
# helpers) get cleaner code by going through these typed filters.

def text_blocks(blocks: list[BlockEntry]) -> list[TextBlockEntry]:
    return [cast(TextBlockEntry, b) for b in blocks if b["kind"] == "text"]


def tool_call_blocks(blocks: list[BlockEntry]) -> list[ToolCallBlockEntry]:
    return [cast(ToolCallBlockEntry, b) for b in blocks if b["kind"] == "tool_call"]


def thinking_blocks(blocks: list[BlockEntry]) -> list[ThinkingBlockEntry]:
    return [cast(ThinkingBlockEntry, b) for b in blocks if b["kind"] == "thinking"]


class UserMessageContent(TypedDict):
    text: str


class AssistantMessageContent(TypedDict):
    """Persisted assistant turn — an ordered sequence of content blocks
    plus whole-turn metadata.

    Old DB rows used parallel buckets (`thinking[]`, `tool_calls[]`, `text`).
    Loaders run them through `normalize_assistant_content` to rebuild
    `blocks` from the legacy shape.
    """
    blocks: list[BlockEntry]
    model: str
    usage: dict[str, Any]
    duration_ms: int
    total_cost_usd: float
    created_files: list[str]


MessageContent = UserMessageContent | AssistantMessageContent


def normalize_assistant_content(raw: dict[str, Any]) -> AssistantMessageContent:
    """Coerce a raw JSONB row into the current `AssistantMessageContent` shape.

    New rows already store `blocks`. Legacy rows store `thinking[] / tool_calls[] / text`
    with no inherent ordering between text and tool calls — we reconstruct them
    in the order they were rendered: thinking first, then tool calls, then a
    single trailing text block. This is lossy for the (impossible-to-recover)
    original interleaving, but matches how the legacy UI displayed them.
    """
    if "blocks" in raw:
        return {  # type: ignore[return-value]
            "blocks": raw.get("blocks") or [],
            "model": raw.get("model", ""),
            "usage": raw.get("usage", {}),
            "duration_ms": raw.get("duration_ms", 0),
            "total_cost_usd": raw.get("total_cost_usd", 0.0),
            "created_files": raw.get("created_files", []),
        }

    blocks: list[BlockEntry] = []
    for t in raw.get("thinking", []) or []:
        blocks.append(ThinkingBlockEntry(
            kind="thinking",
            thinking=t.get("thinking", ""),
            signature=t.get("signature", ""),
        ))
    for tc in raw.get("tool_calls", []) or []:
        blocks.append(ToolCallBlockEntry(
            kind="tool_call",
            id=tc.get("id", ""),
            name=tc.get("name", ""),
            input=tc.get("input", {}),
            result=tc.get("result"),
            is_error=tc.get("is_error"),
        ))
    text = raw.get("text") or ""
    if text:
        blocks.append(TextBlockEntry(kind="text", text=text))

    return {
        "blocks": blocks,
        "model": raw.get("model", ""),
        "usage": raw.get("usage", {}),
        "duration_ms": raw.get("duration_ms", 0),
        "total_cost_usd": raw.get("total_cost_usd", 0.0),
        "created_files": raw.get("created_files", []),
    }


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
    created_files: list[str] = field(default_factory=list)


SDKEvent = ThinkingEvent | ToolUseEvent | ToolResultEvent | TextEvent | ModelInfoEvent | ResultEvent


# ---------------------------------------------------------------------------
# Assistant turn accumulator (mutable, used during streaming)
# ---------------------------------------------------------------------------


@dataclass
class AssistantTurn:
    """Accumulates SDK events into a single assistant turn for DB persistence.

    Blocks are appended in arrival order, so a turn that interleaves text and
    tool calls (e.g. "let me check…" → Read → "now I'll…" → Edit → "done")
    preserves the original sequence rather than collapsing into one final text.
    """

    blocks: list[BlockEntry] = field(default_factory=list)
    model: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
    total_cost_usd: float = 0.0
    created_files: list[str] = field(default_factory=list)

    def process(self, event: SDKEvent) -> None:
        """Update accumulator state from an SDK event."""
        match event:
            case ThinkingEvent(thinking=t, signature=s):
                self.blocks.append(ThinkingBlockEntry(
                    kind="thinking", thinking=t, signature=s,
                ))
            case ToolUseEvent(id=tool_id, name=name, input=inp):
                self.blocks.append(ToolCallBlockEntry(
                    kind="tool_call", id=tool_id, name=name, input=inp,
                    result=None, is_error=None,
                ))
            case ToolResultEvent(tool_use_id=tid, content=c, is_error=e):
                for block in self.blocks:
                    if block.get("kind") == "tool_call" and block.get("id") == tid:
                        block["result"] = c  # type: ignore[typeddict-item]
                        block["is_error"] = e  # type: ignore[typeddict-item]
                        break
            case TextEvent(text=t):
                self.blocks.append(TextBlockEntry(kind="text", text=t))
            case ModelInfoEvent(model=m, usage=u):
                self.model = m or self.model
                if u:
                    self.usage = u
            case ResultEvent(duration_ms=d, total_cost_usd=c, created_files=f):
                self.duration_ms = d
                self.total_cost_usd = c
                self.created_files = f

    def has_content(self) -> bool:
        """True if the turn has accumulated any meaningful content."""
        return bool(self.blocks)

    def to_content(self) -> AssistantMessageContent:
        return AssistantMessageContent(
            blocks=self.blocks,
            model=self.model,
            usage=self.usage,
            duration_ms=self.duration_ms,
            total_cost_usd=self.total_cost_usd,
            created_files=self.created_files,
        )
