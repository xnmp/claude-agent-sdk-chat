#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Check if Postgres container is running
if ! docker ps --format '{{.Names}}' | grep -q claude-chat-postgres; then
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
fi

# Start backend
echo "Starting backend on :8000..."
cd "$ROOT"
uv run uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# Start frontend
echo "Starting frontend on :5173..."
cd "$ROOT/frontend"
bun run dev &
FRONTEND_PID=$!

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT

echo ""
echo "Backend:  http://localhost:8000"
echo "Frontend: http://localhost:5173"
echo ""

wait
