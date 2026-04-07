"""Manages ClaudeSDKClient instances per active conversation.

Implements the SDKClientFactory and SDKClient protocols from ports.py.
"""

from __future__ import annotations

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

from .config import AGENT_CWD
from .ports import SDKClient


class ClaudeSDKClientAdapter:
    """Wraps ClaudeSDKClient to satisfy the SDKClient protocol."""

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

    def receive_response(self):  # noqa: ANN201
        return self._client.receive_response()


class SDKManager:
    """Concrete SDKClientFactory — creates and caches ClaudeSDKClient instances."""

    def __init__(self) -> None:
        self._clients: dict[str, ClaudeSDKClientAdapter] = {}

    async def create(
        self,
        session_id: str,
        resume: bool = False,
    ) -> SDKClient:
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
