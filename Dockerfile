# syntax=docker/dockerfile:1.7

# ---------- Stage 1: build the SvelteKit frontend ----------
# Node base with nothing else — builds a static SPA bundle into
# /app/frontend/build, which the Python runtime stage copies in.
FROM node:22-slim AS frontend-build

WORKDIR /app/frontend

# Copy manifest first so Docker caches the install layer when only
# source files change.
COPY frontend/package.json ./
# Lockfile committed (bun.lock) is for bun; we deliberately use npm here
# per the image contract. No package-lock.json, so `npm install` (not ci).
RUN npm install --no-audit --no-fund

COPY frontend/ ./
RUN npm run build


# ---------- Stage 2: runtime ----------
# Node base so Claude CLI (npm @anthropic-ai/claude-code) runs without
# a separate JS runtime install. Python is layered on top via apt.
FROM node:22-slim AS runtime

# System deps:
#   - python3 / python3-venv : FastAPI runtime
#   - bubblewrap             : required by Claude CLI's Bash sandbox
#   - curl, ca-certificates  : uv installer + healthcheck
#   - git                    : agents frequently shell out to it
#   - tini                   : proper signal handling for the python process
#     (so SIGTERM from `docker stop` actually reaches uvicorn)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-venv \
        bubblewrap \
        curl \
        ca-certificates \
        git \
        tini \
    && rm -rf /var/lib/apt/lists/*

# Do NOT set bwrap setuid. In Docker, setuid binaries that try to call
# capset fail because the container's ambient capabilities don't include
# the source for the elevated caps. bwrap is designed to also run in
# unprivileged-userns mode, which works inside a container as long as
# the runtime allows `pivot_root` and `mount proc` (see docker-compose).

# Install uv (pinned standalone installer). Avoids pulling pip.
# UV_PYTHON_INSTALL_DIR puts the managed interpreter in a world-readable
# location so the non-root `app` user can traverse and execute it. The
# default (~/.local/share/uv) sits under root's home and is unreadable
# by other users, which breaks `uvicorn` at exec time.
ENV UV_INSTALL_DIR=/usr/local/bin \
    UV_PYTHON_INSTALL_DIR=/opt/uv-python
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && uv --version

# Install Claude CLI globally. The claude-agent-sdk spawns `claude` via
# shutil.which, and the CLI in turn invokes bwrap for its sandbox.
RUN npm install -g --no-audit --no-fund @anthropic-ai/claude-code \
    && claude --version

# Non-root user for the running app. Keeping root for the install steps
# above avoids permission contortions with apt/npm.
RUN groupadd --system --gid 1001 app \
    && useradd  --system --uid 1001 --gid app --home-dir /app --shell /bin/bash app

WORKDIR /app

# Copy Python project files first so `uv sync` is cached when only
# source changes.
COPY --chown=app:app pyproject.toml uv.lock ./

# Install Python deps into a venv at /app/.venv using the frozen lockfile.
# --no-dev excludes test/dev extras.
RUN uv sync --frozen --no-dev \
    && chmod -R a+rX /opt/uv-python \
    && chown -R app:app /app/.venv

# Copy backend source, MCP server source, and schema.
COPY --chown=app:app backend/ ./backend/
COPY --chown=app:app mytools/ ./mytools/
COPY --chown=app:app schema.sql ./schema.sql

# Copy the built frontend from stage 1 into the location backend/app.py
# looks for it at startup.
COPY --from=frontend-build --chown=app:app /app/frontend/build ./frontend/build

# Writable workspace for the agent: outputs, scripts, uploads, docs.
# Created here so the layer has correct ownership; in compose this is
# usually overlaid with a named volume for persistence.
RUN mkdir -p /app/agent-workspace/output \
             /app/agent-workspace/output_scripts \
             /app/agent-workspace/uploads \
             /app/agent-workspace/docs \
    && chown -R app:app /app/agent-workspace

ENV AGENT_CWD=/app/agent-workspace \
    PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
