"""UserAdminService tests: cross-role constraints and invariant I-2 (PLAN §3.4)."""
from __future__ import annotations

import uuid

import pytest

from app.application.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from app.application.user_admin_service import UserAdminService
from app.domain.user import Role
from app.infrastructure.db.models import User
from app.infrastructure.security.password import hash_password


def make_user(username, role=Role.USER, is_active=True) -> User:
    return User(
        id=uuid.uuid4(),
        username=username,
        password_hash=hash_password("password123"),
        role=role,
        is_active=is_active,
    )


@pytest.fixture
def actors(fake_users):
    user = make_user("u", Role.USER)
    admin = make_user("a", Role.ADMIN)
    superadmin = make_user("s", Role.SUPER_ADMIN)
    for u in (user, admin, superadmin):
        fake_users.add(u)
    return user, admin, superadmin


# ---- create_user ----
def test_admin_can_create_user(fake_users, actors):
    _, admin, _ = actors
    svc = UserAdminService(fake_users)
    created = svc.create_user(admin, "newuser", "password123", Role.USER)
    assert created.role is Role.USER


def test_admin_cannot_create_admin(fake_users, actors):
    _, admin, _ = actors
    svc = UserAdminService(fake_users)
    with pytest.raises(PermissionDeniedError):
        svc.create_user(admin, "newadmin", "password123", Role.ADMIN)


def test_super_admin_can_create_admin(fake_users, actors):
    _, _, superadmin = actors
    svc = UserAdminService(fake_users)
    created = svc.create_user(superadmin, "newadmin", "password123", Role.ADMIN)
    assert created.role is Role.ADMIN


def test_plain_user_cannot_create_user(fake_users, actors):
    user, _, _ = actors
    svc = UserAdminService(fake_users)
    with pytest.raises(PermissionDeniedError):
        svc.create_user(user, "x", "password123", Role.USER)


def test_cannot_create_super_admin_via_api(fake_users, actors):
    _, _, superadmin = actors
    svc = UserAdminService(fake_users)
    with pytest.raises(ValidationError):
        svc.create_user(superadmin, "root2", "password123", Role.SUPER_ADMIN)


def test_create_user_duplicate_username(fake_users, actors):
    _, admin, _ = actors
    svc = UserAdminService(fake_users)
    with pytest.raises(ConflictError):
        svc.create_user(admin, "u", "password123", Role.USER)  # "u" already exists


def test_create_user_short_password(fake_users, actors):
    _, admin, _ = actors
    svc = UserAdminService(fake_users)
    with pytest.raises(ValidationError):
        svc.create_user(admin, "shorty", "123", Role.USER)


# ---- list_users ----
def test_list_users_requires_permission(fake_users, actors):
    user, admin, _ = actors
    svc = UserAdminService(fake_users)
    assert len(svc.list_users(admin)) == 3
    with pytest.raises(PermissionDeniedError):
        svc.list_users(user)


# ---- set_active ----
def test_admin_can_deactivate_user(fake_users, actors):
    user, admin, _ = actors
    svc = UserAdminService(fake_users)
    result = svc.set_active(admin, user.id, False)
    assert result.is_active is False


def test_admin_cannot_deactivate_admin(fake_users, actors):
    _, admin, _ = actors
    other_admin = make_user("a2", Role.ADMIN)
    fake_users.add(other_admin)
    svc = UserAdminService(fake_users)
    with pytest.raises(PermissionDeniedError):
        svc.set_active(admin, other_admin.id, False)


def test_super_admin_can_deactivate_admin(fake_users, actors):
    _, admin, superadmin = actors
    svc = UserAdminService(fake_users)
    result = svc.set_active(superadmin, admin.id, False)
    assert result.is_active is False


def test_super_admin_cannot_be_deactivated(fake_users, actors):
    """Invariant I-2: no API path deactivates a super_admin."""
    _, _, superadmin = actors
    other_super = make_user("s2", Role.SUPER_ADMIN)
    fake_users.add(other_super)
    svc = UserAdminService(fake_users)
    with pytest.raises(PermissionDeniedError):
        svc.set_active(superadmin, other_super.id, False)


def test_set_active_unknown_user(fake_users, actors):
    _, admin, _ = actors
    svc = UserAdminService(fake_users)
    with pytest.raises(NotFoundError):
        svc.set_active(admin, uuid.uuid4(), False)


# ---- promote ----
def test_super_admin_can_promote_user(fake_users, actors):
    user, _, superadmin = actors
    svc = UserAdminService(fake_users)
    result = svc.promote_to_admin(superadmin, user.id)
    assert result.role is Role.ADMIN


def test_admin_cannot_promote(fake_users, actors):
    user, admin, _ = actors
    svc = UserAdminService(fake_users)
    with pytest.raises(PermissionDeniedError):
        svc.promote_to_admin(admin, user.id)


def test_cannot_promote_non_user(fake_users, actors):
    _, admin, superadmin = actors
    svc = UserAdminService(fake_users)
    with pytest.raises(ConflictError):
        svc.promote_to_admin(superadmin, admin.id)  # already an admin
