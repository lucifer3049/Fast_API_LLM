"""Chat endpoints: session CRUD, history load, and sending a message.

Every route is gated by a coarse RBAC permission (all roles may chat); the
service enforces per-user ownership and returns 404 for foreign sessions.

Two ways to send a message: a plain JSON request that returns both turns at once,
and an SSE endpoint that streams the assistant reply token-by-token (PLAN §3.5).
The streaming view validates and persists the user turn *before* opening the
response, so 404/422 still arrive as real HTTP status codes; only the assistant
tokens flow inside the event stream.
"""
from __future__ import annotations

import json
import uuid

from apiflask import APIBlueprint
from flask import Response, stream_with_context

from app.domain.user import Permission
from app.interface.deps import auth, chat_service, current_user, get_db
from app.interface.permissions import require_permission
from app.interface.schemas import (
    ChatMessageOut,
    ChatSessionDetailOut,
    ChatSessionOut,
    CreateSessionIn,
    MessageOut,
    SendMessageIn,
    SendMessageOut,
)

chat_bp = APIBlueprint("chat", __name__, url_prefix="/chat", tag="Chat")

_message_schema = ChatMessageOut()


def _sse(event: str, data: dict) -> str:
    """One SSE frame: a named event plus a JSON payload (PLAN §3.5)."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@chat_bp.post("/sessions")
@chat_bp.auth_required(auth)
@chat_bp.input(CreateSessionIn)
@chat_bp.output(ChatSessionOut, status_code=201)
@chat_bp.doc(summary="Create a chat session")
@require_permission(Permission.USE_CHAT)
def create_session(json_data: dict):
    session = chat_service().create_session(current_user(), json_data.get("title"))
    get_db().commit()
    return session


@chat_bp.get("/sessions")
@chat_bp.auth_required(auth)
@chat_bp.output(ChatSessionOut(many=True))
@chat_bp.doc(summary="List own sessions", description="Most-recently-active first.")
@require_permission(Permission.MANAGE_OWN_CHATS)
def list_sessions():
    return chat_service().list_sessions(current_user())


@chat_bp.get("/sessions/<uuid:session_id>")
@chat_bp.auth_required(auth)
@chat_bp.output(ChatSessionDetailOut)
@chat_bp.doc(
    summary="Load a session with history",
    description="Returns the session and its messages in chronological order. "
    "404 if the session does not exist or belongs to another user.",
)
@require_permission(Permission.MANAGE_OWN_CHATS)
def get_session(session_id: uuid.UUID):
    return chat_service().get_session(current_user(), session_id)


@chat_bp.delete("/sessions/<uuid:session_id>")
@chat_bp.auth_required(auth)
@chat_bp.output(MessageOut)
@chat_bp.doc(summary="Delete own session", description="Cascades to its messages.")
@require_permission(Permission.MANAGE_OWN_CHATS)
def delete_session(session_id: uuid.UUID):
    chat_service().delete_session(current_user(), session_id)
    get_db().commit()
    return {"message": "Session deleted."}


@chat_bp.post("/sessions/<uuid:session_id>/messages")
@chat_bp.auth_required(auth)
@chat_bp.input(SendMessageIn)
@chat_bp.output(SendMessageOut, status_code=201)
@chat_bp.doc(
    summary="Send a message",
    description="Persists the user message, gets the assistant reply (mock LLM in "
    "this phase), persists it, and returns both. Streaming arrives in Day 5.",
)
@require_permission(Permission.USE_CHAT)
def send_message(session_id: uuid.UUID, json_data: dict):
    result = chat_service().send_message(current_user(), session_id, json_data["content"])
    get_db().commit()
    return result


@chat_bp.post("/sessions/<uuid:session_id>/messages/stream")
@chat_bp.auth_required(auth)
@chat_bp.input(SendMessageIn)
@chat_bp.doc(
    summary="Send a message (SSE streaming)",
    description=(
        "Persists the user turn, then streams the assistant reply as "
        "`text/event-stream`. Events: `meta` (the persisted user message + "
        "session title), repeated `token` (content deltas), and a terminal "
        "`done` (the persisted assistant message) or `error` (the partial reply "
        "that was still saved). Ownership/validation failures return 404/422 "
        "before the stream opens. Send the JWT as a Bearer header."
    ),
    responses={200: "Server-sent event stream of the assistant reply."},
)
@require_permission(Permission.USE_CHAT)
def stream_message(session_id: uuid.UUID, json_data: dict):
    svc = chat_service()
    db = get_db()
    # Validate + persist the user turn up front so 404/422 are real HTTP codes
    # and the user message is durable before the stream begins.
    handle = svc.open_stream(current_user(), session_id, json_data["content"])
    db.commit()

    def generate():
        yield _sse(
            "meta",
            {
                "session_id": str(handle.session.id),
                "title": handle.session.title,
                "user_message": _message_schema.dump(handle.user_message),
            },
        )
        for event in svc.stream_reply(handle, db.commit):
            if event["type"] == "token":
                yield _sse("token", {"value": event["value"]})
            elif event["type"] == "done":
                yield _sse(
                    "done",
                    {"assistant_message": _message_schema.dump(event["assistant_message"])},
                )
            elif event["type"] == "error":
                yield _sse(
                    "error",
                    {
                        "message": event["message"],
                        "assistant_message": _message_schema.dump(
                            event["assistant_message"]
                        ),
                    },
                )

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Defeat proxy/worker response buffering so tokens flush immediately.
            "X-Accel-Buffering": "no",
        },
    )
