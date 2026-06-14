"""Unit tests for AuthService (pure, fake repository — no DB)."""
from __future__ import annotations

import uuid

import pytest

from app.application.auth_service import AuthService
from app.application.errors import AuthenticationError, NotFoundError, ValidationError
from app.domain.user import Role
from app.infrastructure.db.models import User
from app.infrastructure.security.password import hash_password, verify_password


def make_user(username="alice", password="secret123", role=Role.USER, is_active=True) -> User:
    return User(
        id=uuid.uuid4(),
        username=username,
        password_hash=hash_password(password),
        role=role,
        is_active=is_active,
    )


def test_authenticate_success(fake_users):
    user = make_user()
    fake_users.add(user)
    svc = AuthService(fake_users)

    result = svc.authenticate("alice", "secret123")

    assert result.id == user.id


def test_authenticate_is_case_insensitive_on_username(fake_users):
    fake_users.add(make_user(username="Alice"))
    svc = AuthService(fake_users)

    assert svc.authenticate("alice", "secret123") is not None


def test_authenticate_wrong_password(fake_users):
    fake_users.add(make_user())
    svc = AuthService(fake_users)

    with pytest.raises(AuthenticationError):
        svc.authenticate("alice", "wrong")


def test_authenticate_unknown_user(fake_users):
    svc = AuthService(fake_users)

    with pytest.raises(AuthenticationError):
        svc.authenticate("nobody", "whatever")


def test_authenticate_disabled_account(fake_users):
    fake_users.add(make_user(is_active=False))
    svc = AuthService(fake_users)

    with pytest.raises(AuthenticationError):
        svc.authenticate("alice", "secret123")


def test_change_password_success(fake_users):
    user = make_user()
    fake_users.add(user)
    svc = AuthService(fake_users)

    svc.change_own_password(user.id, "secret123", "brand-new-pass")

    assert verify_password(user.password_hash, "brand-new-pass")
    assert not verify_password(user.password_hash, "secret123")


def test_change_password_wrong_current(fake_users):
    user = make_user()
    fake_users.add(user)
    svc = AuthService(fake_users)

    with pytest.raises(AuthenticationError):
        svc.change_own_password(user.id, "nope", "brand-new-pass")


def test_change_password_too_short(fake_users):
    user = make_user()
    fake_users.add(user)
    svc = AuthService(fake_users)

    with pytest.raises(ValidationError):
        svc.change_own_password(user.id, "secret123", "short")


def test_change_password_same_as_current(fake_users):
    user = make_user()
    fake_users.add(user)
    svc = AuthService(fake_users)

    with pytest.raises(ValidationError):
        svc.change_own_password(user.id, "secret123", "secret123")


def test_change_password_unknown_user(fake_users):
    svc = AuthService(fake_users)

    with pytest.raises(NotFoundError):
        svc.change_own_password(uuid.uuid4(), "x", "brand-new-pass")
