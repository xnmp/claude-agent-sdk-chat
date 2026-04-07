"""WebSocket endpoint — thin adapter over ChatSession."""

from __future__ import annotations

import logging
import traceback
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

from ..chat import ChatSession, ConversationNotFoundError

logger = logging.getLogger(__name__)

router = APIRouter()


async def _send_json(ws: WebSocket, data: dict[str, Any]) -> None:
    try:
        await ws.send_json(data)
    except Exception:
        pass


@router.websocket("/api/ws/{conversation_id}")
async def websocket_endpoint(websocket: WebSocket, conversation_id: str) -> None:
    await websocket.accept()

    # Pull injected dependencies from app state
    app = websocket.app
    session = ChatSession(
        conversation_id=UUID(conversation_id),
        conversations=app.state.conversations,
        messages=app.state.messages,
        sdk_factory=app.state.sdk_factory,
    )

    try:
        await session.initialize()
    except ConversationNotFoundError:
        await _send_json(websocket, {"type": "error", "message": "Conversation not found"})
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

                try:
                    async for ws_msg in session.handle_user_message(content):
                        await _send_json(websocket, ws_msg)
                except Exception as e:
                    logger.error("SDK stream error: %s", traceback.format_exc())
                    await _send_json(websocket, {"type": "error", "message": str(e)})

            elif msg_type == "interrupt":
                await session.handle_interrupt()

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.error("WebSocket error: %s", traceback.format_exc())
    finally:
        await session.cleanup()
