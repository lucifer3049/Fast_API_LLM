# LLM Chat Web App

Multi-user LLM chat web application — apiflask (backend) + Vue 3 (frontend) +
PostgreSQL + Groq, one-command up with Docker Compose.

> Build follows [PLAN.md](PLAN.md). This README grows each phase; current state:
> **Day 5 — real Groq SSE streaming** (token-by-token assistant replies, mock
> still available offline).

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
- Readiness (checks DB): http://localhost:8000/health/ready

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
docker-compose.yml       db + api (frontend added later)
.env.example             complete environment template (no secrets committed)
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

## Configuration

All secrets and tunables come from environment variables (`.env`); nothing is
hardcoded. See [.env.example](.env.example) for the full list. `.env` is
git-ignored and docker-ignored.

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
- [ ] Day 6 — export, frontend admin pages, observability bonuses.
- [ ] Day 7 — docs, transcript redaction, demo.
