"""Application-layer errors.

Services raise these framework-agnostic errors; the interface layer maps them to
HTTP status codes (so business rules return 4xx, not 500). PLAN §3.3.
"""
from __future__ import annotations


class AppError(Exception):
    status_code = 400
    message = "Bad request"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.message)
        if message:
            self.message = message


class AuthenticationError(AppError):
    status_code = 401
    message = "Invalid credentials"


class PermissionDeniedError(AppError):
    status_code = 403
    message = "Permission denied"


class NotFoundError(AppError):
    status_code = 404
    message = "Not found"


class ConflictError(AppError):
    status_code = 409
    message = "Conflict"


class ValidationError(AppError):
    status_code = 422
    message = "Validation failed"


class LLMError(AppError):
    """The LLM upstream failed or returned an unusable response (bad gateway)."""

    status_code = 502
    message = "LLM provider error"
