"""Manages ClaudeSDKClient instances per active conversation.

This is the ONLY module that imports from claude_agent_sdk.
It translates SDK types into domain events (SDKEvent) so that
all downstream code depends only on domain types.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from .config import AGENT_CWD
from .models import (
    ModelInfoEvent,
    ResultEvent,
    SDKEvent,
    TextEvent,
    ThinkingEvent,
    ToolResultEvent,
    ToolUseEvent,
)


class ClaudeSDKClientAdapter:
    """Wraps ClaudeSDKClient, translating SDK messages into domain events."""

    def __init__(self, client: ClaudeSDKClient) -> None:
        self._client = client

    async def connect(self) -> None:
        await self._client.connect()

    async def query(self, content: str) -> None:
        await self._client.query(content)

    async def interrupt(self) -> None:
        await self._client.interrupt()

    async def disconnect(self) -> None:
        await self._client.disconnect()

    async def receive_response(self) -> AsyncIterator[SDKEvent]:
        async for msg in self._client.receive_response():
            if isinstance(msg, AssistantMessage):
                for event in _translate_assistant(msg):
                    yield event
            elif isinstance(msg, UserMessage):
                for event in _translate_user(msg):
                    yield event
            elif isinstance(msg, ResultMessage):
                yield ResultEvent(
                    session_id=msg.session_id,
                    duration_ms=msg.duration_ms,
                    total_cost_usd=msg.total_cost_usd or 0.0,
                    num_turns=msg.num_turns,
                    is_error=msg.is_error,
                )


def _translate_assistant(msg: AssistantMessage) -> list[SDKEvent]:
    """Translate an AssistantMessage into domain events."""
    events: list[SDKEvent] = []
    message_id = msg.uuid or msg.message_id or ""

    if msg.model or msg.usage:
        events.append(ModelInfoEvent(model=msg.model or "", usage=msg.usage or {}))

    for block in msg.content:
        if isinstance(block, ThinkingBlock):
            events.append(
                ThinkingEvent(thinking=block.thinking, signature=block.signature, message_id=message_id)
            )
        elif isinstance(block, ToolUseBlock):
            events.append(
                ToolUseEvent(id=block.id, name=block.name, input=block.input, message_id=message_id)
            )
        elif isinstance(block, ToolResultBlock):
            content = block.content if isinstance(block.content, str) else str(block.content)
            events.append(
                ToolResultEvent(tool_use_id=block.tool_use_id, content=content, is_error=block.is_error or False)
            )
        elif isinstance(block, TextBlock):
            events.append(
                TextEvent(text=block.text, message_id=message_id)
            )

    return events


def _translate_user(msg: UserMessage) -> list[SDKEvent]:
    """Translate a UserMessage (typically tool results) into domain events."""
    events: list[SDKEvent] = []
    if isinstance(msg.content, list):
        for block in msg.content:
            if isinstance(block, ToolResultBlock):
                content = block.content if isinstance(block.content, str) else str(block.content)
                events.append(
                    ToolResultEvent(tool_use_id=block.tool_use_id, content=content, is_error=block.is_error or False)
                )
    return events


class SDKManager:
    """Concrete SDKClientFactory — creates and caches SDK client adapters."""

    def __init__(self) -> None:
        self._clients: dict[str, ClaudeSDKClientAdapter] = {}

    async def create(
        self,
        session_id: str,
        resume: bool = False,
    ) -> ClaudeSDKClientAdapter:
        if session_id in self._clients:
            return self._clients[session_id]

        options = ClaudeAgentOptions(
            allowed_tools=["Read", "Edit", "Bash", "Glob", "Grep", "Write", "Skill"],
            permission_mode="acceptEdits",
            cwd=AGENT_CWD,
            setting_sources=["user", "project"],
            sandbox={
                "enabled": True,
                "autoAllowBashIfSandboxed": True,
            },
        )
        if resume:
            options.resume = session_id
        else:
            options.session_id = session_id

        client = ClaudeSDKClient(options=options)
        adapter = ClaudeSDKClientAdapter(client)
        self._clients[session_id] = adapter
        return adapter

    async def remove(self, session_id: str) -> None:
        adapter = self._clients.pop(session_id, None)
        if adapter:
            try:
                await adapter.disconnect()
            except Exception:
                pass

    def has(self, session_id: str) -> bool:
        return session_id in self._clients
