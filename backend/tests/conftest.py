"""Shared test fixtures.

`db_session` gives a real SQLAlchemy session on in-memory SQLite (fast, no
external service) for integration-style tests of repositories and seed.
`FakeUserRepository` is an in-memory port double for pure unit tests of services.
"""
from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator, Sequence

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.domain.chat import LLMMessage
from app.domain.user import Role
from app.infrastructure.db.base import Base

# Importing the models module registers User, ChatSession and Message on the
# shared metadata so `create_all` builds every table.
from app.infrastructure.db.models import ChatSession, Message, User  # noqa: F401


@pytest.fixture
def db_session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


class FakeUserRepository:
    """In-memory implementation of app.domain.ports.UserRepository."""

    def __init__(self) -> None:
        self._by_id: dict[uuid.UUID, User] = {}

    def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return self._by_id.get(user_id)

    def get_by_username(self, username: str) -> User | None:
        for u in self._by_id.values():
            if u.username.lower() == username.lower():
                return u
        return None

    def add(self, user: User) -> User:
        if user.id is None:
            user.id = uuid.uuid4()
        self._by_id[user.id] = user
        return user

    def list_all(self) -> list[User]:
        return list(self._by_id.values())

    def count_active_by_role(self, role: Role) -> int:
        return sum(1 for u in self._by_id.values() if u.role == role and u.is_active)


@pytest.fixture
def fake_users() -> FakeUserRepository:
    return FakeUserRepository()


class FakeChatRepository:
    """In-memory implementation of app.domain.ports.ChatRepository.

    Mimics the DB defaults the ORM/server would supply (PK, timestamps) so
    service logic can be tested without a database.
    """

    def __init__(self) -> None:
        self._sessions: dict[uuid.UUID, ChatSession] = {}
        self._messages: dict[uuid.UUID, Message] = {}

    def add_session(self, session: ChatSession) -> ChatSession:
        if session.id is None:
            session.id = uuid.uuid4()
        now = dt.datetime.now(dt.timezone.utc)
        if session.created_at is None:
            session.created_at = now
        if session.updated_at is None:
            session.updated_at = now
        self._sessions[session.id] = session
        return session

    def get_session(self, session_id: uuid.UUID) -> ChatSession | None:
        return self._sessions.get(session_id)

    def list_sessions(self, user_id: uuid.UUID) -> list[ChatSession]:
        sessions = [s for s in self._sessions.values() if s.user_id == user_id]
        return sorted(sessions, key=lambda s: s.updated_at, reverse=True)

    def delete_session(self, session: ChatSession) -> None:
        self._sessions.pop(session.id, None)
        for mid in [m.id for m in self._messages.values() if m.session_id == session.id]:
            self._messages.pop(mid, None)

    def add_message(self, message: Message) -> Message:
        if message.id is None:
            message.id = uuid.uuid4()
        if message.created_at is None:
            message.created_at = dt.datetime.now(dt.timezone.utc)
        self._messages[message.id] = message
        return message

    def list_messages(self, session_id: uuid.UUID) -> list[Message]:
        msgs = [m for m in self._messages.values() if m.session_id == session_id]
        return sorted(msgs, key=lambda m: m.created_at)


class FakeLLMProvider:
    """Deterministic in-memory LLMProvider double; records the last prompt.

    `stream` yields the reply one character at a time so tests can assert the
    delta sequence. Set `fail_after` to raise mid-stream after that many deltas,
    simulating a dropped upstream so the partial-persist path is exercised.
    """

    def __init__(self, reply: str = "fake reply") -> None:
        self.reply = reply
        self.last_prompt: Sequence[LLMMessage] = ()
        self.fail_after: int | None = None

    def complete(self, messages: Sequence[LLMMessage]) -> str:
        self.last_prompt = list(messages)
        return self.reply

    def stream(self, messages: Sequence[LLMMessage]) -> Iterator[str]:
        self.last_prompt = list(messages)
        for i, ch in enumerate(self.reply):
            if self.fail_after is not None and i >= self.fail_after:
                raise RuntimeError("simulated upstream failure")
            yield ch


@pytest.fixture
def fake_chats() -> FakeChatRepository:
    return FakeChatRepository()


@pytest.fixture
def fake_llm() -> FakeLLMProvider:
    return FakeLLMProvider()
