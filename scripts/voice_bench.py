"""Russian TTS bench: same deck text through several engines, saved as WAV for listening
and scored with faster-whisper (word recall proxy, NOT a listening test).

Engines: Silero v5 RU (local), Piper ru_RU medium (local, models/piper), Edge TTS (online).
Outputs: out/voice_bench/<engine>.wav and out/voice_bench/summary.json.
"""

from __future__ import annotations

import asyncio
import difflib
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import av  # noqa: E402
import build_deck as bd  # noqa: E402
import plan_deck as pd  # noqa: E402
from ru_speech import normalize_ru_ssml  # noqa: E402

OUT_DIR = ROOT / "out" / "voice_bench"
OUT_SR = 24000
PAUSE_SEC = 0.4
ASR_MODEL = "small"
PIPER_VOICES = ["denis", "dmitri", "irina", "ruslan"]
EDGE_VOICES = {"edge_dmitry": "ru-RU-DmitryNeural", "edge_svetlana": "ru-RU-SvetlanaNeural"}
SILERO_SPEAKERS = ["aidar", "eugene"]


def words(text: str) -> list[str]:
    return re.findall(r"[а-яa-z]+", text.lower().replace("ё", "е"))


def decode_to_mono(path: Path, rate: int) -> np.ndarray:
    container = av.open(str(path))
    stream = container.streams.audio[0]
    resampler = av.AudioResampler(format="flt", layout="mono", rate=rate)
    parts: list[np.ndarray] = []
    for frame in container.decode(stream):
        for out in resampler.resample(frame):
            parts.append(out.to_ndarray().reshape(-1))
    for out in resampler.resample(None):
        parts.append(out.to_ndarray().reshape(-1))
    container.close()
    return np.concatenate(parts).astype(np.float32)


def silero_slide(vs: bd.VoiceSynth, speaker: str, text: str) -> np.ndarray:
    audio = bd.postprocess_voice(vs.synth(speaker, text, pd.voice_ssml(text, rate="95%")))
    return resample_poly(np.asarray(audio, dtype=np.float32), OUT_SR, bd.SR).astype(np.float32)


def piper_slide(voice, text: str) -> np.ndarray:
    parts: list[np.ndarray] = []
    sr = None
    for chunk in voice.synthesize(text):
        sr = chunk.sample_rate
        arr = getattr(chunk, "audio_int16_array", None)
        if arr is None:
            arr = np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16)
        parts.append(np.asarray(arr, dtype=np.float32) / 32768.0)
    x = np.concatenate(parts)
    return resample_poly(x, OUT_SR, sr).astype(np.float32)


async def edge_slide(voice_name: str, text: str, tmp: Path) -> np.ndarray:
    import aiohttp.connector
    import aiohttp.resolver
    import edge_tts

    from edge_engine import require_edge_egress

    require_edge_egress(text)

    # aiodns (c-ares) cannot reach DNS on this host; use the system resolver instead.
    aiohttp.connector.DefaultResolver = aiohttp.resolver.ThreadedResolver
    await edge_tts.Communicate(text, voice_name, rate="-5%").save(str(tmp))
    return decode_to_mono(tmp, OUT_SR)


def join(slides: list[np.ndarray]) -> np.ndarray:
    gap = np.zeros(int(PAUSE_SEC * OUT_SR), dtype=np.float32)
    pieces: list[np.ndarray] = []
    for i, s in enumerate(slides):
        if i:
            pieces.append(gap)
        pieces.append(s)
    return np.concatenate(pieces)


def save_wav(path: Path, x: np.ndarray) -> None:
    wavfile.write(str(path), OUT_SR, (np.clip(x, -1.0, 1.0) * 32767).astype(np.int16))


def score(asr, x: np.ndarray, expected: list[str]) -> tuple[float, str]:
    x16 = resample_poly(x, 16000, OUT_SR).astype(np.float32)
    segs, _ = asr.transcribe(x16, language="ru", beam_size=5)
    hyp = " ".join(s.text for s in segs)
    hw = set(words(hyp))
    hits = sum(1 for w in expected if w in hw or difflib.get_close_matches(w, list(hw), n=1, cutoff=0.8))
    return hits / max(1, len(expected)), hyp


def main() -> None:
    from faster_whisper import WhisperModel

    deck = json.load(open(ROOT / "decks" / "radar-newtypes.json", encoding="utf-8"))
    texts = [s["voice_text"] for s in deck["slides"]]
    expected = [w for t in texts for w in words(re.sub(r"<[^>]+>|&[#\w]+;", " ", normalize_ru_ssml(t)))]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    asr = WhisperModel(ASR_MODEL, device="cpu", compute_type="int8")

    results: dict[str, dict] = {}

    def record(name: str, slides: list[np.ndarray], gen_sec: float) -> None:
        x = join(slides)
        save_wav(OUT_DIR / f"{name}.wav", x)
        rec, hyp = score(asr, x, expected)
        results[name] = {
            "recall": round(rec, 3),
            "duration_sec": round(len(x) / OUT_SR, 1),
            "gen_sec": round(gen_sec, 1),
            "hyp_head": hyp[:140],
        }
        print(f"{name:22} recall={rec:.3f} dur={len(x) / OUT_SR:6.1f}s gen={gen_sec:6.1f}s", flush=True)

    vs = bd.VoiceSynth("95%")
    for spk in SILERO_SPEAKERS:
        t0 = time.time()
        slides = [silero_slide(vs, spk, t) for t in texts]
        record(f"silero_{spk}", slides, time.time() - t0)

    from piper import PiperVoice

    # Piper/Edge take plain text, so apply the same Latin->Cyrillic respelling that VoiceSynth applies for Silero.
    plain = [normalize_ru_ssml(t) for t in texts]

    for v in PIPER_VOICES:
        model_path = ROOT / "models" / "piper" / f"ru_RU-{v}-medium.onnx"
        voice = PiperVoice.load(str(model_path))
        t0 = time.time()
        slides = [piper_slide(voice, t) for t in plain]
        record(f"piper_{v}", slides, time.time() - t0)

    for name, voice_name in EDGE_VOICES.items():
        t0 = time.time()
        slides = []
        for i, t in enumerate(plain):
            tmp = OUT_DIR / f"_{name}_{i}.mp3"
            last_err: Exception | None = None
            for attempt in range(1, 4):
                try:
                    slides.append(asyncio.run(edge_slide(voice_name, t, tmp)))
                    last_err = None
                    break
                except Exception as exc:  # network / service errors are retried, then re-raised
                    last_err = exc
                    print(f"  {name} slide {i + 1} attempt {attempt} failed: {type(exc).__name__}", flush=True)
                    time.sleep(3 * attempt)
            if last_err is not None:
                raise last_err
            tmp.unlink(missing_ok=True)
        record(name, slides, time.time() - t0)

    (OUT_DIR / "summary.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("summary:", OUT_DIR / "summary.json")


if __name__ == "__main__":
    main()
