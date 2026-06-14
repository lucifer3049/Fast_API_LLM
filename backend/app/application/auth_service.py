"""Auth use cases: login, change own password.

The service orchestrates repository + security primitives and contains no
framework code. Logout is intentionally not here: with stateless JWT the client
discards the token (documented in README).
"""
from __future__ import annotations

import uuid

from app.application.errors import AuthenticationError, NotFoundError, ValidationError
from app.domain.ports import UserRepository
from app.infrastructure.db.models import User
from app.infrastructure.security.password import (
    hash_password,
    needs_rehash,
    verify_password,
)

MIN_PASSWORD_LENGTH = 8


class AuthService:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    def authenticate(self, username: str, password: str) -> User:
        """Return the user on valid credentials, else raise AuthenticationError.

        Disabled accounts and unknown usernames both fail with the same generic
        error to avoid leaking which usernames exist.
        """
        user = self._users.get_by_username(username)
        if user is None or not verify_password(user.password_hash, password):
            raise AuthenticationError()
        if not user.is_active:
            raise AuthenticationError("Account is disabled")

        # Transparently upgrade the hash if Argon2 params changed.
        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)

        return user

    def change_own_password(
        self, user_id: uuid.UUID, current_password: str, new_password: str
    ) -> None:
        user = self._users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("User not found")
        if not verify_password(user.password_hash, current_password):
            raise AuthenticationError("Current password is incorrect")
        if len(new_password) < MIN_PASSWORD_LENGTH:
            raise ValidationError(
                f"New password must be at least {MIN_PASSWORD_LENGTH} characters"
            )
        if verify_password(user.password_hash, new_password):
            raise ValidationError("New password must differ from the current one")
        user.password_hash = hash_password(new_password)
