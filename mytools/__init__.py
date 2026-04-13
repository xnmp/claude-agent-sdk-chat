"""mytools — a standalone MCP server exposing local Python code as agent tools.

Structurally independent of `backend/` so it can be extracted into its own
package later without touching callsites. The backend imports nothing from
here at import time: it only spawns `python -m mytools.server` as a
subprocess via `ClaudeAgentOptions.mcp_servers`.
"""
