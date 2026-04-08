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

import os

from pathlib import Path

from ..config import AGENT_CWD, ANTHROPIC_API_KEY, ANTHROPIC_MODEL, AUTH_PROXY_ENABLED, AUTH_PROXY_PORT
from .hooks import make_hooks

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

# Env vars safe to pass through to the agent subprocess.
_ENV_ALLOWLIST = frozenset({
    "PATH", "HOME", "LANG", "LC_ALL", "TERM", "USER", "SHELL",
    "TMPDIR", "TMP", "TEMP", "XDG_RUNTIME_DIR",
})

# Known secret-bearing vars to explicitly blank.
# The SDK merges options.env on top of os.environ, so we must
# override these to prevent inheritance from the parent process.
_SECRET_VARS = frozenset({
    "ANTHROPIC_API_KEY", "DATABASE_URL",
    "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
    "GITHUB_TOKEN", "GH_TOKEN",
    "OPENAI_API_KEY", "GOOGLE_API_KEY",
})


def _build_agent_env() -> dict[str, str]:
    """Build a scrubbed environment for the agent subprocess.

    Returns a dict to pass as ClaudeAgentOptions.env. The SDK merges
    this on top of the inherited os.environ, so we:
    1. Point ANTHROPIC_BASE_URL to the local auth proxy
    2. When a key is configured, replace it with a dummy (proxy injects the real one)
    3. Blank out other known secrets (DATABASE_URL, etc.)

    When no ANTHROPIC_API_KEY is configured, the CLI uses its own stored
    credentials (OAuth from ~/.claude/), so we don't override it.
    """
    if not AUTH_PROXY_ENABLED:
        return {}

    env: dict[str, str] = {}

    # Blank out non-API secrets regardless
    for var in _SECRET_VARS - {"ANTHROPIC_API_KEY"}:
        env[var] = ""

    # Only override the API key when we have a real one to inject via proxy.
    # Otherwise let the CLI use its own stored credentials.
    if ANTHROPIC_API_KEY:
        env["ANTHROPIC_API_KEY"] = "proxy-managed"

    # Point agent to the local auth proxy
    env["ANTHROPIC_BASE_URL"] = f"http://127.0.0.1:{AUTH_PROXY_PORT}"

    return env


def _load_system_prompt(output_dir: str, scripts_dir: str) -> str:
    template = (_PROMPTS_DIR / "system.md").read_text()
    return template.replace("{output_dir}", output_dir).replace("{scripts_dir}", scripts_dir)
from ..domain.models import (
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

    def __init__(self, client: ClaudeSDKClient, created_files: set[str] | None = None) -> None:
        self._client = client
        self.created_files: set[str] = created_files if created_files is not None else set()

    async def connect(self) -> None:
        await self._client.connect()

    async def query(self, content: str) -> None:
        await self._client.query(content)

    async def interrupt(self) -> None:
        await self._client.interrupt()

    async def disconnect(self) -> None:
        await self._client.disconnect()

    def pop_created_files(self) -> list[str]:
        """Return and clear the list of files created during the last turn."""
        files = sorted(self.created_files)
        self.created_files.clear()
        return files

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
                    created_files=self.pop_created_files(),
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


_DEFAULT_IDLE_TTL = 30 * 60  # 30 minutes


class SDKManager:
    """Concrete SDKClientFactory — creates and caches SDK client adapters.

    Tracks last-access time per client and evicts idle clients that exceed
    the TTL, preventing unbounded subprocess leaks from abandoned conversations.
    """

    def __init__(self, idle_ttl: float = _DEFAULT_IDLE_TTL) -> None:
        self._clients: dict[str, ClaudeSDKClientAdapter] = {}
        self._last_access: dict[str, float] = {}
        self._idle_ttl = idle_ttl

    async def create(
        self,
        session_id: str,
        resume: bool = False,
    ) -> ClaudeSDKClientAdapter:
        await self._evict_idle()

        if session_id in self._clients:
            self._last_access[session_id] = _now()
            return self._clients[session_id]

        output_dir = os.path.join(AGENT_CWD, "output")
        scripts_dir = os.path.join(AGENT_CWD, "output_scripts")
        uploads_dir = os.path.join(AGENT_CWD, "uploads")
        for d in [output_dir, scripts_dir, uploads_dir]:
            os.makedirs(d, exist_ok=True)
        hook_config = make_hooks(output_dir, scripts_dir, uploads_dir)

        options = ClaudeAgentOptions(
            allowed_tools=["Read", "Edit", "Bash", "Glob", "Grep", "Write", "Skill"],
            permission_mode="acceptEdits",
            cwd=AGENT_CWD,
            model=ANTHROPIC_MODEL or None,
            system_prompt=_load_system_prompt(output_dir, scripts_dir),
            setting_sources=["user", "project"],
            sandbox={
                "enabled": True,
                "autoAllowBashIfSandboxed": True,
            },
            hooks=hook_config["hooks"],
            env=_build_agent_env(),
        )
        if resume:
            options.resume = session_id
        else:
            options.session_id = session_id

        client = ClaudeSDKClient(options=options)
        adapter = ClaudeSDKClientAdapter(client, hook_config["created_files"])
        self._clients[session_id] = adapter
        self._last_access[session_id] = _now()
        return adapter

    async def remove(self, session_id: str) -> None:
        self._last_access.pop(session_id, None)
        adapter = self._clients.pop(session_id, None)
        if adapter:
            try:
                await adapter.disconnect()
            except Exception:
                pass

    def has(self, session_id: str) -> bool:
        return session_id in self._clients

    async def _evict_idle(self) -> None:
        """Remove clients that have been idle longer than the TTL."""
        now = _now()
        expired = [
            sid for sid, ts in self._last_access.items()
            if now - ts > self._idle_ttl
        ]
        for sid in expired:
            await self.remove(sid)


def _now() -> float:
    import time
    return time.monotonic()
