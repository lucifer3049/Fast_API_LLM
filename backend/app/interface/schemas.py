"""Marshmallow schemas for request/response validation and OpenAPI docs."""
from __future__ import annotations

from apiflask import Schema
from apiflask.fields import Boolean, DateTime, Enum, String
from apiflask.validators import Length

from app.domain.user import Role


# ---- Auth ----
class LoginIn(Schema):
    username = String(required=True, validate=Length(min=1, max=64))
    password = String(required=True, validate=Length(min=1))


class TokenOut(Schema):
    access_token = String()
    token_type = String()


class ChangePasswordIn(Schema):
    current_password = String(required=True, validate=Length(min=1))
    new_password = String(required=True, validate=Length(min=8, max=256))


class MessageOut(Schema):
    message = String()


# ---- Admin: user management ----
class CreateUserIn(Schema):
    username = String(required=True, validate=Length(min=1, max=64))
    password = String(required=True, validate=Length(min=8, max=256))
    # super_admin is intentionally not creatable via the API (seed only).
    role = Enum(Role, by_value=True, load_default=Role.USER)


class SetActiveIn(Schema):
    is_active = Boolean(required=True)


# ---- User ----
class UserOut(Schema):
    id = String()
    username = String()
    role = Enum(Role, by_value=True)  # serialize to the enum value, e.g. "super_admin"
    is_active = Boolean()
    created_at = DateTime()
    updated_at = DateTime()
