"""Auth endpoints — thin adapter over UserRepository."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..models import User
from ..ports import AppState, UserRepository

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    display_name: str | None = None


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: str | None


# ---------------------------------------------------------------------------
# Domain logic (pure — depends only on the UserRepository protocol)
# ---------------------------------------------------------------------------


async def find_or_create_user(
    repo: UserRepository, email: str, display_name: str | None,
) -> User:
    """Look up user by email; create if not found."""
    user = await repo.get_by_email(email)
    if user is None:
        user = await repo.create(email, display_name or email.split("@")[0])
    return user


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/login", response_model=UserResponse)
async def login(request: Request, req: LoginRequest) -> UserResponse:
    deps: AppState = request.app.state.deps
    user = await find_or_create_user(deps.users, req.email, req.display_name)
    return UserResponse(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
    )
