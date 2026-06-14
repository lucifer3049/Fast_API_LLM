"""Dependency wiring for the interface layer.

Provides a request-scoped DB session, the Bearer-token authenticator (decodes
JWT -> loads the active user), and small factories that assemble services with
the request's repositories. Views stay thin; swapping a fake repo/LLM in tests
is just a different factory.
"""
from __future__ import annotations

from apiflask import HTTPTokenAuth
from flask import Flask, g
from sqlalchemy.orm import Session

from app.application.auth_service import AuthService
from app.infrastructure.db.models import User
from app.infrastructure.db.repositories import SqlUserRepository
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.security.jwt import TokenError, decode_access_token

auth = HTTPTokenAuth(scheme="Bearer", description="JWT access token from /auth/login")


def get_db() -> Session:
    if "db" not in g:
        g.db = SessionLocal()
    return g.db


def user_repository() -> SqlUserRepository:
    return SqlUserRepository(get_db())


def auth_service() -> AuthService:
    return AuthService(user_repository())


@auth.verify_token
def verify_token(token: str) -> User | None:
    """Decode the JWT and load the active user, or None to reject (401)."""
    try:
        claims = decode_access_token(token)
    except TokenError:
        return None
    user = user_repository().get_by_id(claims.user_id)
    if user is None or not user.is_active:
        return None
    return user


def current_user() -> User:
    """The authenticated user for the current request."""
    return auth.current_user


def init_app(app: Flask) -> None:
    @app.teardown_appcontext
    def _close_db(_exc: BaseException | None) -> None:
        db = g.pop("db", None)
        if db is not None:
            db.close()
