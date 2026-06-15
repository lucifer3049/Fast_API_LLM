"""Super-admin export use case (PLAN §1.2 / §3.1).

Assembles a full JSON dump of every user's conversations. Authorisation flows
through the permission matrix (only super_admin holds ``EXPORT_ALL_CHATS``); the
check runs before any query so an unauthorised caller touches no data.

The shape is user-centric — users → their sessions → messages — so the export
is a complete, self-describing snapshot rather than a flat message list. All
users are included (even those with no conversations) so the dump reflects the
whole account roster.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

from app.domain.ports import ChatRepository, UserRepository
from app.domain.user import Permission, role_has_permission
from app.infrastructure.db.models import ChatSession, Message, User


class ExportService:
    def __init__(self, users: UserRepository, chats: ChatRepository) -> None:
        self._users = users
        self._chats = chats

    def export_all(self, actor: User) -> dict:
        from app.application.errors import PermissionDeniedError

        if not role_has_permission(actor.role, Permission.EXPORT_ALL_CHATS):
            raise PermissionDeniedError()

        users = self._users.list_all()  # ordered by created_at
        sessions_by_user: dict = defaultdict(list)
        for session in self._chats.list_all_sessions_with_messages():
            sessions_by_user[session.user_id].append(session)

        return {
            "exported_at": dt.datetime.now(dt.timezone.utc),
            "users": [self._dump_user(u, sessions_by_user.get(u.id, [])) for u in users],
        }

    def _dump_user(self, user: User, sessions: list[ChatSession]) -> dict:
        return {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "sessions": [self._dump_session(s) for s in sessions],
        }

    def _dump_session(self, session: ChatSession) -> dict:
        return {
            "id": session.id,
            "title": session.title,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "messages": [
                self._dump_message(m)
                for m in sorted(session.messages, key=lambda m: m.created_at)
            ],
        }

    @staticmethod
    def _dump_message(message: Message) -> dict:
        return {
            "role": message.role,
            "content": message.content,
            "created_at": message.created_at,
        }
