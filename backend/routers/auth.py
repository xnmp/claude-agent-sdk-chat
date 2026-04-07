from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from .. import db

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    display_name: str | None = None


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: str | None


@router.post("/login", response_model=UserResponse)
async def login(req: LoginRequest) -> UserResponse:
    """Look up user by email; create if not found."""
    user = await db.get_user_by_email(req.email)
    if user is None:
        user = await db.create_user(req.email, req.display_name or req.email.split("@")[0])
    return UserResponse(
        id=str(user["id"]),
        email=user["email"],
        display_name=user["display_name"],
    )
