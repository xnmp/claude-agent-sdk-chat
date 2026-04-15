"""Manages ClaudeSDKClient instances per active conversation.

This is the ONLY module that imports from claude_agent_sdk.
It translates SDK types into domain events (SDKEvent) so that
all downstream code depends only on domain types.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from loguru import logger

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

from ..config import AGENT_CWD, ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, ANTHROPIC_MODEL, AUTH_PROXY_ENABLED, AUTH_PROXY_PORT
from .askuser_bridge import AskUserBridge
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

    When no ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN is configured, the CLI uses its own stored
    credentials (OAuth from ~/.claude/), so we don't override it.
    """
    if not AUTH_PROXY_ENABLED:
        logger.info("auth proxy disabled; agent inherits parent env unchanged")
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

    # Only override the API key when we have credentials to inject via proxy.
    # Otherwise let the CLI use its own stored credentials (OAuth from ~/.claude/).
    if ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN:
        if ANTHROPIC_API_KEY:
            logger.info("Using auth proxy with injected API key; setting %s=proxy-managed", "ANTHROPIC_API_KEY")
        else:
            logger.info("Using auth proxy with injected AUTH token; setting %s=proxy-managed", "ANTHROPIC_AUTH_TOKEN")
        env["ANTHROPIC_API_KEY"] = "proxy-managed"

    # Point agent to the local auth proxy
    env["ANTHROPIC_BASE_URL"] = f"http://127.0.0.1:{AUTH_PROXY_PORT}"

    logger.info("built agent env with keys={}", sorted(env.keys()))
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
    TextEvent,
    ThinkingBlockStartEvent,
    ThinkingDeltaEvent,
    ThinkingEvent,
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

    Start events (``TextBlockStartEvent`` / ``ThinkingBlockStartEvent``) are
    **deferred** until the first corresponding delta arrives, so empty content
    blocks (``content_block_start`` followed immediately by ``content_block_stop``
    with no deltas in between, as sometimes seen on models that open a
    placeholder text block before streaming thinking) don't leak empty bubbles
    into the UI.

    The buffered ``AssistantMessage`` is usually just metadata (``model``,
    ``usage``), but with some models the stream can stop emitting events after
    thinking deltas — the final text answer and any tool_use blocks then only
    arrive via ``AssistantMessage``. In that case the adapter reconciles the
    buffered content against what the stream already produced (tracked via
    the ``_streamed_*`` flags) and emits ``TextEvent`` / ``ThinkingEvent`` /
    ``ToolUseEvent`` for any block the stream didn't cover.
    """

    def __init__(
        self,
        client: ClaudeSDKClient,
        created_files: set[str] | None = None,
        askuser_bridge: AskUserBridge | None = None,
    ) -> None:
        self._client = client
        self.created_files: set[str] = created_files if created_files is not None else set()
        self.askuser_bridge: AskUserBridge | None = askuser_bridge
        self._current_message_id: str = ""
        self._open_blocks: dict[int, dict[str, Any]] = {}
        # Per-message reconciliation state — reset on every ``message_start``.
        # Tracks what the *stream* path successfully produced, so the buffered
        # ``AssistantMessage`` handler can emit only the blocks the stream
        # didn't already cover. See ``_translate_assistant_meta``.
        self._streamed_text_had_content: bool = False
        self._streamed_thinking_had_content: bool = False
        self._streamed_tool_use_ids: set[str] = set()

    def submit_question_answer(self, answer: str) -> bool:
        """Resolve a pending askuser question with the user's answer.

        Returns False if no question is outstanding (stray client message).
        """
        if self.askuser_bridge is None:
            return False
        return self.askuser_bridge.submit_answer(answer)

    async def connect(self) -> None:
        logger.debug("sdk adapter: connect")
        await self._client.connect()

    async def query(self, content: str) -> None:
        logger.debug("sdk adapter: query len={}", len(content))
        await self._client.query(content)

    async def interrupt(self) -> None:
        logger.info("sdk adapter: interrupt")
        await self._client.interrupt()

    async def disconnect(self) -> None:
        logger.debug("sdk adapter: disconnect")
        await self._client.disconnect()

    def pop_created_files(self) -> list[str]:
        """Return and clear the list of files created during the last turn."""
        files = sorted(self.created_files)
        self.created_files.clear()
        return files

    async def receive_response(self) -> AsyncIterator[SDKEvent]:
        async for msg in self._client.receive_response():
            events: list[SDKEvent]
            match msg:
                case StreamEvent():
                    events = self._handle_stream_event(msg)
                case AssistantMessage():
                    logger.info("sdk AssistantMessage: blocks={}", _block_summary(msg.content))
                    events = self._translate_assistant_meta(msg)
                case UserMessage():
                    logger.info("sdk UserMessage: blocks={}",
                                _block_summary(msg.content) if isinstance(msg.content, list) else "str")
                    events = _translate_user(msg)
                case ResultMessage():
                    logger.info(
                        "sdk ResultMessage: duration_ms={} cost=${:.4f} turns={} error={}",
                        msg.duration_ms, msg.total_cost_usd or 0.0, msg.num_turns, msg.is_error,
                    )
                    events = [ResultEvent(
                        session_id=msg.session_id,
                        duration_ms=msg.duration_ms,
                        total_cost_usd=msg.total_cost_usd or 0.0,
                        num_turns=msg.num_turns,
                        is_error=msg.is_error,
                        created_files=self.pop_created_files(),
                    )]
                case _:
                    events = []
            for event in events:
                yield event

    # -- StreamEvent dispatch -----------------------------------------------

    def _handle_stream_event(self, msg: StreamEvent) -> list[SDKEvent]:
        """Translate one raw Anthropic API stream event into domain events.

        Tracks per-content-block state across calls so deltas can be associated
        with their start events and tool input JSON can be assembled.
        """
        ev = msg.event or {}
        et = ev.get("type")
        logger.debug("stream event: {}", et)

        if et == "message_start":
            inner = ev.get("message") or {}
            self._current_message_id = inner.get("id") or msg.uuid or ""
            self._open_blocks = {}
            self._streamed_text_had_content = False
            self._streamed_thinking_had_content = False
            self._streamed_tool_use_ids = set()
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
        logger.debug("block start: index={} type={} name={}", index, cb_type, cb.get("name"))

        # Initialize state for this open block. Tool-use blocks need a buffer
        # for the partial JSON deltas that follow. ``start_emitted`` tracks
        # whether we've already yielded the paired Start event — deferred until
        # the first delta arrives so empty content blocks (start+stop with no
        # deltas) don't leak empty bubbles into the UI.
        self._open_blocks[index] = {
            "type": cb_type,
            "id": cb.get("id"),
            "name": cb.get("name"),
            "json_buf": "",
            "start_emitted": False,
        }
        # text/thinking: defer start event until first delta
        # tool_use: emit nothing until content_block_stop gives us full input
        return []

    def _on_block_delta(self, ev: dict[str, Any]) -> list[SDKEvent]:
        index = ev.get("index", 0)
        delta = ev.get("delta") or {}
        dt = delta.get("type")
        block = self._open_blocks.get(index)

        if dt == "text_delta":
            self._streamed_text_had_content = True
            events: list[SDKEvent] = []
            if block is not None and not block.get("start_emitted"):
                events.append(TextBlockStartEvent(
                    block_index=index, message_id=self._current_message_id,
                ))
                block["start_emitted"] = True
            events.append(TextDeltaEvent(
                text=delta.get("text", ""),
                block_index=index,
                message_id=self._current_message_id,
            ))
            return events
        if dt == "thinking_delta":
            self._streamed_thinking_had_content = True
            events = []
            if block is not None and not block.get("start_emitted"):
                events.append(ThinkingBlockStartEvent(
                    block_index=index, message_id=self._current_message_id,
                ))
                block["start_emitted"] = True
            events.append(ThinkingDeltaEvent(
                thinking=delta.get("thinking", ""),
                block_index=index,
                message_id=self._current_message_id,
            ))
            return events
        if dt == "input_json_delta" and block is not None:
            block["json_buf"] = block.get("json_buf", "") + (delta.get("partial_json") or "")
        # signature_delta: not currently surfaced (cryptographic signature for
        # thinking blocks; unused by the UI).
        return []

    def _on_block_stop(self, ev: dict[str, Any]) -> list[SDKEvent]:
        index = ev.get("index", 0)
        block = self._open_blocks.pop(index, None)
        logger.debug("block stop: index={} type={}", index, block.get("type") if block else None)
        if block is None or block.get("type") != "tool_use":
            return []

        json_buf = block.get("json_buf") or ""
        try:
            parsed_input = json.loads(json_buf) if json_buf else {}
        except json.JSONDecodeError:
            logger.warning("tool_use block: failed to parse input JSON (index={}, name={})", index, block.get("name"))
            parsed_input = {}

        tool_id = block.get("id") or ""
        logger.info(
            "sdk stream tool_use: name={} id={} {}",
            block.get("name"), _short_id(tool_id), _short_args(parsed_input),
        )
        if tool_id:
            self._streamed_tool_use_ids.add(tool_id)
        return [ToolUseEvent(
            id=tool_id,
            name=block.get("name") or "",
            input=parsed_input if isinstance(parsed_input, dict) else {},
            message_id=self._current_message_id,
        )]

    # -- Buffered-message reconciliation -----------------------------------

    def _translate_assistant_meta(self, msg: AssistantMessage) -> list[SDKEvent]:
        """Translate a buffered ``AssistantMessage`` into domain events.

        Always forwards model/usage metadata and any ``ToolResultBlock``s.
        For ``TextBlock`` / ``ThinkingBlock`` / ``ToolUseBlock``, reconciles
        against what the stream path already produced (via
        ``_streamed_text_had_content``, ``_streamed_thinking_had_content``,
        ``_streamed_tool_use_ids``) and emits only blocks the stream didn't
        cover. This handles models where the SDK stops yielding stream events
        after thinking deltas and the final content only arrives buffered.
        """
        events: list[SDKEvent] = []
        if msg.model or msg.usage:
            events.append(ModelInfoEvent(model=msg.model or "", usage=msg.usage or {}))
        for block in msg.content:
            if isinstance(block, ToolResultBlock):
                content = block.content if isinstance(block.content, str) else str(block.content)
                events.append(ToolResultEvent(
                    tool_use_id=block.tool_use_id,
                    content=content,
                    is_error=block.is_error or False,
                ))
            elif isinstance(block, ToolUseBlock):
                if block.id in self._streamed_tool_use_ids:
                    continue
                self._streamed_tool_use_ids.add(block.id)
                logger.info(
                    "reconcile tool_use: name={} id={} {}",
                    block.name, _short_id(block.id), _short_args(block.input),
                )
                events.append(ToolUseEvent(
                    id=block.id,
                    name=block.name,
                    input=block.input if isinstance(block.input, dict) else {},
                    message_id=self._current_message_id,
                ))
            elif isinstance(block, TextBlock):
                if self._streamed_text_had_content:
                    continue
                self._streamed_text_had_content = True
                logger.info("reconcile text: len={} {}", len(block.text), _preview(block.text))
                events.append(TextEvent(text=block.text, message_id=self._current_message_id))
            elif isinstance(block, ThinkingBlock):
                if self._streamed_thinking_had_content:
                    continue
                self._streamed_thinking_had_content = True
                logger.info("reconcile thinking: len={} {}", len(block.thinking), _preview(block.thinking))
                events.append(ThinkingEvent(
                    thinking=block.thinking,
                    signature=block.signature or "",
                    message_id=self._current_message_id,
                ))
        return events


# -- Logging helpers --------------------------------------------------------
#
# Kept at module level so they're usable from both the receive_response
# summary logs and the deeper _on_block_stop / _translate_assistant_meta
# call sites without duplicating truncation logic.


def _preview(s: str, n: int = 15) -> str:
    """Short quoted preview of a text blob for log lines."""
    head = s[:n].replace("\n", " ")
    return f'"{head}{"…" if len(s) > n else ""}"'


def _short_id(s: str) -> str:
    """Last 8 chars of an id. Tool-use ids look like ``toolu_01Abc…`` — the
    prefix is fixed noise, the trailing entropy is what's useful to correlate
    tool_use ↔ tool_result across log lines."""
    return s[-8:] if len(s) > 8 else s


def _short_args(args: Any) -> str:
    """Compact JSON-ish preview of a tool_use input dict.

    Each top-level value is individually truncated to 15 chars so long
    commands / file bodies / descriptions don't blow out the log line.
    """
    if not isinstance(args, dict):
        return _preview(str(args))

    def trunc_value(v: Any) -> str:
        s = v if isinstance(v, str) else json.dumps(v, separators=(",", ":"))
        head = s[:15].replace("\n", " ")
        quoted = isinstance(v, str)
        body = f"{head}{'…' if len(s) > 15 else ''}"
        return f'"{body}"' if quoted else body

    parts = [f'"{k}":{trunc_value(v)}' for k, v in args.items()]
    return "{" + ",".join(parts) + "}"


def _short_result(content: Any) -> str:
    """Truncated preview of a tool_result's content for log lines."""
    s = content if isinstance(content, str) else str(content)
    return _preview(s, 30)


