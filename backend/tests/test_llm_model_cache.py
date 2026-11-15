"""Chat models are built once and reused (2026-10-12): building a Groq client
cost ~1.5 s and the chain was rebuilt on every call."""
from app.ai import llm as llm_mod


def test_a_model_is_built_once_and_a_swapped_builder_is_honoured(monkeypatch):
    built = []

    def builder(model):
        built.append(model)
        return object()

    monkeypatch.setattr(llm_mod, "_BUILDERS", {**llm_mod._BUILDERS, "groq": builder})
    a = llm_mod._built_model("groq", "m1")
    b = llm_mod._built_model("groq", "m1")
    assert a is b and built == ["m1"]

    def other(model):
        return "other"
    monkeypatch.setattr(llm_mod, "_BUILDERS", {**llm_mod._BUILDERS, "groq": other})
    assert llm_mod._built_model("groq", "m1") == "other", "a stale cached model outlived its builder"
