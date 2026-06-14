"""ChatService SSE-streaming tests: token sequence, persistence, partial-on-error.

Pure unit tests over the fake repository + fake LLM (no DB, no network). The
`commit` hook the service calls between turns is replaced by a counter so we can
assert the user turn is committed before streaming and the assistant turn after.
"""
from __future__ import annotations

import uuid

import pytest

from app.application.chat_service import ChatService
from app.application.errors import NotFoundError, ValidationError
from app.domain.chat import MessageRole
from app.domain.user import Role
from app.infrastructure.db.models import User
from app.infrastructure.llm.mock import MockLLMProvider


def make_user(role: Role = Role.USER) -> User:
    return User(
        id=uuid.uuid4(),
        username=f"user-{uuid.uuid4().hex[:8]}",
        password_hash="x",
        role=role,
        is_active=True,
    )


@pytest.fixture
def svc(fake_chats, fake_llm) -> ChatService:
    return ChatService(fake_chats, fake_llm)


def drain(events):
    return list(events)


# ---- open_stream (pre-stream phase) ----
def test_open_stream_persists_user_turn_and_prompt(svc):
    user = make_user()
    session = svc.create_session(user)
    handle = svc.open_stream(user, session.id, "hello")

    assert handle.user_message.role is MessageRole.USER
    assert handle.user_message.content == "hello"
    assert [m.content for m in handle.prompt] == ["hello"]
    # User turn is already persisted (visible in history) before any token streams.
    assert [m.content for m in svc.get_session(user, session.id)["messages"]] == ["hello"]


def test_open_stream_sets_title_on_first_turn(svc):
    user = make_user()
    session = svc.create_session(user)
    svc.open_stream(user, session.id, "What is the capital of France?")
    assert session.title == "What is the capital of France?"


def test_open_stream_rejects_blank(svc):
    user = make_user()
    session = svc.create_session(user)
    with pytest.raises(ValidationError):
        svc.open_stream(user, session.id, "   ")


def test_open_stream_foreign_session_is_404(svc):
    alice, bob = make_user(), make_user()
    session = svc.create_session(alice)
    with pytest.raises(NotFoundError):
        svc.open_stream(bob, session.id, "hi")


# ---- stream_reply (streaming phase) ----
def test_stream_reply_yields_tokens_then_done(svc, fake_llm):
    fake_llm.reply = "hi!"
    user = make_user()
    session = svc.create_session(user)
    handle = svc.open_stream(user, session.id, "hey")

    commits = []
    events = drain(svc.stream_reply(handle, lambda: commits.append(1)))

    tokens = [e["value"] for e in events if e["type"] == "token"]
    assert "".join(tokens) == "hi!"
    done = [e for e in events if e["type"] == "done"]
    assert len(done) == 1
    assert done[0]["assistant_message"].content == "hi!"
    assert len(commits) == 1  # assistant turn committed once, after the stream


def test_stream_reply_persists_assistant_after_user(svc, fake_llm):
    fake_llm.reply = "world"
    user = make_user()
    session = svc.create_session(user)
    handle = svc.open_stream(user, session.id, "hello")
    drain(svc.stream_reply(handle, lambda: None))

    history = svc.get_session(user, session.id)["messages"]
    assert [(m.role, m.content) for m in history] == [
        (MessageRole.USER, "hello"),
        (MessageRole.ASSISTANT, "world"),
    ]


def test_stream_reply_persists_partial_on_upstream_error(svc, fake_llm):
    fake_llm.reply = "abcdef"
    fake_llm.fail_after = 3  # drop after 3 deltas ("abc")
    user = make_user()
    session = svc.create_session(user)
    handle = svc.open_stream(user, session.id, "hello")

    commits = []
    events = drain(svc.stream_reply(handle, lambda: commits.append(1)))

    assert [e["value"] for e in events if e["type"] == "token"] == ["a", "b", "c"]
    error = [e for e in events if e["type"] == "error"]
    assert len(error) == 1
    # The partial reply is still saved so the user turn isn't left dangling.
    assert error[0]["assistant_message"].content == "abc"
    assert len(commits) == 1
    history = svc.get_session(user, session.id)["messages"]
    assert history[-1].content == "abc"


# ---- mock provider streaming contract ----
def test_mock_stream_concatenates_to_complete():
    from app.domain.chat import LLMMessage

    mock = MockLLMProvider()
    prompt = [LLMMessage(role=MessageRole.USER, content="ping")]
    assert "".join(mock.stream(prompt)) == mock.complete(prompt)
