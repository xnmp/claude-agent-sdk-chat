"""WebSocket endpoint — thin adapter over ChatSession."""

from __future__ import annotations

import logging
import traceback
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..domain.chat import ChatSession, ConversationNotFoundError
from ..domain.ports import AppState
from .uploads import get_attachment
from .utils.message_translator import translate_event
from .utils.ws_events import ErrorWS, WSEvent

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


@router.websocket("/api/ws/{conversation_id}")
async def websocket_endpoint(websocket: WebSocket, conversation_id: str) -> None:
    await websocket.accept()

    deps: AppState = websocket.app.state.deps
    session = ChatSession(
        conversation_id=UUID(conversation_id),
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

                try:
                    async for domain_event in session.handle_user_message(
                        content, prompt_override=enriched,
                    ):
                        for ws_msg in translate_event(domain_event):
                            await _send_json(websocket, ws_msg)
                except Exception as e:
                    logger.error("SDK stream error: %s", traceback.format_exc())
                    await _send_json(websocket, ErrorWS(type="error", message=str(e)))

            elif msg_type == "interrupt":
                await session.handle_interrupt()

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.error("WebSocket error: %s", traceback.format_exc())
    finally:
        await session.save_pending_turn()
        await session.cleanup()
