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
    StreamEvent,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

import json
import os

from pathlib import Path
from typing import Any

from ..config import AGENT_CWD, ANTHROPIC_API_KEY, ANTHROPIC_MODEL, AUTH_PROXY_ENABLED, AUTH_PROXY_PORT
from .hooks import make_hooks

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

# Sandbox configuration for the agent's Bash tool. allowUnsandboxedCommands
# must stay False so the agent cannot bypass the sandbox via
# dangerouslyDisableSandbox.
_SANDBOX_SETTINGS = {
    "enabled": True,
    "autoAllowBashIfSandboxed": True,
    "allowUnsandboxedCommands": False,
}

# Standalone stdio MCP servers spawned alongside the agent. The SDK launches
# these as subprocesses and speaks JSON-RPC over stdin/stdout — they run
# *outside* the Bash sandbox, so they don't need any of the sandbox relaxations
# that would be required to reach a TCP localhost service. See `mytools/`.
#
# --directory pins `uv run` to the repo root regardless of AGENT_CWD, so the
# MCP subprocess always resolves `mytools.server` to the same module that this
# process was loaded with.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_MCP_SERVERS: dict[str, dict[str, object]] = {
    "mytools": {
        "command": "uv",
        "args": ["run", "--directory", str(_REPO_ROOT), "python", "-m", "mytools.server"],
    },
}

# Derived from _MCP_SERVERS — every tool on every registered MCP server is
# allowed via the `mcp__<server>__*` wildcard, so this file stays in sync
# automatically. Adding a new server to _MCP_SERVERS above is the only
# change needed to expose all of its tools to the agent; the per-tool names
# and the allowlist never drift because there's no second list to author.
#
# (The CLI rule language has no `mcp__*__*` cross-server wildcard — the
# matcher uses strict equality on the parsed server name — so a derivation
# is the closest thing to "allow all MCP tools" that doesn't also bypass
# Bash permission gates via permission_mode="bypassPermissions".)
_MCP_ALLOWED_TOOLS: list[str] = [f"mcp__{name}__*" for name in _MCP_SERVERS]

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

    # Set writable cache locations (sandbox may make ~/.cache read-only)
    uv_cache = os.path.join(AGENT_CWD, ".uv-cache")
    mpl_config = os.path.join(AGENT_CWD, ".mpl-config")
    for d in [uv_cache, mpl_config]:
        os.makedirs(d, exist_ok=True)
    env["UV_CACHE_DIR"] = uv_cache
    env["MPLCONFIGDIR"] = mpl_config

    # Suppress GNOME keyring "secret-tool" errors in sandbox.
    # Point to a valid but unused address so secret-tool fails silently.
    env["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=/dev/null"

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
    TextBlockStartEvent,
    TextDeltaEvent,
    ThinkingBlockStartEvent,
    ThinkingDeltaEvent,
    ToolResultEvent,
    ToolUseEvent,
)


