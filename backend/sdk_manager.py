"""Manages ClaudeSDKClient instances per active conversation."""

from __future__ import annotations

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

from .config import AGENT_CWD


class SDKManager:
    def __init__(self) -> None:
        self._clients: dict[str, ClaudeSDKClient] = {}

    async def create_client(
        self,
        session_id: str,
        resume: bool = False,
    ) -> ClaudeSDKClient:
        """Create and connect a new ClaudeSDKClient."""
        if session_id in self._clients:
            return self._clients[session_id]

        options = ClaudeAgentOptions(
            allowed_tools=["Read", "Edit", "Bash", "Glob", "Grep", "Write"],
            permission_mode="bypassPermissions",
            cwd=AGENT_CWD,
        )
        if resume:
            options.resume = session_id
        else:
            options.session_id = session_id

        client = ClaudeSDKClient(options=options)
        self._clients[session_id] = client
        return client

    async def remove_client(self, session_id: str) -> None:
        """Disconnect and remove a client."""
        client = self._clients.pop(session_id, None)
        if client:
            try:
                await client.disconnect()
            except Exception:
                pass

    def has_client(self, session_id: str) -> bool:
        return session_id in self._clients


# Singleton
sdk_manager = SDKManager()
