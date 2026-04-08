"""Chat orchestration — domain logic with no infrastructure dependencies.

Depends only on port interfaces and domain models.
Does NOT import from claude_agent_sdk or transport-layer types.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from uuid import UUID

from .models import (
    AssistantTurn,
    MessageRole,
    ResultEvent,
    SDKEvent,
    UserMessageContent,
)
from .ports import ConversationRepository, MessageRepository, SDKClient, SDKClientFactory

logger = logging.getLogger(__name__)


class ChatSession:
    """Manages a single chat session's interaction with the SDK.

    Holds the SDK client reference across messages within one WebSocket
    connection. All dependencies are injected via constructor.
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
        self._cumulative_cost: float = 0.0
        self._pending_turn: AssistantTurn | None = None
        self._pending_content: str | None = None
        self._turn_persisted: bool = False

    async def initialize(self) -> None:
        """Load conversation and set the SDK session ID. Call once before handling messages."""
        conv = await self._conversations.get(self.conversation_id)
        if conv is None:
            raise ConversationNotFoundError(self.conversation_id)
        self._sdk_session_id = conv.sdk_session_id

    async def handle_user_message(self, content: str) -> AsyncIterator[SDKEvent]:
        """Process a user message and yield domain events."""
        # Persist user message
        await self._messages.save(
            conversation_id=self.conversation_id,
            role=MessageRole.USER,
            content=UserMessageContent(text=content),
        )

        # Lazily create SDK client
        if self._client is None:
            self._client = await self._ensure_sdk_client()

        # Query the agent and stream response
        await self._client.query(content)

        turn = AssistantTurn()
        self._pending_turn = turn
        self._pending_content = content
        self._turn_persisted = False

        async for event in self._client.receive_response():
            # SDK reports cumulative session cost; convert to per-message
            if isinstance(event, ResultEvent):
                per_message_cost = event.total_cost_usd - self._cumulative_cost
                self._cumulative_cost = event.total_cost_usd
                event = ResultEvent(
                    session_id=event.session_id,
                    duration_ms=event.duration_ms,
                    total_cost_usd=per_message_cost,
                    num_turns=event.num_turns,
                    is_error=event.is_error,
                )

            turn.process(event)
            yield event

            if isinstance(event, ResultEvent):
                await self._persist_turn(turn, content)
                self._turn_persisted = True

    async def _persist_turn(self, turn: AssistantTurn, first_content: str) -> None:
        await self._messages.save(
            conversation_id=self.conversation_id,
            role=MessageRole.ASSISTANT,
            content=turn.to_content(),
        )
        await self._auto_title(first_content)

    async def save_pending_turn(self) -> None:
        """Persist any unsaved turn (e.g., after early disconnect).

        Call from the transport layer's cleanup/finally block.
        Safe to call multiple times — no-ops if already persisted or empty.
        """
        if (
            not self._turn_persisted
            and self._pending_turn is not None
            and self._pending_turn.has_content()
            and self._pending_content is not None
        ):
            try:
                await self._persist_turn(self._pending_turn, self._pending_content)
                self._turn_persisted = True
            except Exception:
                logger.error("Failed to persist partial turn on disconnect")

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


class ConversationNotFoundError(Exception):
    def __init__(self, conversation_id: UUID) -> None:
        super().__init__(f"Conversation {conversation_id} not found")
        self.conversation_id = conversation_id
