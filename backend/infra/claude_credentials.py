"""Load OAuth credentials from Claude Code's local credential store.

Used as a fallback when no ANTHROPIC_API_KEY is configured, so background
LLM tasks can reuse the same Max subscription credentials that the Claude
Code CLI uses.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OAuthCredentials:
    access_token: str
    expires_at_ms: int


def _credentials_path() -> Path | None:
    base = Path.home() / ".claude"
    for name in (".credentials.json", "credentials.json"):
        path = base / name
        if path.exists():
            return path
    return None


def load_oauth_credentials() -> OAuthCredentials | None:
    """Read the Claude Code OAuth access token if present and unexpired."""
    path = _credentials_path()
    if path is None:
        return None

    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None

    oauth = data.get("claudeAiOauth") or {}
    token = oauth.get("accessToken")
    if not isinstance(token, str) or not token:
        return None

    expires_at = oauth.get("expiresAt")
    if not isinstance(expires_at, int):
        expires_at = 0

    if expires_at and expires_at < int(time.time() * 1000):
        return None

    return OAuthCredentials(access_token=token, expires_at_ms=expires_at)
