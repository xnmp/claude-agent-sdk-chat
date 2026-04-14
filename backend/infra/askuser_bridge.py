"""Bridge between an in-process MCP `ask` tool and the WebSocket layer.

Each SDK session owns one `AskUserBridge`. The bridge exposes a single
in-process MCP server (`askuser`) with one tool (`ask`). When the agent
invokes `mcp__askuser__ask`, the tool function parks on an asyncio future;
the WebSocket router resolves that future when the frontend posts a
`question_answer` message, and the awaited answer becomes the tool result.

Only one question is allowed in flight at a time — the agent runs serially
within a turn so concurrent questions don't arise in practice. A stray
second call cancels the previous future defensively.
"""

from __future__ import annotations

import asyncio
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool
from claude_agent_sdk.types import McpSdkServerConfig
from loguru import logger

_QUESTION_TIMEOUT_SECONDS = 300.0


class AskUserBridge:
    """Per-session bridge holding the pending-answer future."""

    def __init__(self) -> None:
        self._pending: asyncio.Future[str] | None = None

    def has_pending(self) -> bool:
        return self._pending is not None and not self._pending.done()

    def submit_answer(self, answer: str) -> bool:
        """Resolve the currently-pending question.

        Returns True iff a question was waiting. A False return means the
        client posted a stray answer (no question outstanding) and the WS
        handler can ignore it.
        """
        if self._pending is None or self._pending.done():
            logger.warning("askuser: submit_answer called with no pending question")
            return False
        self._pending.set_result(answer)
        return True

    def create_server(self) -> McpSdkServerConfig:
        bridge = self

        @tool(
            name="ask",
            description=(
                "Ask the end user a clarifying multiple-choice question. The "
                "user sees the question with the supplied options as buttons "
                "and clicks one. Returns the chosen option as a string. Use "
                "this whenever you need a quick disambiguation from the user "
                "rather than guessing."
            ),
            input_schema={"question": str, "options": list[str]},
        )
        async def ask(args: dict[str, Any]) -> dict[str, Any]:
            question = args.get("question") or ""
            options = args.get("options") or []
            logger.info("askuser: ask question={!r} options={}", question, options)

            if bridge._pending is not None and not bridge._pending.done():
                bridge._pending.cancel()

            loop = asyncio.get_running_loop()
            bridge._pending = loop.create_future()

            try:
                answer = await asyncio.wait_for(
                    bridge._pending, timeout=_QUESTION_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                logger.warning(
                    "askuser: timeout after {}s with no answer", _QUESTION_TIMEOUT_SECONDS,
                )
                return {
                    "content": [
                        {"type": "text", "text": "User did not respond within 5 minutes."}
                    ],
                    "isError": True,
                }
            finally:
                bridge._pending = None

            logger.info("askuser: returning answer={!r}", answer)
            return {"content": [{"type": "text", "text": answer}]}

        return create_sdk_mcp_server(name="askuser", tools=[ask])
