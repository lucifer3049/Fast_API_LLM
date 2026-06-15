"""Marshmallow schemas for request/response validation and OpenAPI docs."""
from __future__ import annotations

from apiflask import Schema
from apiflask.fields import Boolean, DateTime, Enum, Nested, String
from apiflask.validators import Length

from app.domain.chat import MessageRole
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


# ---- Chat ----
class CreateSessionIn(Schema):
    # Optional: a session with no title is auto-named from its first message.
    title = String(required=False, validate=Length(max=200))


class ChatSessionOut(Schema):
    """List item — no messages, keeps the left-side list query off the N+1 path."""

    id = String()
    title = String(allow_none=True)
    created_at = DateTime()
    updated_at = DateTime()


class ChatMessageOut(Schema):
    id = String()
    role = Enum(MessageRole, by_value=True)
    content = String()
    created_at = DateTime()


class ChatSessionDetailOut(ChatSessionOut):
    """A session with its full message history (chronological)."""

    messages = Nested(ChatMessageOut, many=True)


class SendMessageIn(Schema):
    content = String(required=True, validate=Length(min=1, max=8000))


class SendMessageOut(Schema):
    user_message = Nested(ChatMessageOut)
    assistant_message = Nested(ChatMessageOut)


# ---- Super-admin export ----
class ExportMessageOut(Schema):
    role = Enum(MessageRole, by_value=True)
    content = String()
    created_at = DateTime()


class ExportSessionOut(Schema):
    id = String()
    title = String(allow_none=True)
    created_at = DateTime()
    updated_at = DateTime()
    messages = Nested(ExportMessageOut, many=True)


class ExportUserOut(Schema):
    id = String()
    username = String()
    role = Enum(Role, by_value=True)
    sessions = Nested(ExportSessionOut, many=True)


class ExportOut(Schema):
    exported_at = DateTime()
    users = Nested(ExportUserOut, many=True)
