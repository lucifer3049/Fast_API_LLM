"""Shared test fixtures.

`db_session` gives a real SQLAlchemy session on in-memory SQLite (fast, no
external service) for integration-style tests of repositories and seed.
`FakeUserRepository` is an in-memory port double for pure unit tests of services.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.domain.user import Role
from app.infrastructure.db.base import Base
from app.infrastructure.db.models import User  # noqa: F401 - registers metadata


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
