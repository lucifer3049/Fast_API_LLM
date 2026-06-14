"""Domain ports (abstract interfaces) implemented by infrastructure.

Dependency rule: domain defines the contract; infrastructure provides the
implementation (PLAN §3.1). To keep a single `User` representation without
hand-mapping while still importing zero framework code at runtime, the ORM model
is referenced only under TYPE_CHECKING.
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:  # type-only: no SQLAlchemy import at runtime in the domain layer
    from app.domain.user import Role
    from app.infrastructure.db.models import User


@runtime_checkable
class UserRepository(Protocol):
    def get_by_id(self, user_id: uuid.UUID) -> "User | None": ...

    def get_by_username(self, username: str) -> "User | None": ...

    def add(self, user: "User") -> "User": ...

    def list_all(self) -> "list[User]": ...

    def count_active_by_role(self, role: "Role") -> int: ...