def _block_summary(content: list[Any]) -> str:
    """One-line description of a content-block list for logging."""
    parts: list[str] = []
    for b in content:
        if isinstance(b, TextBlock):
            parts.append(f"text({len(b.text)},{_preview(b.text)})")
        elif isinstance(b, ThinkingBlock):
            parts.append(f"thinking({len(b.thinking)},{_preview(b.thinking)})")
        elif isinstance(b, ToolUseBlock):
            parts.append(f"tool_use({b.name},id={_short_id(b.id)},{_short_args(b.input)})")
        elif isinstance(b, ToolResultBlock):
            parts.append(f"tool_result(id={_short_id(b.tool_use_id)},{_short_result(b.content)})")
        else:
            parts.append(type(b).__name__)
    return "[" + ",".join(parts) + "]"


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
            logger.debug("sdk manager: reuse cached client session={}", session_id)
            self._last_access[session_id] = _now()
            return self._clients[session_id]

        logger.info(
            "sdk manager: creating client session={} resume={} model={}",
            session_id, resume, ANTHROPIC_MODEL or "<default>",
        )

        # Per-session subdirectories under shared output roots. The FastAPI
        # static mount still serves the whole AGENT_CWD/output tree at
        # /api/output, so tracked files are reported as "<session_id>/<name>"
        # via hooks' track_root and resolve via the URL scheme unchanged.
        output_root = os.path.join(AGENT_CWD, "output")
        scripts_root = os.path.join(AGENT_CWD, "output_scripts")
        output_dir = os.path.join(output_root, session_id)
        scripts_dir = os.path.join(scripts_root, session_id)
        uploads_dir = os.path.join(AGENT_CWD, "uploads")
        docs_dir = os.path.join(AGENT_CWD, "docs")
        for d in [output_dir, scripts_dir, uploads_dir, docs_dir]:
            os.makedirs(d, exist_ok=True)
        hook_config = make_hooks(
            output_dir,
            scripts_dir,
            uploads_dir,
            extra_readable_dirs=[
                os.path.expanduser("~/.claude/skills"),
                str(_REPO_ROOT / ".claude" / "skills"),
            ],
            extra_writable_dirs=[docs_dir],
            track_root=output_root,
        )

        # Per-session askuser bridge — its in-process MCP server holds a
        # reference to a per-session asyncio future, so a fresh bridge (and
        # fresh server config) is built for every new session.
        askuser_bridge = AskUserBridge()
        mcp_servers: dict[str, Any] = {
            **_MCP_SERVERS,
            "askuser": askuser_bridge.create_server(),
        }

        options = ClaudeAgentOptions(
            allowed_tools=[
                "Read", "Edit", "Bash", "Glob", "Grep", "Write", "Skill",
                *_MCP_ALLOWED_TOOLS,
                "mcp__askuser__ask",
            ],
            permission_mode="acceptEdits",
            cwd=AGENT_CWD,
            model=ANTHROPIC_MODEL or None,
            system_prompt=_load_system_prompt(output_dir, scripts_dir),
            setting_sources=["user", "project"],
            sandbox=_SANDBOX_SETTINGS,
            mcp_servers=mcp_servers,  # type: ignore[arg-type]
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
        adapter = ClaudeSDKClientAdapter(
            client, hook_config["created_files"], askuser_bridge=askuser_bridge,
        )
        self._clients[session_id] = adapter
        self._last_access[session_id] = _now()
        logger.info(
            "sdk manager: client ready session={} output_dir={} active_sessions={}",
            session_id, output_dir, len(self._clients),
        )
        return adapter

    async def remove(self, session_id: str) -> None:
        self._last_access.pop(session_id, None)
        adapter = self._clients.pop(session_id, None)
        if adapter:
            logger.info("sdk manager: removing client session={}", session_id)
            try:
                await adapter.disconnect()
            except Exception as exc:
                logger.warning("sdk manager: disconnect failed session={} error={}", session_id, exc)

    def has(self, session_id: str) -> bool:
        return session_id in self._clients

    async def _evict_idle(self) -> None:
        """Remove clients that have been idle longer than the TTL."""
        now = _now()
        expired = [
            sid for sid, ts in self._last_access.items()
            if now - ts > self._idle_ttl
        ]
        if expired:
            logger.info("sdk manager: evicting idle sessions={}", expired)
        for sid in expired:
            await self.remove(sid)


def _now() -> float:
    import time
    return time.monotonic()
