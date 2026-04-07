import os
from dotenv import load_dotenv

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

_REQUIRED_VARS = {
    "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
}


def validate_config() -> None:
    """Raise RuntimeError if any required config values are missing.

    Call during app startup (lifespan), not at import time, so that
    test modules can import individual config values without needing
    every env var set.
    """
    missing = [name for name, value in _REQUIRED_VARS.items() if not value]
    if missing:
        raise RuntimeError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Add them to .env or export them before starting the server."
        )
