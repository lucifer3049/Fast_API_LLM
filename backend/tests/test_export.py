"""End-to-end tests for the super-admin export endpoint (GET /admin/export).

Runs through the Flask test client against an in-memory SQLite session swapped
in for the request-scoped DB, mirroring tests/test_chat_api.py. Exercises RBAC
(only super_admin may export), the user → sessions → messages shape, and the
empty-roster / no-conversation edges.
"""
from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.domain.chat import MessageRole
from app.domain.user import Role
from app.infrastructure.db.base import Base
from app.infrastructure.db.models import ChatSession, Message, User
from app.infrastructure.security.jwt import create_access_token
from app.infrastructure.security.password import hash_password


def _make_user(session, username: str, role: Role) -> User:
    user = User(
        id=uuid.uuid4(),
        username=username,
        password_hash=hash_password("pw"),
        role=role,
        is_active=True,
    )
    session.add(user)
    session.commit()
    return user


@pytest.fixture
def export_env(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    session = TestSession()

    from app.interface import deps

    monkeypatch.setattr(deps, "get_db", lambda: session)

    superadmin = _make_user(session, "root", Role.SUPER_ADMIN)
    admin = _make_user(session, "adm", Role.ADMIN)
    user = _make_user(session, "alice", Role.USER)

    # One session with a user+assistant exchange for alice; admin/superadmin have none.
    now = dt.datetime.now(dt.timezone.utc)
    chat = ChatSession(id=uuid.uuid4(), user_id=user.id, title="Greetings", created_at=now, updated_at=now)
    session.add(chat)
    session.add(Message(id=uuid.uuid4(), session_id=chat.id, role=MessageRole.USER, content="hi", created_at=now))
    session.add(
        Message(
            id=uuid.uuid4(),
            session_id=chat.id,
            role=MessageRole.ASSISTANT,
            content="hello there",
            created_at=now + dt.timedelta(microseconds=1),
        )
    )
    session.commit()

    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()
    tokens = {
        "super_admin": create_access_token(superadmin.id, superadmin.role),
        "admin": create_access_token(admin.id, admin.role),
        "user": create_access_token(user.id, user.role),
    }
    return client, tokens


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_super_admin_export_returns_full_snapshot(export_env):
    client, tokens = export_env
    resp = client.get("/admin/export", headers=_auth(tokens["super_admin"]))
    assert resp.status_code == 200

    payload = resp.get_json()
    assert "exported_at" in payload
    users = {u["username"]: u for u in payload["users"]}
    # All three accounts appear, even those with no conversations.
    assert set(users) == {"root", "adm", "alice"}
    assert users["adm"]["sessions"] == []

    alice = users["alice"]
    assert len(alice["sessions"]) == 1
    chat = alice["sessions"][0]
    assert chat["title"] == "Greetings"
    # Messages are present and in chronological order.
    assert [m["role"] for m in chat["messages"]] == ["user", "assistant"]
    assert [m["content"] for m in chat["messages"]] == ["hi", "hello there"]


@pytest.mark.parametrize("role", ["admin", "user"])
def test_non_super_admin_cannot_export(export_env, role):
    client, tokens = export_env
    resp = client.get("/admin/export", headers=_auth(tokens[role]))
    assert resp.status_code == 403


def test_export_requires_auth(export_env):
    client, _ = export_env
    resp = client.get("/admin/export")
    assert resp.status_code == 401
