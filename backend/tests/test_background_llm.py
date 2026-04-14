"""Integration tests for background LLM tasks.

These tests make real API calls — they are skipped when no credentials
are available (neither ANTHROPIC_API_KEY nor Claude Code OAuth).
"""

from __future__ import annotations

import pytest

from backend.config import ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN
from backend.infra.background_llm import generate_follow_ups, generate_title
from backend.infra.claude_credentials import load_oauth_credentials


def _has_credentials() -> bool:
    if ANTHROPIC_API_KEY and ANTHROPIC_API_KEY.startswith("sk-ant-api"):
        return True
    if ANTHROPIC_AUTH_TOKEN:
        return True
    return load_oauth_credentials() is not None


_skip_no_creds = pytest.mark.skipif(
    not _has_credentials(), reason="no Anthropic credentials available"
)


@pytest.mark.integration
@_skip_no_creds
class TestGenerateTitleIntegration:
    async def test_returns_a_non_empty_string(self) -> None:
        result = await generate_title(
            user_message="What is the difference between a list and a tuple in Python?",
            assistant_response="Lists are mutable sequences; tuples are immutable.",
        )
        assert isinstance(result, str)
        assert result.strip() != ""

    async def test_title_is_short(self) -> None:
        result = await generate_title(
            user_message="How do I reverse a string in Python?",
            assistant_response='Use slicing: `s[::-1]`.',
        )
        assert result is not None
        # Prompt asks for max 6 words; storage cap is 80 chars
        assert len(result) <= 80

    async def test_title_is_relevant_to_content(self) -> None:
        result = await generate_title(
            user_message="Explain how async/await works in Python",
            assistant_response=(
                "async/await is built on coroutines. An async function returns a "
                "coroutine object. await suspends the current coroutine and yields "
                "control to the event loop until the awaited coroutine completes."
            ),
        )
        assert result is not None
        # Should mention Python or async in some form
        assert any(kw in result.lower() for kw in ("async", "python", "await", "coroutine"))


@pytest.mark.integration
@_skip_no_creds
class TestGenerateFollowUpsIntegration:
    async def test_returns_a_non_empty_list(self) -> None:
        result = await generate_follow_ups(
            user_message="What is a Python decorator?",
            assistant_response=(
                "A decorator is a function that wraps another function to modify "
                "its behaviour without changing its source code."
            ),
        )
        assert isinstance(result, list)
        assert len(result) > 0

    async def test_each_suggestion_is_a_non_empty_string(self) -> None:
        result = await generate_follow_ups(
            user_message="What is a Python decorator?",
            assistant_response="A decorator wraps a function to modify its behaviour.",
        )
        for suggestion in result:
            assert isinstance(suggestion, str)
            assert suggestion.strip() != ""

    async def test_returns_at_most_three_suggestions(self) -> None:
        result = await generate_follow_ups(
            user_message="Explain list comprehensions",
            assistant_response="List comprehensions provide a concise way to create lists.",
        )
        assert len(result) <= 3
