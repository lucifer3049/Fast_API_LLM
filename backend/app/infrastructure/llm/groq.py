"""Groq adapter implementing `app.domain.ports.LLMProvider`.

Groq exposes an OpenAI-compatible API, so we drive it with the official `openai`
client pointed at Groq's base URL — swapping providers later is just a base URL +
key change (PLAN §2). `complete` is one-shot; `stream` yields content deltas for
SSE token rendering (PLAN §3.5). Both translate the domain `LLMMessage` into the
wire role/content dicts and wrap upstream failures in `LLMError` so the caller
can persist the partial turn and return a 502 instead of a 500.
"""
from __future__ import annotations

from collections.abc import Iterator, Sequence

from openai import OpenAI, OpenAIError

from app.application.errors import LLMError
from app.domain.chat import LLMMessage


class GroqProvider:
    """OpenAI-compatible chat-completion client targeting Groq."""

    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    def complete(self, messages: Sequence[LLMMessage]) -> str:
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=self._to_wire(messages),
                stream=False,
            )
        except OpenAIError as exc:  # network / auth / rate-limit / bad request
            raise LLMError(f"LLM upstream error: {exc}") from exc
        return resp.choices[0].message.content or ""

    def stream(self, messages: Sequence[LLMMessage]) -> Iterator[str]:
        try:
            stream = self._client.chat.completions.create(
                model=self._model,
                messages=self._to_wire(messages),
                stream=True,
            )
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except OpenAIError as exc:
            # The caller persists whatever was yielded before this point.
            raise LLMError(f"LLM upstream error: {exc}") from exc

    def health_check(self) -> None:
        # Cheapest auth + connectivity probe that spends no tokens: list models.
        try:
            self._client.models.list()
        except OpenAIError as exc:
            raise LLMError(f"LLM upstream error: {exc}") from exc

    @staticmethod
    def _to_wire(messages: Sequence[LLMMessage]) -> list[dict[str, str]]:
        return [{"role": m.role.value, "content": m.content} for m in messages]
