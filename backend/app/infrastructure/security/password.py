"""Password hashing — Argon2id (PLAN §2).

Passwords are never stored in plaintext. Argon2id is memory-hard and
GPU-resistant; the parameters use argon2-cffi defaults which are sane for a
web login flow.
"""
from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError

_hasher = PasswordHasher()


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(password_hash: str, plain: str) -> bool:
    try:
        return _hasher.verify(password_hash, plain)
    except (VerifyMismatchError, VerificationError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True if the hash was made with outdated parameters (rehash on next login)."""
    return _hasher.check_needs_rehash(password_hash)
