"""End-to-end SSE streaming test through the Flask test client.

Exercises the full chat-stream path that the unit tests can't reach: JWT auth,
`open_stream` + commit, `stream_with_context` framing, and assistant persistence
— all against an in-memory SQLite session swapped in for the request-scoped DB.
The LLM is the deterministic mock, so no network is touched.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.domain.user import Role
from app.infrastructure.db.base import Base
from app.infrastructure.db.models import User
from app.infrastructure.security.jwt import create_access_token
from app.infrastructure.security.password import hash_password


@pytest.fixture
def client_and_user(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    session = TestSession()

    # Swap the request-scoped DB for the in-memory session (every repo goes
    # through deps.get_db, so this redirects the whole request). Force the mock
    # LLM so the test is hermetic regardless of the ambient .env provider.
    from app.interface import deps
    from app.infrastructure.llm.mock import MockLLMProvider

    monkeypatch.setattr(deps, "get_db", lambda: session)
    monkeypatch.setattr(deps, "get_llm_provider", lambda _settings: MockLLMProvider())

    user = User(
        id=uuid.uuid4(),
        username="alice",
        password_hash=hash_password("pw"),
        role=Role.USER,
        is_active=True,
    )
    session.add(user)
    session.commit()

    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    token = create_access_token(user.id, user.role)
    return app.test_client(), session, user, token


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_stream_endpoint_emits_meta_tokens_and_done(client_and_user):
    client, session, user, token = client_and_user

    created = client.post("/chat/sessions", json={}, headers=_auth(token))
    session_id = created.get_json()["id"]

    resp = client.post(
        f"/chat/sessions/{session_id}/messages/stream",
        json={"content": "hello"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.mimetype == "text/event-stream"

    body = resp.get_data(as_text=True)
    assert "event: meta" in body
    assert "event: token" in body
    assert "event: done" in body

    # The mock reply for "hello" is persisted as the assistant turn.
    detail = client.get(
        f"/chat/sessions/{session_id}", headers=_auth(token)
    ).get_json()
    roles = [m["role"] for m in detail["messages"]]
    assert roles == ["user", "assistant"]
    assert detail["messages"][1]["content"] == "[mock-llm] You said: hello"


def test_stream_foreign_session_is_404_before_stream_opens(client_and_user):
    client, session, user, token = client_and_user
    # A random session id the user does not own -> 404 as a real HTTP status,
    # not an in-stream error event.
    resp = client.post(
        f"/chat/sessions/{uuid.uuid4()}/messages/stream",
        json={"content": "hi"},
        headers=_auth(token),
    )
    assert resp.status_code == 404
    assert resp.mimetype != "text/event-stream"


def test_stream_requires_auth(client_and_user):
    client, *_ = client_and_user
    resp = client.post(
        f"/chat/sessions/{uuid.uuid4()}/messages/stream",
        json={"content": "hi"},
    )
    assert resp.status_code == 401
