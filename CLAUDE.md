# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Start everything (Postgres + backend + frontend)
./scripts/dev.sh

# Backend only
uv run uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload

# Frontend only
cd frontend && bun run dev

# Frontend type check
cd frontend && npx svelte-check --tsconfig ./tsconfig.json

# Install dependencies
uv sync                    # Python
cd frontend && bun install # JS

# Database (Docker, port 5433)
docker exec -i claude-chat-postgres psql -U claude_chat -d claude_chat < schema.sql
```

## Tooling

- **Python**: uv (not pip/poetry). Type checking: pyrefly (not mypy/pyright).
- **JS/TS**: bun (not npm/yarn/pnpm).
- **Svelte**: v5 with runes mode forced. Avoid `$effect` unless it's a genuine DOM side effect (e.g., scrolling, focus). Use `$derived` or `$derived.by` for computed state.

## Architecture

Two-process app: FastAPI backend (:8000) + SvelteKit frontend (:5173).

### Data flow

1. Frontend creates conversation via REST (`POST /api/conversations`) → stored in Postgres
2. Frontend opens WebSocket (`/api/ws/{conversation_id}`) for real-time chat
3. On first user message, backend lazily creates a `ClaudeSDKClient` (spawns Claude CLI subprocess)
4. SDK messages stream through: `AssistantMessage` → translated to WS JSON → sent to frontend + accumulated in `TurnAccumulator`
5. On `ResultMessage`, the accumulated turn is persisted to Postgres as a single JSONB message

### Backend (`backend/`)

**Domain layer** (no SDK/framework imports):
- `models.py`: Pure domain models (`User`, `Conversation`, `Message`), SDK domain events (`ThinkingEvent`, `ToolUseEvent`, etc.), WS protocol events, and `AssistantTurn` accumulator.
- `ports.py`: Abstract `Protocol` interfaces (`UserRepository`, `ConversationRepository`, `MessageRepository`, `SDKClient`, `SDKClientFactory`) — domain depends on these, concrete implementations live in infrastructure.
- `chat.py`: `ChatSession` orchestrator — manages SDK interaction, user message persistence, event streaming, and conversation auto-titling without importing the SDK directly.

**Infrastructure layer**:
- `app.py`: FastAPI app, CORS, lifespan (asyncpg pool init/teardown), dependency wiring.
- `config.py`: Environment config (`DATABASE_URL`, CORS origins, `AGENT_CWD`).
- `db.py`: Raw asyncpg queries — no ORM. Implements repository ports.
- `sdk_manager.py`: Singleton managing `ClaudeSDKClient` instances keyed by `sdk_session_id`.
- `message_translator.py`: Converts SDK types into domain events.
- `serializers.py`: Domain model → JSON dict serialization for HTTP responses.
- `routers/ws.py`: WebSocket handler — bridges SDK streaming to frontend.
- `routers/conversations.py`: REST CRUD for conversations/messages.

### Frontend (`frontend/src/`)

- `routes/+page.svelte`: Orchestrates state — conversations, messages, WebSocket lifecycle, live turn accumulation.
- `components/`: `ChatView`, `Login`, `MessageInput`, `Sidebar`, `ThinkingBlock`, `ToolCall`, `TurnBubble`.
- `lib/ws.ts`: WebSocket client factory. One connection per conversation.
- `lib/api.ts`: REST client for conversation CRUD.
- `lib/types.ts`: Shared TypeScript types for messages, WS protocol, content structures.

### 3-Level Message Hierarchy

Assistant turns render at three levels of detail:
- **Level 1** (always visible): Final text response
- **Level 2** (collapsed toggle): Tool call names + status badges
- **Level 3** (per-tool expand): Full input JSON + output text

### WebSocket Protocol

Client → Server: `{type: "user_message", content}` or `{type: "interrupt"}`

Server → Client: `thinking`, `tool_use`, `tool_input`, `tool_result`, `assistant_text`, `result`, `error`

### Testing

```bash
# Backend tests (pytest)
uv run pytest backend/tests/

# Frontend unit tests (vitest)
cd frontend && bun run test

# Frontend e2e tests (Playwright)
cd frontend && bunx playwright test
```

- **Backend tests** (`backend/tests/`): Unit tests for models, serializers, message translator, chat session, SDK adapter; integration tests for DB and WebSocket.
- **Frontend unit tests** (`frontend/tests/`): Component tests for Login, MessageInput, Sidebar, ThinkingBlock, ToolCall, TurnBubble.
- **Frontend e2e tests** (`frontend/e2e/`): Playwright specs for conversation flows.
- Test fakes/stubs live in `backend/tests/fakes.py` — implement the ports interfaces for isolation.

### Database

PostgreSQL on port 5433 (Docker). Schema in `schema.sql`. Auth-ready with `user_id` on conversations (defaults to anonymous UUID). Messages store content as JSONB — user messages as `{text}`, assistant messages as `{thinking[], tool_calls[], text, model, usage, duration_ms, total_cost_usd}`.

### Workflow
- All development happens on the `dev` branch. Create feature branches off `dev` and merge back to `dev`. Don't modify files directly on `dev`.
- Always use a merge commit when merging
- Convention: branch names map to issues by title. Branch `feat/my-feature` matches an issue whose title contains "my-feature". A hook validates that a matching open issue exists before allowing branch creation.
- When creating issues, include a `## Screenshots` section in the issue body with markdown checkboxes (e.g., `- [ ] sidebar`). Screenshots must be saved to `screenshots/<branch>/`. The merge hook verifies they exist. Use 'None required' only for pure backend/refactor changes with no user-visible effect. Behavioral fixes still need a screenshot showing the corrected behavior.

#### Per-Issue Checklist

1. Create a GitHub issue (with `## Screenshots` section in the body)
2. Create a branch (hook validates a matching open issue exists)
3. Implement
4. Run unit tests and fix failures
5. If the issue requires screenshots, take them with the `agent-browser` CLI. It is **very important** that you read them to verify they capture working functionality
6. If necessary, create tests. This will include a regression test for fixes, and a E2E test for new features.  
7. Merge to `dev` with a descriptive merge commit (hooks run E2E tests; fix any regressions)
