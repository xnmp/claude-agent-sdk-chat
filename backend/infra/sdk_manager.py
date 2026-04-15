"""Session-construction and lifecycle for ``ClaudeSDKClient``s.

Two responsibilities live here:

- **Construction helpers** — system prompt loading, sandbox settings, MCP
  server config, agent environment scrubbing. These are all the knobs we
  pass to ``ClaudeAgentOptions`` when spawning a new session.
- **Session lifecycle** — ``SDKManager`` caches clients by session id,
  evicts idle ones, and wires up hooks + askuser bridges.

Message-translation (stream events → domain ``SDKEvent``s) lives in
``sdk_adapter.py``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from loguru import logger

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

from ..config import (
    AGENT_CWD,
    ANTHROPIC_API_KEY,
    ANTHROPIC_AUTH_TOKEN,
    ANTHROPIC_MODEL,
    AUTH_PROXY_ENABLED,
    AUTH_PROXY_PORT,
)
from .askuser_bridge import AskUserBridge
from .hooks import make_hooks
from .sdk_adapter import ClaudeSDKClientAdapter

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

# process was loaded with.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_MCP_ROOT = _REPO_ROOT / "backend" / "mcps"

def _discover_mcp_servers() -> dict[str, dict[str, object]]:
    """Scan _MCP_ROOT/scripts/*.py and register each as an MCP server.

    Server name is the filename stem with a trailing '_mcp' stripped
    (e.g. teradata_mcp.py → teradata).  Falls back to an empty dict
    if the directory doesn't exist so a missing checkout doesn't crash startup.
    """
    scripts_dir = _MCP_ROOT
    python_bin = str(_REPO_ROOT / ".venv" / "bin" / "python")
    servers: dict[str, dict[str, object]] = {}

    if not scripts_dir.exists():
        logger.warning("MCP scripts dir not found, skipping discovery: {}", scripts_dir)
        return servers

    for script in sorted(scripts_dir.glob("*.py")):
        name = script.stem.removesuffix("_mcp")
        servers[name] = {"command": python_bin, "args": [str(script)]}
        logger.info("discovered MCP server: name={} script={}", name, script)

    return servers

_MCP_SERVERS: dict[str, dict[str, object]] = _discover_mcp_servers()

logger.warning("MCP servers registered: {}", _MCP_SERVERS)

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
