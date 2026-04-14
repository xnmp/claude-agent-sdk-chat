"""FastAPI application — wires concrete implementations to port interfaces."""

import os
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_AUTH_TOKEN,
    ANTHROPIC_BASE_URL,
    AUTH_PROXY_ENABLED,
    AUTH_PROXY_PORT,
    CORS_ORIGINS,
    validate_config,
)
from .infra.auth_proxy import start_proxy, stop_proxy
from .infra.db import (
    PgConversationRepository,
    PgMessageRepository,
    PgUserRepository,
    close_pool,
    init_pool,
)
from .domain.ports import AppState
from .routers import auth, conversations, uploads, ws
from .infra.sdk_manager import SDKManager


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    validate_config()

    if AUTH_PROXY_ENABLED:
        upstream = ANTHROPIC_BASE_URL or "https://api.anthropic.com"
        await start_proxy(AUTH_PROXY_PORT, ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, upstream)

    pool = await init_pool()

    app.state.deps = AppState(
        users=PgUserRepository(pool),
        conversations=PgConversationRepository(pool),
        messages=PgMessageRepository(pool),
        sdk_factory=SDKManager(),
    )

    yield
    await close_pool()
    if AUTH_PROXY_ENABLED:
        await stop_proxy()


app = FastAPI(title="Claude Agent SDK Chat", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(conversations.router)
app.include_router(uploads.router)
app.include_router(ws.router)

# Serve output files for download
_output_dir = os.path.join(os.environ.get("AGENT_CWD", os.getcwd()), "output")
os.makedirs(_output_dir, exist_ok=True)
app.mount("/api/output", StaticFiles(directory=_output_dir), name="output")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
