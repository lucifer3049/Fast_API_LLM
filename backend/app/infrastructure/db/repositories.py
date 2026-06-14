"""SQLAlchemy implementations of domain repository ports."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.user import Role
from app.infrastructure.db.models import User


class SqlUserRepository:
    """Implements `app.domain.ports.UserRepository`."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return self._session.get(User, user_id)

    def get_by_username(self, username: str) -> User | None:
        stmt = select(User).where(func.lower(User.username) == username.lower())
        return self._session.scalar(stmt)

    def add(self, user: User) -> User:
        self._session.add(user)
        self._session.flush()  # assign PK without committing (caller owns the tx)
        return user

    def list_all(self) -> list[User]:
        stmt = select(User).order_by(User.created_at.asc())
        return list(self._session.scalars(stmt).all())

    def count_active_by_role(self, role: Role) -> int:
        stmt = (
            select(func.count())
            .select_from(User)
            .where(User.role == role, User.is_active.is_(True))
        )
        return int(self._session.scalar(stmt) or 0)
