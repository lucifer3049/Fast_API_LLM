"""Tests for JWT issuing / verification."""
from __future__ import annotations

import uuid

import pytest

from app.domain.user import Role
from app.infrastructure.security.jwt import (
    TokenError,
    create_access_token,
    decode_access_token,
)


def test_token_round_trip():
    uid = uuid.uuid4()
    token = create_access_token(uid, Role.ADMIN)

    claims = decode_access_token(token)

    assert claims.user_id == uid
    assert claims.role == Role.ADMIN


def test_decode_rejects_garbage():
    with pytest.raises(TokenError):
        decode_access_token("not-a-jwt")


def test_decode_rejects_tampered_token():
    token = create_access_token(uuid.uuid4(), Role.USER)
    tampered = token[:-2] + ("aa" if not token.endswith("aa") else "bb")

    with pytest.raises(TokenError):
        decode_access_token(tampered)
