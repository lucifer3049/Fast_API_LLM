"""Domain ports (abstract interfaces) implemented by infrastructure.

Dependency rule: domain defines the contract; infrastructure provides the
implementation (PLAN §3.1). To keep a single `User` representation without
hand-mapping while still importing zero framework code at runtime, the ORM model
is referenced only under TYPE_CHECKING.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from app.domain.chat import LLMMessage

if TYPE_CHECKING:  # type-only: no SQLAlchemy import at runtime in the domain layer
    from app.domain.user import Role
    from app.infrastructure.db.models import ChatSession, Message, User


@runtime_checkable
class UserRepository(Protocol):
    def get_by_id(self, user_id: uuid.UUID) -> "User | None": ...

    def get_by_username(self, username: str) -> "User | None": ...

    def add(self, user: "User") -> "User": ...

    def list_all(self) -> "list[User]": ...

    def count_active_by_role(self, role: "Role") -> int: ...


@runtime_checkable
class ChatRepository(Protocol):
    """Persistence for chat sessions and their messages.

    Reads are scoped so the hot paths stay index-aligned (PLAN §3.2): session
    lists never eager-load messages, and history loads in chronological order.
    Callers own the transaction; mutating methods flush but do not commit.
    """

    def add_session(self, session: "ChatSession") -> "ChatSession": ...

    def get_session(self, session_id: uuid.UUID) -> "ChatSession | None": ...

    def list_sessions(self, user_id: uuid.UUID) -> "list[ChatSession]": ...

    def delete_session(self, session: "ChatSession") -> None: ...

    def add_message(self, message: "Message") -> "Message": ...

    def list_messages(self, session_id: uuid.UUID) -> "list[Message]": ...

    def list_all_sessions_with_messages(self) -> "list[ChatSession]": ...


@runtime_checkable
class LLMProvider(Protocol):
    """Abstraction over the chat-completion backend (mock or Groq).

    `complete` returns the whole reply at once (used for short, non-interactive
    calls). `stream` yields the reply incrementally as content deltas, for SSE
    token-by-token rendering (PLAN §3.5); concatenating every delta reproduces
    what `complete` would have returned. Implementations raise on upstream
    failure so the caller can persist the partial turn and surface an error.
    """

    def complete(self, messages: Sequence[LLMMessage]) -> str: ...

    def stream(self, messages: Sequence[LLMMessage]) -> Iterator[str]: ...
