"""Per-module primary Groq key, every key as failover (2026-10-13).

No module may be stuck on one exhausted key: every chain holds every Groq key
and OpenRouter (paid) last. Each module group STARTS on its own key so one busy
module does not drain the others' quota. Offline: builders are faked.
"""
from __future__ import annotations

import pytest

from app.ai import llm as L
from app.ai import provider_health

GROQS = {"groq", "groq2", "groq3", "groq4", "groq5"}


@pytest.fixture(autouse=True)
def _cloud(monkeypatch):
    monkeypatch.setattr(L.settings, "llm_local_only", False)
    monkeypatch.setattr(L.settings, "llm_provider", "")


@pytest.mark.parametrize("purpose,first", [
    (provider_health.PURPOSE_DIRECT_CHAT, "groq3"),
    (provider_health.PURPOSE_ANSWER_GENERATION, "groq3"),
    (provider_health.PURPOSE_INTAKE_EXTRACTION, "groq"),
    (provider_health.PURPOSE_INTAKE_GROUNDING, "groq"),
    # drafting starts on the fifth account (2026-10-14)
    (provider_health.PURPOSE_DOCUMENT_DRAFTING, "groq5"),
    (provider_health.PURPOSE_PETITION_DRAFTING, "groq5"),
    (provider_health.PURPOSE_DRAFT_STREAM, "groq5"),
    (provider_health.PURPOSE_PLEADING_URDU, "groq5"),
    (provider_health.PURPOSE_QUERY_EXPANSION, "groq4"),
    (provider_health.PURPOSE_RETRIEVAL_GRADER, "groq4"),
    (provider_health.PURPOSE_UNKNOWN, "groq4"),
])
def test_each_module_starts_on_its_own_key(purpose, first):
    order = L._provider_order(purpose)
    assert [p for p in order if p in GROQS][0] == first


@pytest.mark.parametrize("purpose", [None, "direct_chat", "intake_extraction", "document_drafting", "unknown"])
def test_every_chain_holds_every_key_once_and_paid_openrouter_last(purpose):
    order = L._provider_order(purpose)
    assert sorted(p for p in order if p in GROQS) == sorted(GROQS)
    assert len(order) == len(set(order))
    assert order[-1] == "openrouter"


def test_no_purpose_keeps_the_default_order():
    assert L._provider_order() == L._FALLBACK_ORDER


@pytest.mark.parametrize("preferred", ["gemini", "openrouter", "cerebras", "ollama"])
def test_explicit_provider_runs_first_with_default_fallbacks(monkeypatch, preferred):
    default_order = L._provider_order("direct_chat")
    monkeypatch.setattr(L.settings, "llm_provider", preferred)
    assert L._provider_order("direct_chat") == [
        preferred, *[provider for provider in default_order if provider != preferred],
    ]


def test_local_only_still_never_touches_the_cloud(monkeypatch):
    monkeypatch.setattr(L.settings, "llm_local_only", True)
    assert L._provider_order("direct_chat") == ["ollama"]


def test_an_exhausted_primary_key_falls_over_to_the_others(monkeypatch):
    """The chat key in cooldown: chat must still get a model, from another key."""
    monkeypatch.setattr(L, "_built_model", lambda provider, model: f"{provider}:{model}")
    monkeypatch.setattr(provider_health, "is_eligible", lambda p, m: p not in ("groq3", "gemini"))
    monkeypatch.setattr(provider_health, "cooldown_remaining", lambda p, m: 60.0)
    monkeypatch.setattr(provider_health, "cooldown_reason", lambda p, m: "rate_limit (429)")
    cands = L._candidates("main", "direct_chat")
    assert cands[0].provider == "groq" and "groq3" not in [c.provider for c in cands]


