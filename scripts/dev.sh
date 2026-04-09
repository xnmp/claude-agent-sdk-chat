#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Kill any existing backend/frontend processes
pkill -f 'uvicorn backend' 2>/dev/null || true
pkill -f 'vite.*5173' 2>/dev/null || true
# Free port 8000 if still held
fuser -k 8000/tcp 2>/dev/null || true

# Force remove the container if it exists (running or not)
docker rm -f claude-chat-postgres 2>/dev/null || true

echo "Starting Postgres..."
docker run -d --name claude-chat-postgres \
    -e POSTGRES_USER=claude_chat \
    -e POSTGRES_PASSWORD=claude_chat \
    -e POSTGRES_DB=claude_chat \
    -p 5433:5432 \
    postgres:17-alpine

sleep 2
echo "Running schema..."
docker exec -i claude-chat-postgres psql -U claude_chat -d claude_chat < "$ROOT/schema.sql"

run_backend() {
    trap 'exit 0' INT TERM
    cd "$ROOT"
    while true; do
        uv run uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload --reload-dir backend --reload-include '*.py' || true
        echo "Backend exited, restarting in 1s..." >&2
        sleep 1
    done
}

run_frontend() {
    trap 'exit 0' INT TERM
    cd "$ROOT/frontend"
    while true; do
        bun run dev || true
        echo "Frontend exited, restarting in 1s..." >&2
        sleep 1
    done
}

cleanup() {
    kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
    pkill -f 'uvicorn backend' 2>/dev/null || true
    pkill -f 'vite.*5173' 2>/dev/null || true
}
trap cleanup EXIT

# Start backend
echo "Starting backend on :8000..."
run_backend &
BACKEND_PID=$!

# Start frontend
echo "Starting frontend on :5173..."
run_frontend &
FRONTEND_PID=$!

echo ""
echo "Backend:  http://localhost:8000"
echo "Frontend: http://localhost:5173"
echo ""

wait
