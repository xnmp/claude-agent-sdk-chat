"""Chat orchestration — domain logic with no infrastructure dependencies.

Depends only on port interfaces (ConversationRepository, MessageRepository,
SDKClientFactory) and the message translator (pure functions).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from claude_agent_sdk import AssistantMessage, ResultMessage, UserMessage

from .message_translator import (
    TurnAccumulator,
    translate_assistant_message,
    translate_result_message,
    translate_user_message,
)
from .ports import ConversationRepository, MessageRepository, SDKClient, SDKClientFactory

logger = logging.getLogger(__name__)


class ChatSession:
    """Manages a single chat session's interaction with the SDK.

    Holds the SDK client reference across messages within one WebSocket
    connection. The orchestration methods are pure domain logic — they
    read/write through injected repository and SDK interfaces.
    """

    def __init__(
        self,
        conversation_id: UUID,
        conversations: ConversationRepository,
        messages: MessageRepository,
        sdk_factory: SDKClientFactory,
    ) -> None:
        self.conversation_id = conversation_id
        self._conversations = conversations
        self._messages = messages
        self._sdk_factory = sdk_factory
        self._client: SDKClient | None = None
        self._sdk_session_id: str | None = None

    async def initialize(self) -> None:
        """Load conversation and set the SDK session ID. Call once before handling messages."""
        conv = await self._conversations.get(self.conversation_id)
        if conv is None:
            raise ConversationNotFoundError(self.conversation_id)
        self._sdk_session_id = conv.sdk_session_id

    async def handle_user_message(self, content: str) -> AsyncIterator[dict[str, Any]]:
        """Process a user message and yield WebSocket events.

        Saves the user message, lazily creates the SDK client,
        streams the assistant response, and persists the result.
        """
        # Persist user message
        await self._messages.save(
            conversation_id=self.conversation_id,
            role="user",
            content={"text": content},
        )

        # Lazily create SDK client
        if self._client is None:
            self._client = await self._ensure_sdk_client()

        # Query the agent
        await self._client.query(content)

        # Stream and yield response events
        accumulator = TurnAccumulator()
        async for msg in self._client.receive_response():
            if isinstance(msg, AssistantMessage):
                for ws_msg in translate_assistant_message(msg, accumulator):
                    yield ws_msg

            elif isinstance(msg, UserMessage):
                for ws_msg in translate_user_message(msg):
                    yield ws_msg
                    if ws_msg["type"] == "tool_result":
                        _backfill_tool_result(accumulator, ws_msg)

            elif isinstance(msg, ResultMessage):
                accumulator.duration_ms = msg.duration_ms
                accumulator.total_cost_usd = msg.total_cost_usd or 0.0

                # Persist the complete assistant turn
                await self._messages.save(
                    conversation_id=self.conversation_id,
                    role="assistant",
                    content=accumulator.to_content(),
                )

                # Auto-title from first user message
                await self._auto_title(content)

                yield translate_result_message(msg)

    async def handle_interrupt(self) -> None:
        if self._client:
            try:
                await self._client.interrupt()
            except Exception:
                pass

    async def cleanup(self) -> None:
        if self._sdk_session_id:
            await self._sdk_factory.remove(self._sdk_session_id)

    # -- private helpers -----------------------------------------------------

    async def _ensure_sdk_client(self) -> SDKClient:
        if self._sdk_session_id:
            client = await self._sdk_factory.create(self._sdk_session_id, resume=True)
        else:
            self._sdk_session_id = str(uuid.uuid4())
            await self._conversations.update(
                self.conversation_id, sdk_session_id=self._sdk_session_id,
            )
            client = await self._sdk_factory.create(self._sdk_session_id, resume=False)
        await client.connect()
        return client

    async def _auto_title(self, first_content: str) -> None:
        conv = await self._conversations.get(self.conversation_id)
        if conv and not conv.title:
            await self._conversations.update(
                self.conversation_id, title=first_content[:80],
            )


def _backfill_tool_result(accumulator: TurnAccumulator, ws_msg: dict[str, Any]) -> None:
    """Update the accumulator's tool_calls with a tool result."""
    for tc in accumulator.tool_calls:
        if tc["id"] == ws_msg["tool_use_id"]:
            tc["result"] = ws_msg["content"]
            tc["is_error"] = ws_msg["is_error"]
            break


class ConversationNotFoundError(Exception):
    def __init__(self, conversation_id: UUID) -> None:
        super().__init__(f"Conversation {conversation_id} not found")
        self.conversation_id = conversation_id
