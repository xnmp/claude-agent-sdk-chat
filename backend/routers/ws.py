"""WebSocket endpoint for real-time chat with Claude Agent SDK."""

from __future__ import annotations

import logging
import traceback
import uuid
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    UserMessage,
)

from .. import db
from ..message_translator import (
    TurnAccumulator,
    translate_assistant_message,
    translate_result_message,
    translate_user_message,
)
from ..sdk_manager import sdk_manager

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

    # Look up conversation to get sdk_session_id
    conv = await db.get_conversation(conversation_id)
    if not conv:
        await _send_json(websocket, {"type": "error", "message": "Conversation not found"})
        await websocket.close()
        return

    sdk_session_id = conv.get("sdk_session_id")
    client = None

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "user_message":
                content = data.get("content", "").strip()
                if not content:
                    continue

                # Save user message to DB
                await db.save_message(
                    conversation_id=conversation_id,
                    role="user",
                    content={"text": content},
                )

                # Create SDK client lazily on first message
                if client is None:
                    if sdk_session_id:
                        # Resume existing session
                        client = await sdk_manager.create_client(
                            sdk_session_id, resume=True
                        )
                    else:
                        # New session
                        sdk_session_id = str(uuid.uuid4())
                        await db.update_conversation(
                            conversation_id, sdk_session_id=sdk_session_id
                        )
                        client = await sdk_manager.create_client(
                            sdk_session_id, resume=False
                        )
                    await client.connect()

                # Send to agent
                await client.query(content)

                # Stream responses
                accumulator = TurnAccumulator()
                try:
                    async for msg in client.receive_response():
                        if isinstance(msg, AssistantMessage):
                            ws_msgs = translate_assistant_message(msg, accumulator)
                            for ws_msg in ws_msgs:
                                await _send_json(websocket, ws_msg)

                        elif isinstance(msg, UserMessage):
                            # SDK yields UserMessage for tool results in the loop
                            ws_msgs = translate_user_message(msg)
                            for ws_msg in ws_msgs:
                                await _send_json(websocket, ws_msg)
                                # Also update accumulator with tool results
                                if ws_msg["type"] == "tool_result":
                                    for tc in accumulator.tool_calls:
                                        if tc["id"] == ws_msg["tool_use_id"]:
                                            tc["result"] = ws_msg["content"]
                                            tc["is_error"] = ws_msg["is_error"]

                        elif isinstance(msg, ResultMessage):
                            accumulator.duration_ms = msg.duration_ms
                            accumulator.total_cost_usd = msg.total_cost_usd or 0.0

                            # Save assistant turn to DB
                            await db.save_message(
                                conversation_id=conversation_id,
                                role="assistant",
                                content=accumulator.to_content(),
                            )

                            # Auto-generate title from first user message if none
                            conv_check = await db.get_conversation(conversation_id)
                            if conv_check and not conv_check.get("title"):
                                first_title = content[:80]
                                await db.update_conversation(
                                    conversation_id, title=first_title
                                )

                            ws_result = translate_result_message(msg)
                            await _send_json(websocket, ws_result)

                except Exception as e:
                    logger.error("SDK stream error: %s", traceback.format_exc())
                    await _send_json(
                        websocket, {"type": "error", "message": str(e)}
                    )

            elif msg_type == "interrupt":
                if client:
                    try:
                        await client.interrupt()
                    except Exception:
                        pass

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("WebSocket error: %s", traceback.format_exc())
    finally:
        if sdk_session_id:
            await sdk_manager.remove_client(sdk_session_id)
