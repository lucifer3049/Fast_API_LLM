"""JWT issuing / verification — HS256 (PLAN §2).

Single issuer, single service: HS256 with an env-provided secret is sufficient.
The token carries the user id (`sub`), role, and expiry. Decoding raises
`TokenError` on any problem (expired, bad signature, malformed) so callers can
map it to 401 uniformly.
"""
from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

import jwt

from app.domain.user import Role
from app.infrastructure.config import get_settings


class TokenError(Exception):
    """Raised when a token cannot be verified."""


@dataclass(frozen=True)
class TokenClaims:
    user_id: uuid.UUID
    role: Role


def create_access_token(user_id: uuid.UUID, role: Role) -> str:
    settings = get_settings()
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role.value,
        "iat": now,
        "exp": now + dt.timedelta(minutes=settings.jwt_access_token_expires_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> TokenClaims:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return TokenClaims(user_id=uuid.UUID(payload["sub"]), role=Role(payload["role"]))
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise TokenError(str(exc)) from exc
