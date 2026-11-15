"""Singleton Whisper service — one model instance for the entire process."""
from __future__ import annotations

import asyncio
import io
import logging
import os
import tempfile
import threading

import soundfile as sf

logger = logging.getLogger(__name__)

_MODEL_SIZE   = "base"
_DEVICE       = "cpu"
_COMPUTE_TYPE = "int8"
_BEAM_SIZE    = 5

# WHICH LANGUAGE (2026-10-12). Free auto-detection is wrong for this app: the
# base model hears spoken Urdu as Hindi about half the time (measured: Urdu
# clips scored hi 0.54-0.93 against ur 0.07-0.44), and on accented or noisy
# speech it picks English -- whose decoder then writes the Urdu speech out as
# ENGLISH text. Output is therefore only ever Urdu (Urdu script) or English:
#   "ur" / "en"  -- the client chose; transcribed in that language
#   "auto"       -- Urdu-family speech (ur, hi, pa, sd) vs English, by summed
#                   probability; Hindi is never an output (it is Devanagari)
OUTPUT_LANGUAGES = ("ur", "en")
_URDU_FAMILY = ("ur", "hi", "pa", "sd")

# Primes the Urdu decoder towards legal vocabulary and Urdu spelling (measured:
# "قبضہ" and "حصہ" instead of "کبسا" / "اسہ"). Paired with the VAD filter, so
# silence is dropped rather than "transcribed" into the prompt's own words.
_URDU_PROMPT = ("یہ ایک قانونی معاملہ ہے۔ جائیداد، پلاٹ، قبضہ، حصہ، وراثت، خلع، طلاق، "
                "نان نفقہ، ایف آئی آر، ضمانت، عدالت، وکیل۔")

_GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
_GROQ_TIMEOUT = 60.0


class GroqUnavailable(Exception):
    """Groq could not transcribe this audio; the caller falls back to local."""


def _groq_keys() -> list[str]:
    from app.core.config import settings
    return [k for k in (settings.groq_api_key, settings.groq_api_key_2) if k]


async def _groq_call(audio_bytes: bytes, filename: str, fields: dict) -> dict:
    """One transcription request; tries the second key on a 429."""
    import httpx

    from app.core.config import settings

    keys = _groq_keys()
    if not keys:
        raise GroqUnavailable("no key")
    last = "no response"
    async with httpx.AsyncClient(timeout=_GROQ_TIMEOUT) as client:
        for key in keys:
            try:
                res = await client.post(
                    _GROQ_URL, headers={"Authorization": f"Bearer {key}"},
                    data={"model": settings.voice_groq_model, "temperature": "0", **fields},
                    files={"file": (filename, audio_bytes)},
                )
            except httpx.HTTPError as exc:
                raise GroqUnavailable(exc.__class__.__name__) from exc
            if res.status_code == 200:
                return res.json()
            last = f"http {res.status_code}"
            if res.status_code != 429:
                break
    raise GroqUnavailable(last)


async def transcribe_with_groq(audio_bytes: bytes, filename: str, language: str) -> dict:
    """Same contract as `WhisperService.transcribe`, on Groq's whisper-large-v3.

    "auto" asks Groq to detect, and anything that is not English is
    transcribed again as Urdu -- the same rule as the local path, so Hindi
    (Devanagari) is never an output.
    """
    lang = language if language in OUTPUT_LANGUAGES else None
    if lang is None:
        detected = await _groq_call(audio_bytes, filename, {"response_format": "verbose_json"})
        if str(detected.get("language") or "").strip().lower() in ("english", "en"):
            return {"transcript": str(detected.get("text") or "").strip(), "language": "en",
                    "language_name": "English", "language_probability": None}
        lang = "ur"
    fields = {"response_format": "json", "language": lang}
    if lang == "ur":
        fields["prompt"] = _URDU_PROMPT
    out = await _groq_call(audio_bytes, filename, fields)
    return {"transcript": str(out.get("text") or "").strip(), "language": lang,
            "language_name": _LANG_NAMES.get(lang, lang.upper()), "language_probability": None}


# ISO 639-1 codes relevant to Pakistani users
_LANG_NAMES: dict[str, str] = {
    "ur": "Urdu",
    "en": "English",
    "pa": "Punjabi",
    "sd": "Sindhi",
    "ps": "Pashto",
    "hi": "Hindi",
    "ar": "Arabic",
    "fa": "Persian",
}


