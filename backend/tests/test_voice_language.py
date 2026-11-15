"""Voice transcription is only ever Urdu (Urdu script) or English (2026-10-12).

Free auto-detection heard spoken Urdu as Hindi (Devanagari output) or English
(the Urdu speech written out as English text). The client now chooses, and
"auto" decides between the Urdu family and English only. No model is loaded
here: the decision is tested against a stub's detection probabilities.
"""
from __future__ import annotations

import pytest

from app.services import whisper_service as ws


class _Seg:
    def __init__(self, text):
        self.text = text


class FakeModel:
    def __init__(self, probs):
        self.probs = probs
        self.calls = []

    def detect_language(self, audio):
        top = max(self.probs, key=lambda kv: kv[1])
        return top[0], top[1], self.probs

    def transcribe(self, audio, **kw):
        self.calls.append(kw)
        return iter([_Seg("text")]), None


def _service(monkeypatch, probs):
    svc = ws.WhisperService()
    model = FakeModel(probs)
    monkeypatch.setattr(ws.WhisperService, "_model", model, raising=False)
    monkeypatch.setattr(svc, "_decode", lambda b, f: ([0.0] * 16, None))
    return svc, model


@pytest.mark.parametrize("probs", [
    [("hi", 0.93), ("ur", 0.07)],          # the measured failure: Urdu heard as Hindi
    [("hi", 0.54), ("ur", 0.44), ("en", 0.01)],
    [("pa", 0.6), ("en", 0.3)],
])
def test_urdu_family_speech_is_transcribed_as_urdu(monkeypatch, probs):
    svc, model = _service(monkeypatch, probs)
    out = svc.transcribe(b"x", "a.wav", "auto")
    assert out["language"] == "ur"
    assert model.calls[-1]["language"] == "ur"
    assert model.calls[-1]["task"] == "transcribe", "speech must never be translated"
    assert model.calls[-1]["initial_prompt"], "the Urdu legal prompt was not used"


def test_english_speech_stays_english(monkeypatch):
    svc, model = _service(monkeypatch, [("en", 0.8), ("ur", 0.1), ("hi", 0.05)])
    out = svc.transcribe(b"x", "a.wav", "auto")
    assert out["language"] == "en" and model.calls[-1]["language"] == "en"
    assert model.calls[-1]["initial_prompt"] is None


@pytest.mark.parametrize("chosen", ["ur", "en"])
def test_the_clients_choice_is_used_without_detection(monkeypatch, chosen):
    svc, model = _service(monkeypatch, [("en", 0.99)] if chosen == "ur" else [("hi", 0.99)])
    out = svc.transcribe(b"x", "a.wav", chosen)
    assert out["language"] == chosen and model.calls[-1]["language"] == chosen
    assert out["language_probability"] is None


def test_silence_is_filtered_not_transcribed(monkeypatch):
    svc, model = _service(monkeypatch, [("ur", 0.9)])
    svc.transcribe(b"x", "a.wav", "ur")
    assert model.calls[-1]["vad_filter"] is True


async def test_the_route_refuses_an_unknown_language():
    from httpx import ASGITransport, AsyncClient

    from app.dependencies import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: {"_id": "u", "role": "client"}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            res = await client.post("/api/v1/voice/transcribe", data={"language": "hi"},
                                    files={"audio": ("a.wav", b"RIFF0000", "audio/wav")})
        assert res.status_code == 422
    finally:
        app.dependency_overrides.clear()


# ── Groq first, the local model as the fallback ─────────────────────────────

@pytest.fixture
def groq_on(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "voice_provider", "groq")
    monkeypatch.setattr(settings, "groq_api_key", "k1")
    monkeypatch.setattr(settings, "groq_api_key_2", "k2")
    local = {"n": 0}

    def local_transcribe(self, audio_bytes, filename="a.wav", language="auto"):
        local["n"] += 1
        return {"transcript": "LOCAL", "language": "ur", "language_name": "Urdu", "language_probability": None}
    monkeypatch.setattr(ws.WhisperService, "transcribe", local_transcribe)
    return local


async def test_groq_answers_and_the_local_model_is_not_used(monkeypatch, groq_on):
    calls = []

    async def fake_call(audio, filename, fields):
        calls.append(fields)
        return {"text": " میری بیوی نے خلع کا دعویٰ کیا ہے "}
    monkeypatch.setattr(ws, "_groq_call", fake_call)
    out = await ws.whisper_service.transcribe_async(b"x", "a.wav", "ur")
    assert out["transcript"] == "میری بیوی نے خلع کا دعویٰ کیا ہے" and out["language"] == "ur"
    assert calls[0]["language"] == "ur" and calls[0]["prompt"]
    assert groq_on["n"] == 0


@pytest.mark.parametrize("detected,want,n_calls", [("English", "en", 1), ("Hindi", "ur", 2), ("Urdu", "ur", 2)])
async def test_groq_auto_is_only_ever_urdu_or_english(monkeypatch, groq_on, detected, want, n_calls):
    calls = []

    async def fake_call(audio, filename, fields):
        calls.append(fields)
        if fields.get("response_format") == "verbose_json":
            return {"language": detected, "text": "detected text"}
        return {"text": "urdu text"}
    monkeypatch.setattr(ws, "_groq_call", fake_call)
    out = await ws.whisper_service.transcribe_async(b"x", "a.wav", "auto")
    assert out["language"] == want and len(calls) == n_calls
    if want == "ur":
        assert calls[-1]["language"] == "ur", "non-English speech was not transcribed as Urdu"


async def test_any_groq_failure_falls_back_to_the_local_model(monkeypatch, groq_on):
    async def down(audio, filename, fields):
        raise ws.GroqUnavailable("http 503")
    monkeypatch.setattr(ws, "_groq_call", down)
    out = await ws.whisper_service.transcribe_async(b"x", "a.wav", "ur")
    assert out["transcript"] == "LOCAL" and groq_on["n"] == 1


async def test_local_provider_never_sends_audio_out(monkeypatch, groq_on):
    from app.core.config import settings
    monkeypatch.setattr(settings, "voice_provider", "local")

    async def must_not(*a, **k):
        raise AssertionError("audio was sent to Groq with voice_provider=local")
    monkeypatch.setattr(ws, "_groq_call", must_not)
    out = await ws.whisper_service.transcribe_async(b"x", "a.wav", "ur")
    assert out["transcript"] == "LOCAL"


async def test_a_rate_limited_key_tries_the_second_one(monkeypatch, groq_on):
    import httpx
    used = []

    async def fake_post(self, url, headers=None, data=None, files=None):
        used.append(headers["Authorization"])
        code = 429 if headers["Authorization"].endswith("k1") else 200
        return httpx.Response(code, json={"text": "ok"}, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    out = await ws._groq_call(b"x", "a.wav", {"language": "ur"})
    assert out == {"text": "ok"} and used == ["Bearer k1", "Bearer k2"]
