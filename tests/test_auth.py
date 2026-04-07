"""Unit tests for auth domain logic — find_or_create_user with fake repo."""

from __future__ import annotations

from backend.routers.auth import find_or_create_user
from tests.fakes import FakeUserRepository


class TestFindOrCreateUser:
    async def test_creates_new_user_when_not_found(self, user_repo: FakeUserRepository):
        user = await find_or_create_user(user_repo, "alice@example.com", "Alice")

        assert user.email == "alice@example.com"
        assert user.display_name == "Alice"
        assert user.id is not None

    async def test_returns_existing_user_when_found(self, user_repo: FakeUserRepository):
        original = await find_or_create_user(user_repo, "bob@example.com", "Bob")
        found = await find_or_create_user(user_repo, "bob@example.com", "Different Name")

        assert found.id == original.id
        assert found.display_name == "Bob"  # Original name, not the new one

    async def test_uses_email_prefix_when_display_name_is_none(self, user_repo: FakeUserRepository):
        user = await find_or_create_user(user_repo, "charlie@company.org", None)

        assert user.display_name == "charlie"

    async def test_uses_email_prefix_when_display_name_is_empty(self, user_repo: FakeUserRepository):
        user = await find_or_create_user(user_repo, "dave@example.com", "")

        # Empty string is falsy, so it should fall back to email prefix
        assert user.display_name == "dave"
