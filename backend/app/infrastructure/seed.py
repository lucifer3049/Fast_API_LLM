"""super_admin idempotent seed — invariant I-1 (PLAN §3.4).

Rules:
  * Missing SUPER_ADMIN_USERNAME or SUPER_ADMIN_PASSWORD -> raise (fail fast).
    The app must never silently boot with no administrator.
  * super_admin already present -> skip (idempotent), no error, no rebuild.
  * Otherwise -> create it.

Run as a module on container start (entrypoint), after migrations:
    python -m app.infrastructure.seed
Credentials come only from env — nothing is hardcoded.
"""
from __future__ import annotations

import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.user import Role
from app.infrastructure.config import Settings, get_settings
from app.infrastructure.db.models import User
from app.infrastructure.db.repositories import SqlUserRepository
from app.infrastructure.db.session import session_scope
from app.infrastructure.security.password import hash_password

logger = logging.getLogger(__name__)


class SeedConfigError(RuntimeError):
    """Raised when required seed env vars are missing (fail fast)."""


def seed_super_admin(session: Session, settings: Settings | None = None) -> User | None:
    """Ensure exactly the configured super_admin exists. Returns the created
    user, or None if one already existed (idempotent)."""
    settings = settings or get_settings()
    username = (settings.super_admin_username or "").strip()
    password = settings.super_admin_password or ""

    if not username or not password:
        raise SeedConfigError(
            "SUPER_ADMIN_USERNAME and SUPER_ADMIN_PASSWORD must both be set; "
            "refusing to start without an administrator."
        )

    repo = SqlUserRepository(session)

    # Idempotent: if a super_admin with this username already exists, do nothing.
    existing = repo.get_by_username(username)
    if existing is not None:
        if existing.role != Role.SUPER_ADMIN:
            raise SeedConfigError(
                f"User '{username}' exists but is not a super_admin; refusing to seed."
            )
        logger.info("super_admin '%s' already exists; skipping seed.", username)
        return None

    user = User(
        username=username,
        password_hash=hash_password(password),
        role=Role.SUPER_ADMIN,
        is_active=True,
    )
    try:
        repo.add(user)
        session.flush()
    except IntegrityError:
        # Concurrent seed won the race; treat as idempotent success.
        session.rollback()
        logger.info("super_admin '%s' created concurrently; skipping.", username)
        return None

    logger.info("super_admin '%s' created.", username)
    return user


def main() -> None:
    logging.basicConfig(level=get_settings().log_level.upper())
    with session_scope() as session:
        seed_super_admin(session)


if __name__ == "__main__":
    main()
