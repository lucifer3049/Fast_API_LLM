"""Mock LLM provider — deterministic, offline, free.

Used to wire the chat flow end-to-end before the real Groq adapter lands
(PLAN Day 4 → Day 5). It implements `app.domain.ports.LLMProvider` so swapping
in Groq later is a config change, not a code change. The reply echoes the latest
user turn with a visible marker so a demo makes the mock obvious.
"""
from __future__ import annotations

from collections.abc import Iterator, Sequence

from app.domain.chat import LLMMessage, MessageRole

_CHUNK = 8  # characters per streamed delta — enough to look incremental in a demo


class MockLLMProvider:
    """Implements `app.domain.ports.LLMProvider` without any network call."""

    def complete(self, messages: Sequence[LLMMessage]) -> str:
        last_user = next(
            (m.content for m in reversed(messages) if m.role is MessageRole.USER),
            "",
        )
        return f"[mock-llm] You said: {last_user}"

    def stream(self, messages: Sequence[LLMMessage]) -> Iterator[str]:
        # Slice the full reply into small deltas; concatenating them reproduces
        # `complete` exactly (the port contract), so streamed and non-streamed
        # paths persist identical content.
        reply = self.complete(messages)
        for i in range(0, len(reply), _CHUNK):
            yield reply[i : i + _CHUNK]

    def health_check(self) -> None:
        # Offline and deterministic: always available.
        return None