def test_an_unconfigured_key_is_skipped_not_fatal(monkeypatch):
    monkeypatch.setattr(L.settings, "groq_api_key_4", "")
    with pytest.raises(L._ProviderUnavailable):
        L._build_groq4("openai/gpt-oss-120b")
    real = L._built_model

    def built(provider, model):
        if provider == "groq4":
            raise L._ProviderUnavailable("groq4: GROQ_API_KEY_4 is not configured")
        return f"{provider}:{model}"
    monkeypatch.setattr(L, "_built_model", built)
    monkeypatch.setattr(provider_health, "is_eligible", lambda p, m: p != "gemini")
    cands = L._candidates("main", "query_expansion")
    assert "groq4" not in [c.provider for c in cands] and cands[0].provider == "groq"
    assert real is not None


def test_gemini_is_a_free_fallback_after_every_groq_key_and_before_paid_openrouter():
    order = L._provider_order("direct_chat")
    assert order.index("gemini") > max(order.index(g) for g in GROQS)
    assert order.index("gemini") < order.index("openrouter")


def test_gemini_models_come_from_settings():
    assert L._MODELS["gemini"] == {"main": L.settings.gemini_model_main, "fast": L.settings.gemini_model_fast}
    assert "2.0" not in L._MODELS["gemini"]["main"], "gemini-2.x is no longer served to this account"


def test_a_stalled_rest_call_fails_over_instead_of_ending_the_chain():
    import requests
    assert issubclass(requests.exceptions.ReadTimeout, L._FAILOVER_EXCEPTIONS)
    assert issubclass(requests.exceptions.ConnectionError, L._FAILOVER_EXCEPTIONS)


# ── Gemini: declared, graceful when absent, never leaks a key ───────────────

FAKE_KEY = "AIzaFAKE-test-key-0000000000000000000"


def test_the_gemini_runtime_dependency_is_declared_exactly():
    from pathlib import Path
    req = (Path(__file__).resolve().parent.parent / "requirements.txt").read_text(encoding="utf-8")
    pins = [l.split("#")[0].strip() for l in req.splitlines()]
    assert "langchain-google-genai==2.1.12" in pins, "declared, not only commented"


def test_gemini_configured_and_importable_builds_without_a_live_call(monkeypatch):
    monkeypatch.setattr(L.settings, "gemini_api_key", FAKE_KEY)
    model = L._build_gemini("gemini-3.5-flash-lite")
    assert type(model).__name__ == "ChatGoogleGenerativeAI"
    assert FAKE_KEY not in repr(model) and FAKE_KEY not in str(model)


def test_gemini_key_absent_is_unavailable_not_fatal(monkeypatch):
    monkeypatch.setattr(L.settings, "gemini_api_key", "")
    with pytest.raises(L._ProviderUnavailable) as e:
        L._build_gemini("gemini-3.5-flash-lite")
    assert "GEMINI_API_KEY is not configured" in str(e.value)


def test_gemini_package_unavailable_is_unavailable_not_fatal(monkeypatch):
    import sys
    monkeypatch.setattr(L.settings, "gemini_api_key", FAKE_KEY)
    monkeypatch.setitem(sys.modules, "langchain_google_genai", None)
    with pytest.raises(L._ProviderUnavailable) as e:
        L._build_gemini("gemini-3.5-flash-lite")
    assert FAKE_KEY not in str(e.value)


def test_gemini_transient_errors_fall_through():
    from google.api_core import exceptions as g
    for exc in (g.ServiceUnavailable, g.ResourceExhausted, g.DeadlineExceeded):
        assert issubclass(exc, L._FAILOVER_EXCEPTIONS)


def test_an_unconfigured_key_error_names_the_setting_never_a_value(monkeypatch):
    monkeypatch.setattr(L.settings, "groq_api_key_3", "")
    with pytest.raises(L._ProviderUnavailable) as e:
        L._build_groq3("openai/gpt-oss-120b")
    assert str(e.value) == "groq3: GROQ_API_KEY_3 is not configured"


def test_a_built_groq_model_does_not_expose_its_key(monkeypatch):
    monkeypatch.setattr(L.settings, "groq_api_key_4", "gsk_FAKE_" + "x" * 40)
    model = L._build_groq4("openai/gpt-oss-120b")
    assert "gsk_FAKE_" not in repr(model) and "gsk_FAKE_" not in str(model)
