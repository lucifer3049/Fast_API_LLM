"""Tests for the super_admin seed — invariant I-1 (PLAN §3.4)."""
from __future__ import annotations

import pytest

from app.domain.user import Role
from app.infrastructure.config import Settings
from app.infrastructure.db.models import User
from app.infrastructure.db.repositories import SqlUserRepository
from app.infrastructure.seed import SeedConfigError, seed_super_admin
from app.infrastructure.security.password import hash_password, verify_password


def make_settings(username="root", password="rootpass123") -> Settings:
    # Explicit init kwargs take precedence over any ambient env / .env.
    return Settings(
        super_admin_username=username,
        super_admin_password=password,
        _env_file=None,
    )


@pytest.mark.parametrize(
    "username,password",
    [(None, "pw"), ("root", None), (None, None), ("", "pw"), ("root", "")],
)
def test_missing_env_fails_fast(db_session, username, password):
    settings = make_settings(username=username, password=password)
    with pytest.raises(SeedConfigError):
        seed_super_admin(db_session, settings)


def test_creates_super_admin(db_session):
    settings = make_settings()
    created = seed_super_admin(db_session, settings)

    assert created is not None
    assert created.role == Role.SUPER_ADMIN
    assert created.is_active is True
    assert verify_password(created.password_hash, "rootpass123")
    # Password is never stored in plaintext.
    assert created.password_hash != "rootpass123"


def test_seed_is_idempotent(db_session):
    settings = make_settings()
    first = seed_super_admin(db_session, settings)
    second = seed_super_admin(db_session, settings)

    assert first is not None
    assert second is None  # already existed -> skipped, no error

    repo = SqlUserRepository(db_session)
    assert repo.count_active_by_role(Role.SUPER_ADMIN) == 1


def test_existing_username_with_wrong_role_is_rejected(db_session):
    # A non-super_admin already owns the configured username.
    db_session.add(
        User(
            username="root",
            password_hash=hash_password("x"),
            role=Role.USER,
            is_active=True,
        )
    )
    db_session.flush()

    with pytest.raises(SeedConfigError):
        seed_super_admin(db_session, make_settings())
