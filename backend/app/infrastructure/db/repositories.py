"""SQLAlchemy implementations of domain repository ports."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.domain.user import Role
from app.infrastructure.db.models import ChatSession, Message, User


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


class SqlChatRepository:
    """Implements `app.domain.ports.ChatRepository`."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add_session(self, session: ChatSession) -> ChatSession:
        self._session.add(session)
        self._session.flush()  # assign PK without committing (caller owns the tx)
        return session

    def get_session(self, session_id: uuid.UUID) -> ChatSession | None:
        return self._session.get(ChatSession, session_id)

    def list_sessions(self, user_id: uuid.UUID) -> list[ChatSession]:
        # Left-side list: most-recent first. No messages loaded -> avoids N+1.
        stmt = (
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(ChatSession.updated_at.desc())
        )
        return list(self._session.scalars(stmt).all())

    def delete_session(self, session: ChatSession) -> None:
        # Messages cascade via the FK / relationship cascade.
        self._session.delete(session)
        self._session.flush()

    def add_message(self, message: Message) -> Message:
        self._session.add(message)
        self._session.flush()
        return message

    def list_messages(self, session_id: uuid.UUID) -> list[Message]:
        # Chronological history, served by ix_messages_session_created.
        stmt = (
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.asc())
        )
        return list(self._session.scalars(stmt).all())

    def list_all_sessions_with_messages(self) -> list[ChatSession]:
        # Super-admin export (PLAN §3.2): every session with its messages eagerly
        # loaded via selectinload — one extra batched IN query for all messages,
        # not one per session, so the export stays off the N+1 path.
        stmt = (
            select(ChatSession)
            .options(selectinload(ChatSession.messages))
            .order_by(ChatSession.user_id, ChatSession.created_at.asc())
        )
        return list(self._session.scalars(stmt).all())
