"""Standalone stdio MCP server.

Runs as a subprocess of whatever MCP client spawns it (the Claude Agent SDK
in this repo, but any MCP client works). Communication is JSON-RPC over
stdin/stdout — no network, no sockets, no sandbox interaction.

Run directly:
    uv run python -m mytools.server

Or register via the Agent SDK:
    ClaudeAgentOptions(
        mcp_servers={
            "mytools": {
                "command": "uv",
                "args": ["run", "python", "-m", "mytools.server"],
            }
        },
        allowed_tools=[..., "mcp__mytools__ping", "mcp__mytools__echo"],
    )

Add tools by decorating async functions with ``@mcp.tool()`` — the decorator
reads the signature, type hints, and docstring to generate the MCP tool
schema. Keep the tool set small and focused; the agent picks tools by name
and description, so clear naming is more useful than clever implementations.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("mytools")


@mcp.tool()
async def ping() -> dict[str, str]:
    """Health check. Returns ``{"status": "ok"}``.

    Useful as a liveness probe and as the simplest possible end-to-end
    verification that the MCP plumbing is working.
    """
    return {"status": "ok"}


@mcp.tool()
async def echo(message: str) -> dict[str, str]:
    """Echo a message back to the caller.

    Args:
        message: The text to echo.
    """
    return {"echoed": message}


if __name__ == "__main__":
    mcp.run()
