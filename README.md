# LLM Chat Web App

Multi-user LLM chat web application — apiflask (backend) + Vue 3 (frontend) +
PostgreSQL + Groq, one-command up with Docker Compose.

> Build follows [PLAN.md](PLAN.md). This README grows each phase; current state:
> **Day 6 — super-admin export + separated Vue 3 frontend** (login, streaming
> chat, admin pages) on top of the Day 5 real Groq SSE streaming.

## Quick start

```bash
# 1. Create your env file from the template and fill in secrets.
cp .env.example .env
# Generate a strong JWT secret:
python -c "import secrets; print(secrets.token_urlsafe(48))"
# Set JWT_SECRET, POSTGRES_PASSWORD, SUPER_ADMIN_USERNAME/PASSWORD in .env.

# 2. Bring up the stack (Postgres + API). Migrations run automatically.
docker compose up --build
```

Then open:

- API docs (OpenAPI / Swagger UI): http://localhost:8000/docs
- Liveness:  http://localhost:8000/health
- Readiness (checks DB + LLM upstream): http://localhost:8000/health/ready

## Project layout

```
backend/                 apiflask service (Clean Architecture, PLAN §3.1)
  app/
    domain/              pure business: Role, RBAC matrix, message roles
    application/         use-case / service layer (added Day 2+)
    infrastructure/      config, db (SQLAlchemy + Alembic), security, llm
    interface/           apiflask blueprints + schemas
  alembic/               migrations
  Dockerfile            multi-stage, non-root runtime
docker-compose.yml       db + api + frontend, one-command up
.env.example             complete environment template (no secrets committed)

../vue_llm/              Vue 3 + Vite SPA (separated frontend, PLAN Day 6)
  src/api/               fetch client, SSE stream parser, typed endpoints
  src/stores/            Pinia: auth + chat (streaming state)
  src/views/             Login / Chat / Admin / Account
  Dockerfile, nginx.conf serve built SPA + reverse-proxy the API
```

## Tech choices & rationale

See [PLAN.md §2](PLAN.md). Summary:

- **PostgreSQL** — production-grade, mature SQLAlchemy + Alembic ecosystem,
  native JSONB; the extra service is covered by compose so one-command-up holds.
- **Groq** — free tier, OpenAI-compatible API, native SSE streaming. Wrapped
  behind an `LLMProvider` port so the provider can be swapped via config.
- **JWT HS256** — single issuer / single service; HS256 + env secret is the
  simplest sufficient choice (RS256 would be over-engineering here).
- **Argon2id** — modern, memory-hard password hashing.
- **Gunicorn + gevent worker** — SSE streams are long-lived I/O waits;
  gevent keeps workers from being tied up per stream.

## Authentication

- **Default admin (seed):** on first startup an idempotent seed creates the
  `super_admin` from `SUPER_ADMIN_USERNAME` / `SUPER_ADMIN_PASSWORD`. If either
  is missing the app **fails fast** rather than booting with no administrator
  (invariant I-1). Re-running is a no-op (never rebuilds/overwrites).
- **Login:** `POST /auth/login` with `{username, password}` returns a JWT
  access token. Send it as `Authorization: Bearer <token>` on protected routes.
- **Logout:** `POST /auth/logout` — JWT is stateless, so logout is client-side
  token disposal; the endpoint exists for symmetry and audit logging.
- **Change own password:** `POST /auth/change-password`.
- **Passwords** are hashed with Argon2id, never stored in plaintext.

Quick demo (after `docker compose up`):

```bash
TOKEN=$(curl -s -X POST localhost:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"superadmin","password":"<your SUPER_ADMIN_PASSWORD>"}' \
  | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
curl -s localhost:8000/auth/me -H "Authorization: Bearer $TOKEN"
```

## Authorization (RBAC)

Three roles — `user` / `admin` / `super_admin` — driven by a single permission
matrix in [domain/user.py](backend/app/domain/user.py). Views carry a
`@require_permission(...)` gate; fine-grained, target-dependent rules live in the
service layer (so business rules return 4xx, not 500).

Admin / Super Admin API:

