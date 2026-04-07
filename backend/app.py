"""FastAPI application — wires concrete implementations to port interfaces."""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import CORS_ORIGINS
from .db import (
    PgConversationRepository,
    PgMessageRepository,
    PgUserRepository,
    close_pool,
    init_pool,
)
from .ports import AppState
from .routers import auth, conversations, ws
from .sdk_manager import SDKManager


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    pool = await init_pool()

    app.state.deps = AppState(
        users=PgUserRepository(pool),
        conversations=PgConversationRepository(pool),
        messages=PgMessageRepository(pool),
        sdk_factory=SDKManager(),
    )

    yield
    await close_pool()


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
app.include_router(ws.router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
