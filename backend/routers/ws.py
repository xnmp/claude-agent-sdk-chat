"""WebSocket endpoint — thin adapter over ChatSession."""

from __future__ import annotations

import asyncio
import logging
import traceback
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..domain.chat import ChatSession, ConversationNotFoundError
from ..domain.models import ResultEvent, TextDeltaEvent, TextEvent
from ..domain.ports import AppState
from ..infra.background_llm import generate_follow_ups, generate_title
from .uploads import get_attachment
from .utils.message_translator import translate_event
from .utils.ws_events import ErrorWS, SuggestionsWS, TitleUpdateWS, WSEvent

logger = logging.getLogger(__name__)

router = APIRouter()


def _resolve_attachments(content: str, attachment_ids: list[str]) -> str | None:
    """Build enriched prompt with file injections, or None if no attachments."""
    if not attachment_ids:
        return None
    enriched = content
    for aid in attachment_ids:
        result = get_attachment(aid)
        if result:
            _, attachment = result
            enriched += attachment.injection
    return enriched


async def _send_json(ws: WebSocket, data: WSEvent) -> None:
    try:
        await ws.send_json(data)
    except Exception:
        pass


async def _run_background_tasks(
    websocket: WebSocket,
    conversation_id: UUID,
    conversations: object,
    user_content: str,
    assistant_text: str,
    generate_title_this_turn: bool,
) -> None:
    """Run title generation and follow-up suggestions in parallel, send results via WS.

    `generate_title_this_turn` gates the title generator — the caller flips it
    to False after the first turn so later turns only regenerate suggestions.
    """
    async def do_title() -> None:
        # Two titles can already be on the conversation at this point:
        #   1. The placeholder set by ChatSession._auto_title (always equals
        #      `user_content[:80]`). This is overwritable — we're the final
        #      LLM-based title and the placeholder only exists so the sidebar
        #      shows *something* between stream-end and our completion.
        #   2. A title the user set manually via PATCH /api/conversations/{id}
        #      — either before WS connect (caught by needs_title=False) or
        #      between WS connect and this background task firing (the race
        #      the needs_title flag can't catch). Manual titles are anything
        #      that doesn't match the placeholder shape.
        current = await conversations.get(conversation_id)  # type: ignore[union-attr]
        if current is not None and current.title is not None:
            auto_placeholder = user_content[:80]
            if current.title != auto_placeholder:
                return  # Manual rename — leave it alone.
        title = await generate_title(user_content, assistant_text)
        if title:
            await conversations.update(conversation_id, title=title)  # type: ignore[union-attr]
            await _send_json(websocket, TitleUpdateWS(type="title_update", title=title))

    async def do_suggestions() -> None:
        questions = await generate_follow_ups(user_content, assistant_text)
        if questions:
            await _send_json(websocket, SuggestionsWS(type="suggestions", questions=questions))

    if generate_title_this_turn:
        await asyncio.gather(do_title(), do_suggestions(), return_exceptions=True)
    else:
        await do_suggestions()


async def _stream_turn(
    websocket: WebSocket,
    session: ChatSession,
    conversation_id: UUID,
    conversations: object,
    content: str,
    enriched: str | None,
    generate_title_this_turn: bool,
) -> None:
    """Stream a single assistant turn to the websocket.

    Runs as a background task so the main receive loop can process
    concurrent control messages (e.g. interrupt) while the turn is in flight.
    """
    # Accumulate the full assistant text for the title/follow-up generators that
    # fire after the turn completes. Both a complete TextEvent (used by tests
    # and the non-streaming fallback) and the streaming TextDeltaEvent fragments
    # contribute, so the join here works regardless of which path the SDK
    # adapter takes.
    text_chunks: list[str] = []
    turn_complete = False

    try:
        async for domain_event in session.handle_user_message(
            content, prompt_override=enriched,
        ):
            if isinstance(domain_event, TextEvent):
                text_chunks.append(domain_event.text)
            elif isinstance(domain_event, TextDeltaEvent):
                text_chunks.append(domain_event.text)
            if isinstance(domain_event, ResultEvent):
                turn_complete = True

            for ws_msg in translate_event(domain_event):
                await _send_json(websocket, ws_msg)
    except Exception as e:
        logger.error("SDK stream error: %s", traceback.format_exc())
        await _send_json(websocket, ErrorWS(type="error", message=str(e)))

    if turn_complete and text_chunks:
        asyncio.create_task(
            _run_background_tasks(
                websocket, conversation_id, conversations, content,
                "".join(text_chunks),
                generate_title_this_turn=generate_title_this_turn,
            )
        )


@router.websocket("/api/ws/{conversation_id}")
async def websocket_endpoint(websocket: WebSocket, conversation_id: str) -> None:
    await websocket.accept()

    deps: AppState = websocket.app.state.deps
    conv_id = UUID(conversation_id)
    session = ChatSession(
        conversation_id=conv_id,
        conversations=deps.conversations,
        messages=deps.messages,
        sdk_factory=deps.sdk_factory,
    )

    try:
        await session.initialize()
    except ConversationNotFoundError:
        await _send_json(websocket, ErrorWS(type="error", message="Conversation not found"))
        await websocket.close()
        return

    # The title is generated exactly once per conversation, on the first user
    # turn. We cache the flag here so subsequent turns in the same session
    # skip the generator without re-reading the DB. On reconnect the flag
    # re-derives from the DB, so it persists across sessions via the title
    # column rather than via in-memory state.
    existing_conv = await deps.conversations.get(conv_id)
    needs_title = existing_conv is None or existing_conv.title is None

    stream_task: asyncio.Task[None] | None = None

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "user_message":
                # Ignore if a turn is already streaming — UI disables send,
                # but guard against races / misbehaving clients.
                if stream_task is not None and not stream_task.done():
                    continue

                content = data.get("content", "").strip()
                if not content:
                    continue

                attachment_ids = data.get("attachment_ids", [])
                enriched = _resolve_attachments(content, attachment_ids)

                stream_task = asyncio.create_task(
                    _stream_turn(
                        websocket, session, conv_id, deps.conversations,
                        content, enriched,
                        generate_title_this_turn=needs_title,
                    )
                )
                # Optimistically flip — later turns skip the title generator
                # regardless of whether this turn's generation actually lands
                # a title in the DB. Failed generations retry on reconnect.
                needs_title = False

            elif msg_type == "interrupt":
                await session.handle_interrupt()

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.error("WebSocket error: %s", traceback.format_exc())
    finally:
        if stream_task is not None and not stream_task.done():
            try:
                await asyncio.wait_for(stream_task, timeout=5.0)
            except (TimeoutError, Exception):
                stream_task.cancel()
        await session.save_pending_turn()
        await session.cleanup()