class ClaudeSDKClientAdapter:
    """Wraps ClaudeSDKClient, translating SDK messages into domain events.

    Runs the SDK in `include_partial_messages=True` mode so we can stream
    text/thinking deltas to the UI as they arrive. The adapter keeps a small
    amount of per-content-block state (open block kinds, buffered tool input
    JSON) so it can:
      - emit ``TextBlockStartEvent`` + ``TextDeltaEvent`` per text block
      - emit ``ThinkingBlockStartEvent`` + ``ThinkingDeltaEvent`` per thinking
      - buffer ``input_json_delta`` fragments and emit one ``ToolUseEvent``
        with the parsed input on ``content_block_stop``

    The buffered ``AssistantMessage`` that the SDK still delivers is then used
    only for ``model``/``usage`` metadata — its content blocks would duplicate
    what the stream events already produced.
    """

    def __init__(self, client: ClaudeSDKClient, created_files: set[str] | None = None) -> None:
        self._client = client
        self.created_files: set[str] = created_files if created_files is not None else set()
        self._current_message_id: str = ""
        self._open_blocks: dict[int, dict[str, Any]] = {}

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
            if isinstance(msg, StreamEvent):
                for event in self._handle_stream_event(msg):
                    yield event
            elif isinstance(msg, AssistantMessage):
                # Content blocks (text/thinking/tool_use) come from stream events;
                # only forward the model/usage metadata here. Tool *results* sometimes
                # arrive as ToolResultBlocks on AssistantMessage in synthetic flows,
                # so still emit those.
                for event in _translate_assistant_meta(msg):
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

    # -- StreamEvent dispatch -----------------------------------------------

    def _handle_stream_event(self, msg: StreamEvent) -> list[SDKEvent]:
        """Translate one raw Anthropic API stream event into domain events.

        Tracks per-content-block state across calls so deltas can be associated
        with their start events and tool input JSON can be assembled.
        """
        ev = msg.event or {}
        et = ev.get("type")

        if et == "message_start":
            inner = ev.get("message") or {}
            self._current_message_id = inner.get("id") or msg.uuid or ""
            self._open_blocks = {}
            return []

        if et == "content_block_start":
            return self._on_block_start(ev)

        if et == "content_block_delta":
            return self._on_block_delta(ev)

        if et == "content_block_stop":
            return self._on_block_stop(ev)

        # message_delta / message_stop / etc. — nothing to surface
        return []

    def _on_block_start(self, ev: dict[str, Any]) -> list[SDKEvent]:
        index = ev.get("index", 0)
        cb = ev.get("content_block") or {}
        cb_type = cb.get("type")

        # Initialize state for this open block. Tool-use blocks need a buffer
        # for the partial JSON deltas that follow.
        self._open_blocks[index] = {
            "type": cb_type,
            "id": cb.get("id"),
            "name": cb.get("name"),
            "json_buf": "",
        }

        if cb_type == "text":
            return [TextBlockStartEvent(
                block_index=index, message_id=self._current_message_id,
            )]
        if cb_type == "thinking":
            return [ThinkingBlockStartEvent(
                block_index=index, message_id=self._current_message_id,
            )]
        # tool_use: don't emit until we have the full input on content_block_stop
        return []

    def _on_block_delta(self, ev: dict[str, Any]) -> list[SDKEvent]:
        index = ev.get("index", 0)
        delta = ev.get("delta") or {}
        dt = delta.get("type")
        block = self._open_blocks.get(index)

        if dt == "text_delta":
            return [TextDeltaEvent(
                text=delta.get("text", ""),
                block_index=index,
                message_id=self._current_message_id,
            )]
        if dt == "thinking_delta":
            return [ThinkingDeltaEvent(
                thinking=delta.get("thinking", ""),
                block_index=index,
                message_id=self._current_message_id,
            )]
        if dt == "input_json_delta" and block is not None:
            block["json_buf"] = block.get("json_buf", "") + (delta.get("partial_json") or "")
        # signature_delta: not currently surfaced (cryptographic signature for
        # thinking blocks; unused by the UI).
        return []

    def _on_block_stop(self, ev: dict[str, Any]) -> list[SDKEvent]:
        index = ev.get("index", 0)
        block = self._open_blocks.pop(index, None)
        if block is None or block.get("type") != "tool_use":
            return []

        json_buf = block.get("json_buf") or ""
        try:
            parsed_input = json.loads(json_buf) if json_buf else {}
        except json.JSONDecodeError:
            parsed_input = {}

        return [ToolUseEvent(
            id=block.get("id") or "",
            name=block.get("name") or "",
            input=parsed_input if isinstance(parsed_input, dict) else {},
            message_id=self._current_message_id,
        )]


def _translate_assistant_meta(msg: AssistantMessage) -> list[SDKEvent]:
    """Forward only metadata from a buffered AssistantMessage.

    Content blocks (text/thinking/tool_use) are skipped because they're already
    produced by the streaming path. Tool result blocks, which sometimes appear
    on synthetic AssistantMessages, are still translated.
    """
    events: list[SDKEvent] = []
    if msg.model or msg.usage:
        events.append(ModelInfoEvent(model=msg.model or "", usage=msg.usage or {}))
    for block in msg.content:
        if isinstance(block, ToolResultBlock):
            content = block.content if isinstance(block.content, str) else str(block.content)
            events.append(
                ToolResultEvent(tool_use_id=block.tool_use_id, content=content, is_error=block.is_error or False)
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
            allowed_tools=[
                "Read", "Edit", "Bash", "Glob", "Grep", "Write", "Skill",
                *_MCP_ALLOWED_TOOLS,
            ],
            permission_mode="acceptEdits",
            cwd=AGENT_CWD,
            model=ANTHROPIC_MODEL or None,
            system_prompt=_load_system_prompt(output_dir, scripts_dir),
            setting_sources=["user", "project"],
            sandbox=_SANDBOX_SETTINGS,
            mcp_servers=_MCP_SERVERS,  # type: ignore[arg-type]
            hooks=hook_config["hooks"],
            env=_build_agent_env(),
            # Stream raw Anthropic API events alongside the buffered
            # AssistantMessage so the WS layer can forward text/thinking deltas
            # to the UI as they arrive instead of buffering until each block is
            # complete.
            include_partial_messages=True,
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
