"""`@require_permission` decorator — the single RBAC gate for views.

Authorisation is checked against the permission matrix (domain), never scattered
as ad-hoc role comparisons in view bodies (PLAN §3.3). Stack it below the
`auth_required` decorator so `current_user` is populated first.
"""
from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import TypeVar

from app.application.errors import PermissionDeniedError
from app.domain.user import Permission, role_has_permission
from app.interface.deps import current_user

F = TypeVar("F", bound=Callable[..., object])


def require_permission(permission: Permission) -> Callable[[F], F]:
    def decorator(fn: F) -> F:
        @wraps(fn)
        def wrapper(*args: object, **kwargs: object) -> object:
            user = current_user()
            if not role_has_permission(user.role, permission):
                raise PermissionDeniedError()
            return fn(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
