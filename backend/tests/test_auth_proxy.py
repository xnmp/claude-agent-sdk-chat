"""Unit tests for the auth proxy and env scrubbing."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from backend.infra.auth_proxy import _build_app, start_proxy, stop_proxy
from backend.infra.sdk_manager import _build_agent_env, _SECRET_VARS


# ---------------------------------------------------------------------------
# Env scrubbing tests
# ---------------------------------------------------------------------------


class TestBuildAgentEnv:
    def test_scrubs_api_key(self, monkeypatch):
        monkeypatch.setattr("backend.infra.sdk_manager.ANTHROPIC_API_KEY", "sk-real-secret")
        env = _build_agent_env()
        assert env["ANTHROPIC_API_KEY"] == "proxy-managed"

    def test_does_not_override_api_key_when_unconfigured(self, monkeypatch):
        monkeypatch.setattr("backend.infra.sdk_manager.ANTHROPIC_API_KEY", "")
        env = _build_agent_env()
        assert "ANTHROPIC_API_KEY" not in env

    def test_scrubs_database_url(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host/db")
        env = _build_agent_env()
        assert env["DATABASE_URL"] == ""

    def test_scrubs_all_non_api_secret_vars(self, monkeypatch):
        for var in _SECRET_VARS:
            monkeypatch.setenv(var, "secret-value")
        env = _build_agent_env()
        for var in _SECRET_VARS - {"ANTHROPIC_API_KEY"}:
            assert env[var] == "", f"{var} should be scrubbed"

    def test_sets_proxy_base_url(self):
        env = _build_agent_env()
        assert env["ANTHROPIC_BASE_URL"].startswith("http://127.0.0.1:")

    def test_returns_empty_when_disabled(self, monkeypatch):
        monkeypatch.setattr("backend.infra.sdk_manager.AUTH_PROXY_ENABLED", False)
        env = _build_agent_env()
        assert env == {}


# ---------------------------------------------------------------------------
# Proxy app tests (using httpx test client)
# ---------------------------------------------------------------------------


FAKE_API_KEY = "sk-test-real-key-12345"
UPSTREAM_URL = "https://api.anthropic.com"


@pytest.fixture
def proxy_app():
    return _build_app(FAKE_API_KEY, UPSTREAM_URL)


class TestProxyRouting:
    async def test_health_endpoint(self, proxy_app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=proxy_app),
            base_url="http://testserver",
        ) as client:
            resp = await client.get("/health")
            assert resp.status_code == 200
            assert resp.json() == {"status": "ok"}

    async def test_blocks_non_v1_paths(self, proxy_app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=proxy_app),
            base_url="http://testserver",
        ) as client:
            resp = await client.get("/admin/settings")
            assert resp.status_code == 403

    async def test_blocks_non_api_endpoints(self, proxy_app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=proxy_app),
            base_url="http://testserver",
        ) as client:
            resp = await client.post("/oauth/token", content=b"{}")
            assert resp.status_code == 403

    async def test_blocks_root_path(self, proxy_app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=proxy_app),
            base_url="http://testserver",
        ) as client:
            resp = await client.get("/")
            assert resp.status_code == 403


class TestProxyHeaderInjection:
    """Test that the proxy correctly injects/strips API key headers.

    Uses a mock upstream that echoes back the received headers.
    """

    @pytest.fixture
    def echo_app(self):
        """A tiny ASGI app that echoes request headers and body back."""
        from starlette.applications import Starlette
        from starlette.requests import Request
        from starlette.responses import JSONResponse
        from starlette.routing import Route

        async def echo(request: Request) -> JSONResponse:
            body = await request.body()
            return JSONResponse({
                "headers": dict(request.headers),
                "body": body.decode(),
                "path": request.url.path,
            })

        return Starlette(routes=[
            Route("/{path:path}", echo, methods=["POST", "GET"]),
        ])

    @pytest.fixture
    def proxy_with_echo(self, echo_app):
        """Proxy app pointing to the echo upstream via httpx ASGITransport."""
        from backend.infra.auth_proxy import _ALLOWED_PATH_PREFIXES, _HEADER_DENYLIST_ALWAYS, _HEADER_DENYLIST_AUTH

        from starlette.applications import Starlette
        from starlette.requests import Request
        from starlette.responses import JSONResponse, StreamingResponse
        from starlette.routing import Route

        api_key = FAKE_API_KEY

        # Create the upstream client directly (no lifespan needed for tests)
        upstream_client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=echo_app),
            base_url="http://upstream",
        )

        async def proxy_handler(request: Request) -> JSONResponse | StreamingResponse:
            if not any(request.url.path.startswith(p) for p in _ALLOWED_PATH_PREFIXES):
                return JSONResponse({"error": "blocked"}, status_code=403)

            body = await request.body()
            denylist = _HEADER_DENYLIST_ALWAYS | _HEADER_DENYLIST_AUTH
            headers = {
                k: v for k, v in request.headers.items()
                if k.lower() not in denylist
            }
            headers["x-api-key"] = api_key

            upstream_req = upstream_client.build_request(
                method=request.method,
                url=request.url.path,
                headers=headers,
                content=body,
            )
            upstream_resp = await upstream_client.send(upstream_req, stream=True)
            content = await upstream_resp.aread()
            return JSONResponse(
                json.loads(content),
                status_code=upstream_resp.status_code,
            )

        return Starlette(
            routes=[
                Route("/health", lambda r: JSONResponse({"status": "ok"}), methods=["GET"]),
                Route("/{path:path}", proxy_handler, methods=["POST", "GET"]),
            ],
        )

    async def test_injects_api_key(self, proxy_with_echo):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=proxy_with_echo),
            base_url="http://testserver",
        ) as client:
            resp = await client.post(
                "/v1/messages",
                content=b'{"model": "test"}',
                headers={"content-type": "application/json"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["headers"]["x-api-key"] == FAKE_API_KEY

    async def test_strips_incoming_api_key(self, proxy_with_echo):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=proxy_with_echo),
            base_url="http://testserver",
        ) as client:
            resp = await client.post(
                "/v1/messages",
                content=b'{"model": "test"}',
                headers={
                    "content-type": "application/json",
                    "x-api-key": "sk-attacker-spoofed-key",
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            # Should have the real key, not the spoofed one
            assert data["headers"]["x-api-key"] == FAKE_API_KEY

    async def test_strips_authorization_header(self, proxy_with_echo):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=proxy_with_echo),
            base_url="http://testserver",
        ) as client:
            resp = await client.post(
                "/v1/messages",
                content=b'{"model": "test"}',
                headers={
                    "content-type": "application/json",
                    "authorization": "Bearer sk-spoofed",
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "authorization" not in data["headers"]

    async def test_forwards_body(self, proxy_with_echo):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=proxy_with_echo),
            base_url="http://testserver",
        ) as client:
            body = '{"model": "claude-sonnet-4-5-20250514", "messages": []}'
            resp = await client.post(
                "/v1/messages",
                content=body.encode(),
                headers={"content-type": "application/json"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["body"] == body
