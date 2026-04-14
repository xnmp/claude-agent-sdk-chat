import logging
import os
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

# Strip empty ANTHROPIC_* env vars so downstream libraries don't treat
# "" as a "configured" value. docker-compose's `${VAR:-}` fallback sets
# unset host vars to empty strings inside the container; the anthropic
# Python SDK then reads an empty ANTHROPIC_AUTH_TOKEN as a bearer token
# and builds a malformed `Authorization: Bearer ` header, breaking title
# generation and follow-up suggestions when only ANTHROPIC_API_KEY is
# configured. Removing empty keys entirely lets the SDK's os.environ.get
# calls return None, so only real values influence its auth choice.
for _k in (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_MODEL",
    "ANTHROPIC_SMALL_FAST_MODEL",
):
    if os.environ.get(_k) == "":
        del os.environ[_k]

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://claude_chat:claude_chat@localhost:5433/claude_chat",
)

CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")

# Working directory for the SDK agent
AGENT_CWD = os.environ.get("AGENT_CWD", os.getcwd())

# Anthropic API key — required for the Claude Agent SDK.
# Read here so it's available as a config value; validated at startup.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Optional Bearer token for corporate/proxy auth (e.g. AIPE gateway).
# When set, passed as Authorization: Bearer instead of x-api-key.
ANTHROPIC_AUTH_TOKEN = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")

# Optional base URL override (e.g. for proxies or custom endpoints)
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "")

# Auth proxy — intercepts agent API calls to inject credentials,
# so the agent subprocess never sees the real API key.
AUTH_PROXY_ENABLED = os.environ.get("AUTH_PROXY_ENABLED", "true").lower() in ("true", "1", "yes")
AUTH_PROXY_PORT = int(os.environ.get("AUTH_PROXY_PORT", "9100"))

# Model to use for the agent. Passed as --model to the CLI.
# Defaults to claude-sonnet-4-5-20250514 (the CLI default when omitted).
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "")

# Smaller/faster model for background tasks (title generation, follow-up suggestions)
ANTHROPIC_SMALL_FAST_MODEL = os.environ.get("ANTHROPIC_SMALL_FAST_MODEL", "claude-haiku-4-5-20251001")

_WARNED_VARS = {
    "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
}


def validate_config() -> None:
    """Log warnings for missing config values at startup.

    Called during app lifespan, not at import time, so that test modules
    can import individual config values without needing every env var set.
    """
    missing = [name for name, value in _WARNED_VARS.items() if not value]
    if missing:
        logger.warning(
            "Missing environment variable(s): %s. "
            "The server will start, but agent features will not work. "
            "Add them to .env or export them before sending messages.",
            ", ".join(missing),
        )
