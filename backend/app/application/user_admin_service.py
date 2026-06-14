"""User administration use cases (admin / super_admin).

All authorisation flows through the permission matrix (PLAN §3.3); cross-role
constraints are enforced here in the service, returning 4xx rather than 500.

Invariant I-2 ("always >= 1 active super_admin", PLAN §3.4) is guaranteed
structurally: there is no API path that creates, deactivates, or demotes a
super_admin. super_admin accounts can only be created by the seed, and any
operation targeting a super_admin is rejected here.
"""
from __future__ import annotations

import uuid

from app.application.errors import ConflictError, NotFoundError, PermissionDeniedError, ValidationError
from app.domain.ports import UserRepository
from app.domain.user import Permission, Role, role_has_permission
from app.infrastructure.db.models import User
from app.infrastructure.security.password import hash_password

MIN_PASSWORD_LENGTH = 8


class UserAdminService:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    def list_users(self, actor: User) -> list[User]:
        self._require(actor, Permission.LIST_USERS)
        return self._users.list_all()

    def create_user(self, actor: User, username: str, password: str, role: Role) -> User:
        if role is Role.SUPER_ADMIN:
            # super_admin is created only by the seed (invariant I-1/I-2).
            raise ValidationError("Cannot create a super_admin via the API")

        # admin may create users; only super_admin may create admins.
        required = Permission.CREATE_ADMIN if role is Role.ADMIN else Permission.CREATE_USER
        self._require(actor, required)

        username = username.strip()
        if not username:
            raise ValidationError("Username is required")
        if len(password) < MIN_PASSWORD_LENGTH:
            raise ValidationError(
                f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
            )
        if self._users.get_by_username(username) is not None:
            raise ConflictError("Username already taken")

        user = User(
            username=username,
            password_hash=hash_password(password),
            role=role,
            is_active=True,
        )
        return self._users.add(user)

    def set_active(self, actor: User, target_id: uuid.UUID, is_active: bool) -> User:
        target = self._get(target_id)

        if target.role is Role.SUPER_ADMIN:
            # No API path deactivates a super_admin -> protects invariant I-2.
            raise PermissionDeniedError("super_admin accounts cannot be modified")

        required = (
            Permission.TOGGLE_ADMIN_ACTIVE
            if target.role is Role.ADMIN
            else Permission.TOGGLE_USER_ACTIVE
        )
        self._require(actor, required)

        # Note: self-deactivation is already impossible — no role passes the gate
        # above for a target of its own role, and super_admins are unreachable.
        target.is_active = is_active
        return target

    def promote_to_admin(self, actor: User, target_id: uuid.UUID) -> User:
        self._require(actor, Permission.PROMOTE_USER_TO_ADMIN)
        target = self._get(target_id)
        if target.role is not Role.USER:
            raise ConflictError("Only a regular user can be promoted to admin")
        target.role = Role.ADMIN
        return target

    # ---- helpers ----
    def _get(self, target_id: uuid.UUID) -> User:
        target = self._users.get_by_id(target_id)
        if target is None:
            raise NotFoundError("User not found")
        return target

    @staticmethod
    def _require(actor: User, permission: Permission) -> None:
        if not role_has_permission(actor.role, permission):
            raise PermissionDeniedError()
