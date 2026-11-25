"""DUP Presenter — TTS engine registry (fail-closed, no silent fallback).

Engines:
  - Silero v5 RU  (speakers: eugene, xenia, aidar, baya, kseniya)      -> torch package, SSML
  - Silero v3 EN  (speakers: en_0 ... en_21)                           -> torch package, SSML (legacy)
  - Kokoro-82M v1.0 EN (speakers: af_bella, am_michael, ...)           -> kokoro-onnx, plain text
    Apache-2.0 model. Weights: models/kokoro/kokoro-v1.0.onnx + voices-v1.0.bin
    (https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.0)

Engine is selected by speaker id, so a deck never needs a separate engine flag.
If a selected engine's files are missing, synthesis FAILS instead of switching voices.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
KOKORO_DIR = ROOT / "models" / "kokoro"
KOKORO_MODEL = KOKORO_DIR / "kokoro-v1.0.onnx"
KOKORO_VOICES = KOKORO_DIR / "voices-v1.0.bin"
KOKORO_NATIVE_SR = 24000

# Curated Kokoro English voices (all ids verified against voices-v1.0.bin).
KOKORO_VOICE_CATALOG: list[dict[str, str]] = [
    {"id": "am_michael", "label": "Michael — male, neutral (рекомендуется)", "gender": "male"},
    {"id": "af_bella", "label": "Bella — female, warm (рекомендуется)", "gender": "female"},
    {"id": "am_adam", "label": "Adam — male, deep", "gender": "male"},
    {"id": "af_sarah", "label": "Sarah — female, clear", "gender": "female"},
    {"id": "bm_george", "label": "George — male, British", "gender": "male"},
    {"id": "bf_emma", "label": "Emma — female, British", "gender": "female"},
    {"id": "am_fenrir", "label": "Fenrir — male, energetic", "gender": "male"},
    {"id": "af_heart", "label": "Heart — female, expressive", "gender": "female"},
]
KOKORO_VOICE_IDS: frozenset[str] = frozenset(v["id"] for v in KOKORO_VOICE_CATALOG)
KOKORO_DEFAULT = "am_michael"
KOKORO_PARTNERS = {
    "am_michael": "af_bella",
    "af_bella": "am_michael",
    "am_adam": "af_sarah",
    "af_sarah": "am_adam",
    "bm_george": "bf_emma",
    "bf_emma": "bm_george",
    "am_fenrir": "af_heart",
    "af_heart": "am_fenrir",
}

SILERO_EN_VOICE_IDS: frozenset[str] = frozenset({"en_0", "en_1", "en_2", "en_3", "en_5", "en_10", "en_18", "en_21"})


class TTSEngineError(RuntimeError):
    """A TTS engine is unavailable or produced unusable audio."""


def speaker_lang(speaker: str) -> str:
    """Map a speaker id to its language code (ru | en)."""
    s = str(speaker or "")
    if s in KOKORO_VOICE_IDS or s in SILERO_EN_VOICE_IDS or s.startswith("en_"):
        return "en"
    return "ru"


def speaker_engine(speaker: str) -> str:
    """Return the engine id that must synthesize this speaker."""
    s = str(speaker or "")
    if s in KOKORO_VOICE_IDS:
        return "kokoro_v1"
    if s in SILERO_EN_VOICE_IDS or s.startswith("en_"):
        return "silero_v3_en"
    return "silero_v5_ru"


def rate_to_speed(rate: str) -> float:
    """Convert a rate string like '95%' into Kokoro speed (0.95)."""
    raw = str(rate or "100%").strip()
    try:
        if raw.endswith("%"):
            value = float(raw[:-1]) / 100.0
        else:
            value = float(raw)
    except ValueError as exc:
        raise TTSEngineError(f"Invalid rate {rate!r}") from exc
    if not 0.5 <= value <= 1.5:
        raise TTSEngineError(f"Rate {rate!r} is outside the supported range 50%..150%")
    return value


def _resample_to(x: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    from math import gcd

    from scipy.signal import resample_poly

    if src_sr == dst_sr:
        return x.astype(np.float32)
    g = gcd(src_sr, dst_sr)
    return resample_poly(x.astype(np.float64), dst_sr // g, src_sr // g).astype(np.float32)


class KokoroEngine:
    """Lazy-loaded Kokoro-82M ONNX engine. Raises TTSEngineError when weights are missing."""

    def __init__(self) -> None:
        self._model = None

    def _load(self):
        if self._model is not None:
            return self._model
        missing = [str(p) for p in (KOKORO_MODEL, KOKORO_VOICES) if not p.is_file()]
        if missing:
            raise TTSEngineError(
                "Kokoro weights missing: " + ", ".join(missing)
                + ". Download from https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.0"
            )
        try:
            from kokoro_onnx import Kokoro
        except ImportError as exc:
            raise TTSEngineError("kokoro-onnx is not installed: pip install kokoro-onnx") from exc
        self._model = Kokoro(str(KOKORO_MODEL), str(KOKORO_VOICES))
        return self._model

    def synth(self, text: str, voice: str, rate: str, sr: int) -> np.ndarray:
        """Return mono float32 audio at `sr` Hz for plain English text."""
        if voice not in KOKORO_VOICE_IDS:
            raise TTSEngineError(f"Unknown Kokoro voice {voice!r}")
        clean = " ".join(str(text or "").split())
        if not clean:
            raise TTSEngineError("Empty text for Kokoro")
        model = self._load()
        samples, got_sr = model.create(clean, voice=voice, speed=rate_to_speed(rate), lang="en-us")
        if int(got_sr) != KOKORO_NATIVE_SR:
            raise TTSEngineError(f"Kokoro returned {got_sr} Hz, expected {KOKORO_NATIVE_SR} Hz")
        audio = np.asarray(samples, dtype=np.float32).reshape(-1)
        if audio.size == 0 or not np.isfinite(audio).all():
            raise TTSEngineError(f"Kokoro produced invalid audio for voice {voice!r}")
        return _resample_to(audio, KOKORO_NATIVE_SR, sr)
