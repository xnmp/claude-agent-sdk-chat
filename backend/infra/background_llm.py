"""Background LLM tasks — title generation and follow-up suggestions.

Uses the Anthropic API directly (not the Agent SDK) with a small/fast model.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from anthropic import AsyncAnthropic
from anthropic.types import TextBlock

from ..config import ANTHROPIC_API_KEY, ANTHROPIC_BASE_URL, ANTHROPIC_SMALL_FAST_MODEL

logger = logging.getLogger(__name__)


def _get_client() -> AsyncAnthropic | None:
    if not ANTHROPIC_API_KEY:
        return None
    kwargs: dict[str, Any] = {"api_key": ANTHROPIC_API_KEY}
    if ANTHROPIC_BASE_URL and ANTHROPIC_BASE_URL.startswith("http"):
        kwargs["base_url"] = ANTHROPIC_BASE_URL
    else:
        # Prevent the SDK from picking up an empty ANTHROPIC_BASE_URL from env
        kwargs["base_url"] = "https://api.anthropic.com"
    return AsyncAnthropic(**kwargs)


async def generate_title(user_message: str, assistant_response: str) -> str | None:
    """Generate a short conversation title from the first exchange."""
    client = _get_client()
    if not client:
        return None

    try:
        response = await client.messages.create(
            model=ANTHROPIC_SMALL_FAST_MODEL,
            max_tokens=50,
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
    client = _get_client()
    if not client:
        return []

    try:
        response = await client.messages.create(
            model=ANTHROPIC_SMALL_FAST_MODEL,
            max_tokens=200,
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
