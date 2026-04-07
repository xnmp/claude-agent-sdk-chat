"""Unit tests for auth domain logic — find_or_create_user with fake repo."""

from __future__ import annotations

from backend.routers.auth import find_or_create_user
from backend.tests.fakes import FakeUserRepository


class TestFindOrCreateUser:
    async def test_returns_existing_user_without_overwriting(self, user_repo: FakeUserRepository):
        """Idempotency: calling twice with different display_name keeps the original."""
        original = await find_or_create_user(user_repo, "bob@example.com", "Bob")
        found = await find_or_create_user(user_repo, "bob@example.com", "Different Name")

        assert found.id == original.id
        assert found.display_name == "Bob"

    async def test_falls_back_to_email_prefix_when_no_display_name(self, user_repo: FakeUserRepository):
        user = await find_or_create_user(user_repo, "charlie@company.org", None)
        assert user.display_name == "charlie"

        user2 = await find_or_create_user(user_repo, "dave@example.com", "")
        assert user2.display_name == "dave"

    async def test_handles_email_without_at_sign(self, user_repo: FakeUserRepository):
        """Edge case: email.split('@')[0] on a local-only address."""
        user = await find_or_create_user(user_repo, "localuser", None)
        assert user.display_name == "localuser"
