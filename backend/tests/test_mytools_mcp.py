"""Unit + integration tests for the mytools stdio MCP server.

Unit tests exercise the FastMCP instance directly: they don't need the Claude
SDK or network, so they always run.

The integration test spawns a real agent via SDKManager, prompts it to invoke
``mcp__mytools__ping``, and asserts both that the MCP subprocess got wired up
and that the agent's tool-use event flows through to the SDK adapter
correctly. Skipped unless `claude` and `bwrap` are on PATH — same precondition
as the existing sandbox integration tests — and makes one real API call per
run.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import uuid

import pytest

from backend.domain.models import ResultEvent, SDKEvent, ToolUseEvent
from backend.infra.auth_proxy import start_proxy, stop_proxy
from backend.infra.sdk_manager import (
    _MCP_ALLOWED_TOOLS,
    _MCP_SERVERS,
    SDKManager,
)
from mytools.server import mcp


# ---------------------------------------------------------------------------
# Unit tests — pure FastMCP, no SDK
# ---------------------------------------------------------------------------


class TestMytoolsServer:
    async def test_both_tools_are_registered(self) -> None:
        tools = await mcp.list_tools()
        names = {t.name for t in tools}
        assert names == {"ping", "echo"}

    async def test_ping_schema_has_no_arguments(self) -> None:
        tools = await mcp.list_tools()
        ping = next(t for t in tools if t.name == "ping")
        assert ping.inputSchema.get("properties") == {}

    async def test_echo_schema_requires_message_string(self) -> None:
        tools = await mcp.list_tools()
        echo = next(t for t in tools if t.name == "echo")
        assert echo.inputSchema["required"] == ["message"]
        assert echo.inputSchema["properties"]["message"]["type"] == "string"

    async def test_ping_returns_ok(self) -> None:
        result = await mcp.call_tool("ping", {})
        # FastMCP.call_tool returns a tuple: (content_blocks, structured_output).
        # The structured output holds the actual dict the tool returned.
        _content, structured = result
        assert structured == {"status": "ok"}

    async def test_echo_returns_message(self) -> None:
        _content, structured = await mcp.call_tool("echo", {"message": "hi"})
        assert structured == {"echoed": "hi"}


class TestSdkManagerWiring:
    def test_mcp_server_registered(self) -> None:
        assert "mytools" in _MCP_SERVERS
        cfg = _MCP_SERVERS["mytools"]
        assert cfg["command"] == "uv"
        # The argv must run the package as a module, not a script path, so it
        # survives being invoked from any cwd.
        args = cfg["args"]
        assert isinstance(args, list)
        assert "-m" in args
        assert "mytools.server" in args

    async def test_allowed_tools_cover_every_server_tool(self) -> None:
        # If a new tool is added to mytools/server.py without extending
        # _MCP_ALLOWED_TOOLS, the agent will silently lose the ability to
        # call it. This test forces the two to stay in sync.
        registered = {t.name for t in await mcp.list_tools()}
        allowed_suffixes = {t.split("__")[-1] for t in _MCP_ALLOWED_TOOLS}
        missing = registered - allowed_suffixes
        assert not missing, (
            f"mytools.server exposes tools the agent is not allowed to call: {missing}"
        )


# ---------------------------------------------------------------------------
# Integration test — real SDK, real MCP subprocess
# ---------------------------------------------------------------------------


integration_required = [
    pytest.mark.skipif(
        shutil.which("claude") is None, reason="claude CLI not in PATH"
    ),
    pytest.mark.skipif(
        shutil.which("bwrap") is None, reason="bwrap not in PATH"
    ),
]


async def _collect(adapter) -> list[SDKEvent]:
    return [e async for e in adapter.receive_response()]


@pytest.mark.integration
@pytest.mark.skipif(
    shutil.which("claude") is None, reason="claude CLI not in PATH"
)
@pytest.mark.skipif(
    shutil.which("bwrap") is None, reason="bwrap not in PATH"
)
async def test_agent_can_invoke_mytools_ping(tmp_path, monkeypatch) -> None:
    """End-to-end: agent runs mcp__mytools__ping through the stdio MCP server."""
    monkeypatch.setattr("backend.infra.sdk_manager.AGENT_CWD", str(tmp_path))

    # Pick a free port for the auth proxy so this can run alongside a dev server.
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        auth_port = s.getsockname()[1]
    monkeypatch.setattr("backend.infra.sdk_manager.AUTH_PROXY_PORT", auth_port)

    upstream = os.environ.get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com"
    await start_proxy(auth_port, os.environ.get("ANTHROPIC_API_KEY", ""), upstream)

    try:
        manager = SDKManager()
        session_id = str(uuid.uuid4())
        adapter = await manager.create(session_id=session_id)
        await adapter.connect()
        try:
            await adapter.query(
                "Call the `mcp__mytools__ping` tool exactly once, then stop. "
                "Do not call any other tools."
            )
            events = await asyncio.wait_for(_collect(adapter), timeout=120)
        finally:
            await manager.remove(session_id)

        tool_uses = [e for e in events if isinstance(e, ToolUseEvent)]
        ping_uses = [e for e in tool_uses if e.name == "mcp__mytools__ping"]
        assert ping_uses, (
            "Agent did not invoke mcp__mytools__ping. "
            f"Tool uses seen: {[e.name for e in tool_uses]}"
        )

        results = [e for e in events if isinstance(e, ResultEvent)]
        assert results, f"No ResultEvent in agent events: {events}"
        assert not results[-1].is_error, f"Agent turn errored: {results[-1]}"
    finally:
        await stop_proxy()