| Method & path | Permission | admin | super_admin |
|---|---|:---:|:---:|
| `GET  /admin/users` | list users | ✓ | ✓ |
| `POST /admin/users` (role=user) | create user | ✓ | ✓ |
| `POST /admin/users` (role=admin) | create admin | ✗ | ✓ |
| `PATCH /admin/users/{id}/active` (user) | toggle user | ✓ | ✓ |
| `PATCH /admin/users/{id}/active` (admin) | toggle admin | ✗ | ✓ |
| `POST /admin/users/{id}/promote` | promote user→admin | ✗ | ✓ |
| `GET  /admin/export` | export all conversations (JSON) | ✗ | ✓ |

**Invariant I-2 — always ≥ 1 active super_admin:** guaranteed structurally.
No API path creates, deactivates, or demotes a super_admin (they exist only via
the seed), so the system can never reach a "no super admin" state. Any operation
targeting a super_admin is rejected (403).

## Chat

Each user has multiple chat sessions (ChatGPT-style). Sessions and messages are
persisted; history loads in chronological order. Authorization here is **per-user
ownership** — a session belonging to another user returns `404` (not `403`) so
the API never reveals which session ids exist.

| Method & path | Description |
|---|---|
| `POST   /chat/sessions` | create a session (optional `title`) |
| `GET    /chat/sessions` | list own sessions, most-recently-active first |
| `GET    /chat/sessions/{id}` | load a session with its full message history |
| `DELETE /chat/sessions/{id}` | delete own session (cascades to messages) |
| `POST   /chat/sessions/{id}/messages` | send a message; persists the user turn, gets the assistant reply, persists it, returns both (non-streaming) |
| `POST   /chat/sessions/{id}/messages/stream` | same, but streams the assistant reply token-by-token over SSE |

- **LLM provider** is abstracted behind an `LLMProvider` port with two
  implementations: a deterministic offline **mock** (`LLM_PROVIDER=mock`, works
  with no API key) and the real **Groq** adapter (`LLM_PROVIDER=groq` +
  `GROQ_API_KEY`), an OpenAI-compatible client so swapping providers is config,
  not code. `LLM_PROVIDER=groq` with no key **fails fast**.
- **Streaming (SSE).** The stream endpoint persists the user turn and commits it
  *before* opening the response (so ownership/validation errors are real
  `404`/`422`, and the user turn survives a dropped client), then emits
  `text/event-stream` events: a `meta` frame (persisted user message + session
  title), repeated `token` frames (content deltas), and a terminal `done`
  (persisted assistant message) or `error`. On an upstream failure mid-stream the
  partial reply received so far is still persisted, so a user turn never dangles
  without an answer (PLAN §3.5). Pass the JWT as a Bearer header. The served
  reply concatenates the deltas to exactly what the non-streaming path returns.
- **First message** auto-names an untitled session (truncated); the title is not
  overwritten afterwards.
- **Ordering** does not trust the wall clock (Postgres `now()` is
  transaction-time, and OS clocks can be coarse): each message is stamped
  strictly after the last in its session, so history is deterministic without an
  extra sequence column.

```bash
SID=$(curl -s -X POST localhost:8000/chat/sessions \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{}' | python -c "import sys,json;print(json.load(sys.stdin)['id'])")
curl -s -X POST localhost:8000/chat/sessions/$SID/messages \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"content":"Hello!"}'

# Streaming variant — -N disables curl's buffering so tokens print as they arrive:
curl -N -X POST localhost:8000/chat/sessions/$SID/messages/stream \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"content":"Tell me a short joke."}'
```

## Export (super_admin)

`GET /admin/export` returns a complete JSON snapshot of every user with their
chat sessions and messages — for archival / migration. super_admin only (others
get `403`). Sessions are loaded with `selectinload` so the export is one batched
query for all messages, not one per session (off the N+1 path, PLAN §3.2).

```bash
curl -s localhost:8000/admin/export -H "Authorization: Bearer $TOKEN" -o export.json
```

Shape: `{ exported_at, users: [ { id, username, role, sessions: [ { id, title,
created_at, updated_at, messages: [ { role, content, created_at } ] } ] } ] }`.

## Frontend (Vue 3)

A separate Vue 3 + Vite + TypeScript + Pinia SPA lives in the sibling repo
[`../vue_llm`](../vue_llm) (front-end/back-end split): login / logout / change
password, multi-session chat with **token-by-token SSE streaming** and markdown
rendering, and Bonus admin pages (user management + export).

```bash
cd ../vue_llm
npm install
npm run dev          # http://localhost:5173, proxies the API to :8000
```

