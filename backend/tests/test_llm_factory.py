"""`get_llm_provider` selection: mock, groq fail-fast on missing key, unknown."""
from __future__ import annotations

import pytest

from app.infrastructure.config import Settings
from app.infrastructure.llm import get_llm_provider
from app.infrastructure.llm.mock import MockLLMProvider


def test_mock_provider_selected_by_default():
    assert isinstance(get_llm_provider(Settings(llm_provider="mock")), MockLLMProvider)


def test_groq_without_api_key_fails_fast():
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        get_llm_provider(Settings(llm_provider="groq", groq_api_key=None))


def test_groq_with_key_builds_adapter():
    # No network call is made at construction time; just verify wiring.
    from app.infrastructure.llm.groq import GroqProvider

    provider = get_llm_provider(Settings(llm_provider="groq", groq_api_key="test-key"))
    assert isinstance(provider, GroqProvider)


def test_unknown_provider_rejected():
    with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
        get_llm_provider(Settings(llm_provider="nope"))
