"""Translates domain SDK events into WebSocket protocol events.

Pure functions — no infrastructure dependencies, no SDK imports.
"""

from __future__ import annotations

from ...domain.models import (
    ModelInfoEvent,
    ResultEvent,
    SDKEvent,
    TextEvent,
    ThinkingEvent,
    ToolResultEvent,
    ToolUseEvent,
)
from .ws_events import (
    AssistantTextWS,
    ResultWS,
    ThinkingWS,
    ToolInputWS,
    ToolResultWS,
    ToolUseWS,
    WSEvent,
)


def translate_event(event: SDKEvent) -> list[WSEvent]:
    """Convert a domain SDK event into WebSocket events for the frontend.

    Returns an empty list for events that have no WS representation
    (e.g. ModelInfoEvent).
    """
    match event:
        case ThinkingEvent(thinking=t, message_id=mid):
            return [ThinkingWS(type="thinking", thinking=t, message_id=mid)]

        case ToolUseEvent(id=tool_id, name=name, input=inp, message_id=mid):
            return [
                ToolUseWS(type="tool_use", id=tool_id, name=name, message_id=mid),
                ToolInputWS(type="tool_input", tool_use_id=tool_id, input=inp),
            ]

        case ToolResultEvent(tool_use_id=tid, content=c, is_error=e):
            return [ToolResultWS(type="tool_result", tool_use_id=tid, content=c, is_error=e)]

        case TextEvent(text=t, message_id=mid):
            return [AssistantTextWS(type="assistant_text", text=t, message_id=mid)]

        case ModelInfoEvent():
            return []

        case ResultEvent(session_id=sid, duration_ms=d, total_cost_usd=c, num_turns=n, is_error=e):
            return [ResultWS(
                type="result",
                session_id=sid,
                duration_ms=d,
                total_cost_usd=c,
                num_turns=n,
                is_error=e,
            )]