class WhisperService:
    """Thread-safe singleton that holds the loaded WhisperModel."""

    _instance: WhisperService | None = None
    _lock = threading.Lock()   # guards model init (sync / thread-pool context)
    _model = None

    # ── Singleton ──────────────────────────────────────────────────────────────
    def __new__(cls) -> WhisperService:
        if cls._instance is None:
            inst = super().__new__(cls)
            inst._alock = asyncio.Lock()   # serialises inference (async / event-loop context)
            cls._instance = inst
        return cls._instance

    # ── Lazy model property ────────────────────────────────────────────────────
    @property
    def model(self):
        """Auto-loads on first access (thread-safe via _lock)."""
        if self._model is None:
            self.load()
        return self._model

    # ── Lifecycle ──────────────────────────────────────────────────────────────
    def load(self) -> None:
        """Load model into memory (idempotent, thread-safe)."""
        with self._lock:
            if self._model is not None:
                return
            logger.info("Loading Whisper '%s' on %s …", _MODEL_SIZE, _DEVICE)
            from faster_whisper import WhisperModel
            self._model = WhisperModel(_MODEL_SIZE, device=_DEVICE, compute_type=_COMPUTE_TYPE)
            logger.info("Whisper model ready.")

    async def warmup(self) -> None:
        """Fire-and-forget preload — call once from FastAPI lifespan."""
        asyncio.create_task(asyncio.to_thread(self.load))

    # ── Audio decoding ─────────────────────────────────────────────────────────
    def _decode(self, audio_bytes: bytes, filename: str) -> tuple:
        """
        Decode audio bytes into a source faster-whisper can consume.

        Returns (source, tmp_path):
          source    — float32 numpy array (soundfile) or str file path (ffmpeg fallback)
          tmp_path  — path to delete after inference, or None when source is an array
        """
        try:
            data, _sr = sf.read(io.BytesIO(audio_bytes), dtype="float32")
            array = data.mean(axis=1) if data.ndim > 1 else data
            return array, None
        except Exception:
            pass

        # Fallback: temp file for ffmpeg-backed formats (webm / ogg / mp4)
        suffix = os.path.splitext(filename)[1] or ".webm"
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        try:
            tmp.write(audio_bytes)
            tmp.flush()
        finally:
            tmp.close()
        return tmp.name, tmp.name

    # ── Transcription (sync — runs in thread pool) ─────────────────────────────
    def _choose_language(self, audio, language: str) -> tuple[str, float | None]:
        """("ur" | "en", detection confidence or None when the client chose)."""
        if language in OUTPUT_LANGUAGES:
            return language, None
        _lang, _p, all_probs = self.model.detect_language(audio)
        probs = dict(all_probs or [])
        urdu = sum(probs.get(code, 0.0) for code in _URDU_FAMILY)
        english = probs.get("en", 0.0)
        # Pakistani speech that is neither clearly Urdu-family nor English
        # (Pashto, Sindhi accents, noise) is still far likelier to be Urdu.
        if english > urdu:
            return "en", round(english / max(urdu + english, 1e-9), 3)
        return "ur", round(urdu / max(urdu + english, 1e-9), 3)

    def transcribe(self, audio_bytes: bytes, filename: str = "audio.wav", language: str = "auto") -> dict:
        """
        Transcribe raw audio bytes (blocking — call via transcribe_async).

        Returns:
          transcript           — full text string
          language             — ISO 639-1 code   (e.g. "ur", "en")
          language_name        — display name     (e.g. "Urdu", "English")
          language_probability — detection confidence 0–1, or None when the
                                 client chose the language
        """
        from faster_whisper.audio import decode_audio

        source, tmp_path = self._decode(audio_bytes, filename)
        try:
            audio = decode_audio(source, sampling_rate=16000) if isinstance(source, str) else source
            lang, confidence = self._choose_language(audio, language)
            segments, _info = self.model.transcribe(
                audio, language=lang, task="transcribe", beam_size=_BEAM_SIZE,
                initial_prompt=_URDU_PROMPT if lang == "ur" else None,
                vad_filter=True,
            )
            transcript = " ".join(seg.text.strip() for seg in segments).strip()
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        return {
            "transcript": transcript,
            "language": lang,
            "language_name": _LANG_NAMES.get(lang, lang.upper()),
            "language_probability": confidence,
        }

    # ── Transcription (async — use this from route handlers) ──────────────────
    async def transcribe_async(self, audio_bytes: bytes, filename: str = "audio.wav", language: str = "auto") -> dict:
        """
        Queue-protected transcription for concurrent HTTP requests.

        _alock serialises inference so CPU is never saturated by parallel calls.
        Callers await in line — no request is dropped, no OOM from parallel models.
        """
        from app.core.config import settings

        # Groq first (more accurate on Urdu); the local model whenever Groq
        # cannot answer -- offline, rate-limited, a provider error. Voice input
        # must not stop working because a free tier ran out.
        if settings.voice_provider == "groq" and _groq_keys():
            try:
                return await transcribe_with_groq(audio_bytes, filename, language)
            except GroqUnavailable as exc:
                logger.warning("voice: Groq transcription unavailable (%s) — using the local model", exc)
            except Exception as exc:  # noqa: BLE001 -- any provider surprise falls back
                logger.warning("voice: Groq transcription failed (%s) — using the local model",
                               exc.__class__.__name__)
        async with self._alock:
            return await asyncio.to_thread(self.transcribe, audio_bytes, filename, language)


# Module-level singleton — import this everywhere
whisper_service = WhisperService()
