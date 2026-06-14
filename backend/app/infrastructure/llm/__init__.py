"""LLM provider selection.

`get_llm_provider` returns the configured `LLMProvider` implementation: the
deterministic offline mock, or the real Groq adapter (PLAN §3.5). The Groq adapter
is imported lazily so a mock-only deployment never needs the `openai` dependency
loaded, and a missing API key fails fast rather than erroring mid-stream.
"""
from __future__ import annotations

from app.domain.ports import LLMProvider
from app.infrastructure.config import Settings
from app.infrastructure.llm.mock import MockLLMProvider


def get_llm_provider(settings: Settings) -> LLMProvider:
    provider = settings.llm_provider.lower()
    if provider == "mock":
        return MockLLMProvider()
    if provider == "groq":
        if not settings.groq_api_key:
            raise RuntimeError(
                "LLM_PROVIDER=groq requires GROQ_API_KEY to be set "
                "(use LLM_PROVIDER=mock for an offline demo)."
            )
        from app.infrastructure.llm.groq import GroqProvider

        return GroqProvider(
            api_key=settings.groq_api_key,
            base_url=settings.groq_base_url,
            model=settings.llm_model,
        )
    raise ValueError(
        f"Unknown LLM_PROVIDER={settings.llm_provider!r} (expected 'mock' or 'groq')"
    )
