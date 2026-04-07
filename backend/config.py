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
