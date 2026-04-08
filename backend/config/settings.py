import logging
import os
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

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

# Optional base URL override (e.g. for proxies or custom endpoints)
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "")

# Model to use for the agent. Passed as --model to the CLI.
# Defaults to claude-sonnet-4-5-20250514 (the CLI default when omitted).
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "")

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
