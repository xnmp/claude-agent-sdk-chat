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
        assert names == {"ping", "get_weather"}

    async def test_ping_schema_has_no_arguments(self) -> None:
        tools = await mcp.list_tools()
        ping = next(t for t in tools if t.name == "ping")
        assert ping.inputSchema.get("properties") == {}

    async def test_get_weather_schema_requires_location_string(self) -> None:
        tools = await mcp.list_tools()
        weather = next(t for t in tools if t.name == "get_weather")
        assert weather.inputSchema["required"] == ["location"]
        assert weather.inputSchema["properties"]["location"]["type"] == "string"

    async def test_ping_returns_ok(self) -> None:
        result = await mcp.call_tool("ping", {})
        # FastMCP.call_tool returns a tuple: (content_blocks, structured_output).
        # The structured output holds the actual dict the tool returned.
        _content, structured = result
        assert structured == {"status": "ok"}

    async def test_get_weather_returns_location_and_weather(self) -> None:
        _content, structured = await mcp.call_tool(
            "get_weather", {"location": "sydney"}
        )
        assert structured == {"location": "sydney", "weather": "windy"}


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

    def test_allowlist_is_derived_from_registered_servers(self) -> None:
        # _MCP_ALLOWED_TOOLS must be a pure function of _MCP_SERVERS — one
        # wildcard entry per registered server and nothing else. That's the
        # contract that keeps "add a new MCP server" a one-liner instead of
        # a two-file edit, and it's the only reason this file doesn't need
        # to name individual tools.
        expected = {f"mcp__{name}__*" for name in _MCP_SERVERS}
        assert set(_MCP_ALLOWED_TOOLS) == expected
        # Regression guard: the derivation must actually cover every server.
        for name in _MCP_SERVERS:
            assert f"mcp__{name}__*" in _MCP_ALLOWED_TOOLS


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
async def test_agent_can_invoke_mytools_get_weather(tmp_path, monkeypatch) -> None:
    """End-to-end: agent runs mcp__mytools__get_weather through the stdio MCP server."""
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
                "Use the get_weather tool to check the weather in Sydney, "
                "then stop. Do not call any other tools."
            )
            events = await asyncio.wait_for(_collect(adapter), timeout=120)
        finally:
            await manager.remove(session_id)

        tool_uses = [e for e in events if isinstance(e, ToolUseEvent)]
        weather_uses = [e for e in tool_uses if e.name == "mcp__mytools__get_weather"]
        assert weather_uses, (
            "Agent did not invoke mcp__mytools__get_weather. "
            f"Tool uses seen: {[e.name for e in tool_uses]}"
        )
        # Asserting on the argument proves the schema flowed all the way
        # through to the model's tool-call — a stronger guarantee than ping
        # (which has an empty argument schema).
        assert "location" in weather_uses[0].input
        assert "sydney" in str(weather_uses[0].input["location"]).lower()

        results = [e for e in events if isinstance(e, ResultEvent)]
        assert results, f"No ResultEvent in agent events: {events}"
        assert not results[-1].is_error, f"Agent turn errored: {results[-1]}"
    finally:
        await stop_proxy()
