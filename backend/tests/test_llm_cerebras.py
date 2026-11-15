"""Cerebras as a lateral failover after the Groq keys (2026-10-14). Offline:
no request is ever sent; the key used here is a fake.
"""
from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.ai import llm as L

GROQS = ["groq", "groq2", "groq3", "groq4"]
FAKE_KEY = "test-not-a-real-key"


@pytest.fixture(autouse=True)
def _cloud(monkeypatch):
    monkeypatch.setattr(L.settings, "llm_local_only", False)
    monkeypatch.setattr(L.settings, "llm_provider", "")
    L._MODEL_CACHE.clear()
    yield
    L._MODEL_CACHE.clear()


@pytest.mark.parametrize("purpose", [None, "direct_chat", "intake_extraction", "document_drafting", "unknown"])
def test_cerebras_follows_every_groq_key_and_precedes_the_other_families(purpose):
    order = L._provider_order(purpose)
    assert order.index("cerebras") > max(order.index(g) for g in GROQS)
    assert order.index("cerebras") < order.index("gemini") < order.index("openrouter")
    assert order.count("cerebras") == 1


def test_cerebras_serves_the_same_model_family_as_groq():
    assert L._MODELS["cerebras"] == {"main": L.settings.cerebras_model_main,
                                    "fast": L.settings.cerebras_model_fast}
    assert L.settings.cerebras_model_main == "gpt-oss-120b"


def test_without_a_key_cerebras_is_skipped_and_nothing_changes(monkeypatch):
    monkeypatch.setattr(L.settings, "cerebras_api_key", "")
    with pytest.raises(L._ProviderUnavailable):
        L._build_cerebras("gpt-oss-120b")


def test_with_a_key_it_builds_an_openai_compatible_client_without_a_call(monkeypatch):
    monkeypatch.setattr(L.settings, "cerebras_api_key", FAKE_KEY)
    model = L._build_cerebras("gpt-oss-120b")
    assert model.model_name == "gpt-oss-120b"
    assert str(model.openai_api_base).rstrip("/") == "https://api.cerebras.ai/v1"
    assert model.max_tokens == L.MAX_OUTPUT_TOKENS


def test_structured_output_on_cerebras_uses_tool_calling_only(monkeypatch):
    """gpt-oss-120b on Cerebras rejects tools + response_format together."""
    assert L._structured_kwargs("cerebras") == {"method": "function_calling"}
    assert L._structured_kwargs("groq") == {} and L._structured_kwargs("openrouter") == {}

    class Verdict(BaseModel):
        ok: bool

    monkeypatch.setattr(L.settings, "cerebras_api_key", FAKE_KEY)
    bound = L._build_cerebras("gpt-oss-120b").with_structured_output(
        Verdict, **L._structured_kwargs("cerebras"))
    kwargs = bound.first.kwargs if hasattr(bound, "first") else {}
    assert "tools" in kwargs and "response_format" not in kwargs


def test_a_cerebras_failure_falls_over_like_any_openai_compatible_provider():
    import openai
    for exc in (openai.RateLimitError, openai.BadRequestError, openai.APIConnectionError,
                openai.InternalServerError):
        assert exc in L._FAILOVER_EXCEPTIONS
