"""Translates ``claude_agent_sdk`` messages into domain ``SDKEvent``s.

This is the *only* module (besides ``sdk_manager``, which constructs the
client) that imports from ``claude_agent_sdk``. Everything downstream of
``receive_response()`` depends only on domain types.

Responsibilities:

- **Stream-event handling** — the SDK runs in ``include_partial_messages``
  mode, so text/thinking/tool_use blocks are driven by raw Anthropic API
  streaming events (``content_block_start`` / ``content_block_delta`` /
  ``content_block_stop``). This file buffers partial state per open block
  and emits ``TextBlockStartEvent`` / ``TextDeltaEvent`` / ``ToolUseEvent``
  etc. at the right moments.
- **Reconciliation with buffered ``AssistantMessage``** — on some models
  the stream stops emitting events part-way through a turn and the final
  content only arrives on the buffered message. The adapter tracks what
  the stream already produced (via ``_streamed_*`` flags) and emits only
  the blocks the stream didn't cover, with id-level dedup for tool_use so
  whichever path arrives first "wins" and the other skips.
- **Deferred start events** — ``TextBlockStartEvent`` /
  ``ThinkingBlockStartEvent`` are held until the first corresponding
  delta, so empty content blocks (start immediately followed by stop with
  no deltas) don't leak empty bubbles into the UI.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from loguru import logger

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeSDKClient,
    ResultMessage,
    StreamEvent,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

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
from .askuser_bridge import AskUserBridge


# -- Logging helpers --------------------------------------------------------
#
# Kept at module level so ``_on_block_stop`` and ``_translate_assistant_meta``
# can share the truncation logic with ``_block_summary`` (used by
# ``receive_response``'s top-level log lines).


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


# -- Adapter ---------------------------------------------------------------


class ClaudeSDKClientAdapter:
    """Wraps ``ClaudeSDKClient``, translating SDK messages into domain events.

    See the module docstring for the overall event-flow model. This class
    holds only the per-message state needed to interpret the SDK's stream
    and reconcile it against buffered ``AssistantMessage``s.
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
        try:
            await self._client.connect()
        except Exception as exc:
            logger.error(
                "sdk adapter: connect failed — {} | stderr={}",
                exc,
                getattr(exc, "stderr", None) or getattr(exc, "error_output", None) or "N/A",
            )
            raise

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
                    logger.info(
                        "sdk UserMessage: blocks={}",
                        _block_summary(msg.content) if isinstance(msg.content, list) else "str",
                    )
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
        # Dedup against reconciliation: if the buffered AssistantMessage
        # arrived before this content_block_stop, reconciliation already
        # emitted a ToolUseEvent for this id and added it to the set. Don't
        # emit a duplicate.
        if tool_id and tool_id in self._streamed_tool_use_ids:
            logger.debug(
                "sdk stream tool_use: dedup name={} id={} (already reconciled)",
                block.get("name"), _short_id(tool_id),
            )
            return []
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
