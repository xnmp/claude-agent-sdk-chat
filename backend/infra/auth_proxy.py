"""Credential-injecting auth proxy for the Claude agent subprocess.

Runs a lightweight HTTP reverse proxy on localhost that:
1. Accepts requests from the agent (which has no API key)
2. Injects the real x-api-key header
3. Forwards to the upstream Anthropic API
4. Streams SSE responses back transparently

The agent subprocess gets ANTHROPIC_BASE_URL pointed here,
so it never sees or needs the real API key.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

logger = logging.getLogger(__name__)

_ALLOWED_PATH_PREFIXES = ("/v1/",)

_HEADER_DENYLIST_ALWAYS = frozenset({
    "host",
    "transfer-encoding",
})

_HEADER_DENYLIST_AUTH = frozenset({
    "x-api-key",
    "authorization",
})

_server: uvicorn.Server | None = None
_server_task: asyncio.Task[None] | None = None


_client: httpx.AsyncClient | None = None


def _build_app(api_key: str, auth_token: str, upstream_url: str) -> Starlette:
    """Build the proxy Starlette app with the given credentials."""

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        global _client
        _client = httpx.AsyncClient(
            base_url=upstream_url,
            timeout=httpx.Timeout(connect=10, read=300, write=30, pool=10),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
        yield
        await _client.aclose()
        _client = None

    async def proxy_handler(request: Request) -> Response:
        if not any(request.url.path.startswith(p) for p in _ALLOWED_PATH_PREFIXES):
            return JSONResponse(
                {"error": f"Path {request.url.path} not allowed"},
                status_code=403,
            )

        if _client is None:
            return JSONResponse(
                {"error": "Proxy not initialized"},
                status_code=503,
            )

        body = await request.body()

        has_creds = bool(api_key or auth_token)
        denylist = _HEADER_DENYLIST_ALWAYS | (_HEADER_DENYLIST_AUTH if has_creds else frozenset())
        headers = {
            k: v for k, v in request.headers.items()
            if k.lower() not in denylist
        }
        if api_key:
            headers["x-api-key"] = api_key
        elif auth_token:
            headers["authorization"] = f"Bearer {auth_token}"

        upstream_req = _client.build_request(
            method=request.method,
            url=request.url.path,
            headers=headers,
            content=body,
            params=request.query_params,
        )

        upstream_resp = await _client.send(upstream_req, stream=True)

        async def stream_body() -> AsyncIterator[bytes]:
            try:
                async for chunk in upstream_resp.aiter_raw():
                    yield chunk
            except httpx.RemoteProtocolError as exc:
                logger.warning(
                    "auth proxy: upstream closed connection mid-stream (%s %s): %s",
                    request.method, request.url.path, exc,
                )
            finally:
                await upstream_resp.aclose()

        return StreamingResponse(
            stream_body(),
            status_code=upstream_resp.status_code,
            headers=dict(upstream_resp.headers),
        )

    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    return Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Route("/{path:path}", proxy_handler, methods=["POST", "GET", "PUT", "DELETE"]),
        ],
        lifespan=lifespan,
    )


async def start_proxy(port: int, api_key: str, auth_token: str, upstream_url: str) -> None:
    """Start the auth proxy server as a background asyncio task."""
    global _server, _server_task

    app = _build_app(api_key, auth_token, upstream_url)

    config = uvicorn.Config(
        app=app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )
    _server = uvicorn.Server(config)

    _server_task = asyncio.create_task(_server.serve())

    # Wait for server to be ready
    for _ in range(50):
        if _server.started:
            break
        await asyncio.sleep(0.1)
    else:
        raise RuntimeError(f"Auth proxy failed to start on port {port}")

    logger.info("Auth proxy listening on 127.0.0.1:%d → %s", port, upstream_url)


async def stop_proxy() -> None:
    """Gracefully shut down the proxy server."""
    global _server, _server_task

    if _server is not None:
        _server.should_exit = True

    if _server_task is not None:
        try:
            await asyncio.wait_for(_server_task, timeout=5.0)
        except asyncio.TimeoutError:
            _server_task.cancel()

    _server = None
    _server_task = None
    logger.info("Auth proxy stopped")
