# LLM Chat Web App

Multi-user LLM chat web application — apiflask (backend) + Vue 3 (frontend) +
PostgreSQL + Groq, one-command up with Docker Compose.

> Build follows [PLAN.md](PLAN.md). This README grows each phase; current state:
> **Day 2 — auth + super_admin seed** (JWT login, Argon2, idempotent seed).

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
- [ ] Day 3 — RBAC + admin/super-admin API.
- [ ] Day 4 — chat persistence (mock LLM).
- [ ] Day 5 — real Groq SSE streaming.
- [ ] Day 6 — export, frontend admin pages, observability bonuses.
- [ ] Day 7 — docs, transcript redaction, demo.