- **API integration.** In dev the Vite proxy forwards `/auth /chat /admin
  /health` to `:8000`, keeping the browser same-origin (no CORS friction). To
  talk to the API directly instead, set `VITE_API_BASE=http://localhost:8000` —
  the backend then allows that origin via **`CORS_ORIGINS`** (config below).
- **Streaming.** `EventSource` can't send an `Authorization` header, so the SPA
  POSTs with `fetch` and parses the `text/event-stream` body manually
  (`src/api/chat.ts`), consuming the `meta` / `token` / `done` / `error` frames.
- **Auth token.** The JWT is kept in `localStorage` and sent as a Bearer header;
  a `401` clears it and bounces to `/login`. *(Trade-off: simpler than an
  httpOnly cookie but readable by JS, so it relies on the markdown sanitiser to
  contain XSS — see "Known limitations".)*
- **Production / one-command-up.** `docker compose up --build` also builds the
  frontend (`frontend` service): nginx serves the built SPA and reverse-proxies
  the API, so the browser is same-origin and no CORS is needed. Open
  http://localhost:5173.

## Configuration

All secrets and tunables come from environment variables (`.env`); nothing is
hardcoded. See [.env.example](.env.example) for the full list. `.env` is
git-ignored and docker-ignored. **`CORS_ORIGINS`** (comma-separated) lists the
origins allowed to call the API cross-origin; defaults to the Vite dev server
(`http://localhost:5173`). Leave it empty when the SPA is served same-origin
behind the compose nginx.

## Testing

Unit tests use a fake repository (no DB) for services and in-memory SQLite for
seed/repository tests — fast and deterministic.

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

## Status / roadmap

- [x] **Day 1** — foundation: skeleton, config, DB + Alembic migration, `/docs`,
  health checks, Docker Compose one-command-up.
- [x] **Day 2** — auth: Argon2 hashing, JWT (HS256), login/logout/me/change
  password, super_admin idempotent seed with fail-fast, unit tests.
- [x] **Day 3** — RBAC: central permission matrix + `@require_permission`,
  admin/super-admin API (create/list/activate/promote), cross-role guards,
  invariant I-2 (always >=1 active super_admin), full matrix tests.
- [x] **Day 4** — chat persistence: session CRUD, chronological message history,
  per-user ownership (404 on foreign sessions), `LLMProvider` port + mock,
  auto-title on first message; service + repository tests.
- [x] **Day 5** — real Groq SSE streaming: `LLMProvider.stream`, Groq adapter
  (OpenAI-compatible, fail-fast on missing key), SSE endpoint with token frames,
  partial-persist on dropped upstream; gevent worker already configured for the
  long-lived connections. Service, factory, and end-to-end stream tests.
- [x] **Day 6** — super-admin export (`GET /admin/export`, N+1-safe), CORS for
  the separated frontend, and the Vue 3 SPA (`../vue_llm`): login, streaming
  chat with markdown, admin user-management + export pages; compose now builds
  the frontend too. Observability bonuses: structured JSON logging with
  request-id correlation and a DB + LLM readiness probe. Export + observability
  tests added.
- [ ] Day 7 — docs, transcript redaction, demo.

## Observability

- **Structured logging.** Every log line is one JSON object on stdout
  (`infrastructure/logging.py`); one access log per request carries method,
  path, status and duration.
- **Request-id correlation.** Each request gets an id (inbound `X-Request-ID`
  header or a fresh uuid), stamped on every log line and echoed on the response
  `X-Request-ID` header — so logs for one request can be grepped together and
  traced from an upstream proxy.
- **Readiness probe.** `GET /health/ready` verifies the DB connection and the
  LLM upstream (mock is always ok; the Groq adapter does a token-free
  `models.list` ping). The compose healthcheck polls liveness (`/health`) so
  container health never flaps on an external dependency.

## Known limitations / trade-offs

- **JWT in `localStorage`** (frontend): simpler than an httpOnly cookie and fine
  for this single-page bearer-token flow, but readable by JS — assistant content
  is sanitised (DOMPurify) to contain XSS. A cookie + CSRF approach would be the
  hardening step.
- **Export is assembled in one pass** (`selectinload`), not streamed in batches;
  correct and N+1-safe, but for very large datasets a server-side batched/stream
  response would bound memory. Noted in PLAN §3.2.
