"""Background LLM tasks — title generation and follow-up suggestions.

Uses the Anthropic API directly (not the Agent SDK) with a small/fast model.

Authentication falls back through two paths:
1. If ANTHROPIC_API_KEY is a real API key (starts with "sk-ant-api"), send
   it as the x-api-key header.
2. Otherwise try Claude Code's stored OAuth credentials from
   ~/.claude/.credentials.json and send them as a Bearer token with the
   `oauth-2025-04-20` beta header. OAuth tokens also require the
   "You are Claude Code..." system prompt.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from anthropic import AsyncAnthropic
from anthropic.types import TextBlock

from ..config import ANTHROPIC_API_KEY, ANTHROPIC_BASE_URL, ANTHROPIC_SMALL_FAST_MODEL
from .claude_credentials import load_oauth_credentials

logger = logging.getLogger(__name__)

# OAuth tokens from Claude Code are only accepted by the API when paired with
# a system prompt that identifies the caller as Claude Code.
_CLAUDE_CODE_SYSTEM_PROMPT = "You are Claude Code, Anthropic's official CLI for Claude."


@dataclass(frozen=True)
class _ClientHandle:
    client: AsyncAnthropic
    is_oauth: bool


def _base_url_kwarg() -> dict[str, str]:
    if ANTHROPIC_BASE_URL and ANTHROPIC_BASE_URL.startswith("http"):
        return {"base_url": ANTHROPIC_BASE_URL}
    # Prevent the SDK from picking up an empty ANTHROPIC_BASE_URL from env
    return {"base_url": "https://api.anthropic.com"}


def _get_client() -> _ClientHandle | None:
    # Prefer a real API key when explicitly configured
    if ANTHROPIC_API_KEY and ANTHROPIC_API_KEY.startswith("sk-ant-api"):
        kwargs: dict[str, Any] = {"api_key": ANTHROPIC_API_KEY, **_base_url_kwarg()}
        return _ClientHandle(AsyncAnthropic(**kwargs), is_oauth=False)

    # Fall back to Claude Code's OAuth credentials
    creds = load_oauth_credentials()
    if creds is not None:
        oauth_kwargs: dict[str, Any] = {
            "auth_token": creds.access_token,
            "default_headers": {"anthropic-beta": "oauth-2025-04-20"},
            **_base_url_kwarg(),
        }
        return _ClientHandle(AsyncAnthropic(**oauth_kwargs), is_oauth=True)

    return None


def _system_for(handle: _ClientHandle) -> str:
    """Claude Code system prompt required by OAuth; empty string otherwise."""
    return _CLAUDE_CODE_SYSTEM_PROMPT if handle.is_oauth else ""


async def generate_title(user_message: str, assistant_response: str) -> str | None:
    """Generate a short conversation title from the first exchange."""
    handle = _get_client()
    if handle is None:
        return None

    try:
        response = await handle.client.messages.create(
            model=ANTHROPIC_SMALL_FAST_MODEL,
            max_tokens=50,
            system=_system_for(handle),
            messages=[{
                "role": "user",
                "content": (
                    "Generate a very short title (max 6 words) for a conversation that starts with:\n\n"
                    f"User: {user_message[:200]}\n"
                    f"Assistant: {assistant_response[:200]}\n\n"
                    "Reply with ONLY the title, no quotes or punctuation."
                ),
            }],
        )
        block = response.content[0]
        if not isinstance(block, TextBlock):
            return None
        title = block.text.strip().strip('"\'')
        return title[:80] if title else None
    except Exception:
        logger.warning("Title generation failed", exc_info=True)
        return None


async def generate_follow_ups(
    user_message: str, assistant_response: str,
) -> list[str]:
    """Generate 2-3 follow-up question suggestions."""
    handle = _get_client()
    if handle is None:
        return []

    try:
        response = await handle.client.messages.create(
            model=ANTHROPIC_SMALL_FAST_MODEL,
            max_tokens=200,
            system=_system_for(handle),
            messages=[{
                "role": "user",
                "content": (
                    "Given this conversation:\n\n"
                    f"User: {user_message[:300]}\n"
                    f"Assistant: {assistant_response[:500]}\n\n"
                    "Suggest 2-3 short follow-up questions the user might ask. "
                    "Reply as a JSON array of strings, e.g. [\"question 1\", \"question 2\"]. "
                    "Keep each question under 60 characters. Reply with ONLY the JSON array."
                ),
            }],
        )
        block = response.content[0]
        if not isinstance(block, TextBlock):
            return []
        text = block.text.strip()
        if not text:
            return []
        # Extract JSON array even if wrapped in markdown code fences
        if "```" in text:
            text = text.split("```")[1].removeprefix("json").strip()
        # Find the array in the response
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1:
            return []
        suggestions = json.loads(text[start : end + 1])
        if isinstance(suggestions, list):
            return [s for s in suggestions if isinstance(s, str)][:3]
        return []
    except Exception:
        logger.warning("Follow-up generation failed", exc_info=True)
        return []
