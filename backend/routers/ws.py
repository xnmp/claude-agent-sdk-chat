"""WebSocket endpoint — thin adapter over ChatSession."""

from __future__ import annotations

import asyncio
import logging
import traceback
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..domain.chat import ChatSession, ConversationNotFoundError
from ..domain.models import ResultEvent, TextEvent
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
) -> None:
    """Run title generation and follow-up suggestions in parallel, send results via WS."""
    async def do_title() -> None:
        title = await generate_title(user_content, assistant_text)
        if title:
            await conversations.update(conversation_id, title=title)  # type: ignore[union-attr]
            await _send_json(websocket, TitleUpdateWS(type="title_update", title=title))

    async def do_suggestions() -> None:
        questions = await generate_follow_ups(user_content, assistant_text)
        if questions:
            await _send_json(websocket, SuggestionsWS(type="suggestions", questions=questions))

    await asyncio.gather(do_title(), do_suggestions(), return_exceptions=True)


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

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "user_message":
                content = data.get("content", "").strip()
                if not content:
                    continue

                # Resolve file attachments and build enriched prompt
                attachment_ids = data.get("attachment_ids", [])
                enriched = _resolve_attachments(content, attachment_ids)

                # Track assistant text for background tasks
                assistant_text = ""
                turn_complete = False

                try:
                    async for domain_event in session.handle_user_message(
                        content, prompt_override=enriched,
                    ):
                        if isinstance(domain_event, TextEvent):
                            assistant_text = domain_event.text
                        if isinstance(domain_event, ResultEvent):
                            turn_complete = True

                        for ws_msg in translate_event(domain_event):
                            await _send_json(websocket, ws_msg)
                except Exception as e:
                    logger.error("SDK stream error: %s", traceback.format_exc())
                    await _send_json(websocket, ErrorWS(type="error", message=str(e)))

                # Fire background tasks after turn completes
                if turn_complete and assistant_text:
                    asyncio.create_task(
                        _run_background_tasks(
                            websocket, conv_id, deps.conversations,
                            content, assistant_text,
                        )
                    )

            elif msg_type == "interrupt":
                await session.handle_interrupt()

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.error("WebSocket error: %s", traceback.format_exc())
    finally:
        await session.save_pending_turn()
        await session.cleanup()
