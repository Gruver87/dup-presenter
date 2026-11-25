"""Online Russian TTS via Microsoft Edge neural voices (edge-tts). Requires network access.

Used as the primary RU voice when the internet is reachable; the deck pipeline falls back to the offline
Silero voice for the WHOLE deck when this engine is unavailable (never mixes voices inside one deck).
"""

from __future__ import annotations

import asyncio
import os
import socket
import tempfile
import time
from pathlib import Path

import numpy as np

EDGE_RU_VOICES = {
    "dmitry": "ru-RU-DmitryNeural",
    "svetlana": "ru-RU-SvetlanaNeural",
}
EDGE_HOST = "speech.platform.bing.com"


class EdgeEngineError(RuntimeError):
    """Online Edge TTS failed; the caller must fall back to an offline voice for the whole deck."""


def edge_available(timeout: float = 4.0) -> bool:
    """True when the Edge TTS service host accepts a TCP connection (cheap pre-flight check)."""
    try:
        with socket.create_connection((EDGE_HOST, 443), timeout=timeout):
            return True
    except OSError:
        return False


def edge_rate(rate: str) -> str:
    """Convert a deck rate such as '95%' into edge-tts relative rate such as '-5%'."""
    raw = str(rate or "100%").strip()
    if not raw.endswith("%"):
        raise EdgeEngineError(f"unsupported rate {rate!r}; expected a percentage like '95%'")
    try:
        pct = int(float(raw[:-1]))
    except ValueError as exc:
        raise EdgeEngineError(f"unsupported rate {rate!r}") from exc
    return f"{pct - 100:+d}%"


def _decode_mp3(path: Path, sr: int) -> np.ndarray:
    import av

    container = av.open(str(path))
    try:
        stream = container.streams.audio[0]
        resampler = av.AudioResampler(format="flt", layout="mono", rate=sr)
        parts: list[np.ndarray] = []
        for frame in container.decode(stream):
            for out in resampler.resample(frame):
                parts.append(out.to_ndarray().reshape(-1))
        for out in resampler.resample(None):
            parts.append(out.to_ndarray().reshape(-1))
    finally:
        container.close()
    if not parts:
        raise EdgeEngineError("Edge TTS returned no decodable audio")
    return np.concatenate(parts).astype(np.float32)


async def _stream_edge(voice: str, text: str, rel_rate: str, out_mp3: Path) -> list[dict]:
    """Stream MP3 audio and capture real SentenceBoundary timings in one Edge TTS request."""
    import edge_tts

    comm = edge_tts.Communicate(text, voice, rate=rel_rate, boundary="SentenceBoundary")
    boundaries: list[dict] = []
    with out_mp3.open("wb") as f:
        async for chunk in comm.stream():
            ctype = chunk.get("type")
            if ctype == "audio":
                data = chunk.get("data")
                if data:
                    f.write(data)
            elif ctype in ("SentenceBoundary", "WordBoundary"):
                # Edge TTS offsets/durations are in 100-nanosecond ticks (1e7 ticks = 1 sec).
                start_s = float(chunk.get("offset", 0)) / 10_000_000.0
                dur_s = float(chunk.get("duration", 0)) / 10_000_000.0
                boundaries.append({
                    "start_sec": round(start_s, 3),
                    "end_sec": round(start_s + dur_s, 3),
                    "text": str(chunk.get("text") or ""),
                })
    return boundaries


def synth_edge_with_timings(
    speaker: str,
    text: str,
    sr: int,
    rate: str = "95%",
    attempts: int = 5,
) -> tuple[np.ndarray, list[dict]]:
    """Synthesize one utterance with Edge neural voice. Returns (mono float32 at sr, sentence boundaries)."""
    voice = EDGE_RU_VOICES.get(speaker)
    if voice is None:
        raise EdgeEngineError(f"unknown Edge speaker {speaker!r}; allowed: {sorted(EDGE_RU_VOICES)}")
    if not text.strip():
        raise EdgeEngineError("empty text for Edge TTS")

    import aiohttp.connector
    import aiohttp.resolver

    # aiodns (c-ares) cannot reach DNS on some Windows hosts; the system resolver works. Process-wide for aiohttp.
    aiohttp.connector.DefaultResolver = aiohttp.resolver.ThreadedResolver
    rel_rate = edge_rate(rate)

    fd, tmp_name = tempfile.mkstemp(suffix=".mp3")
    tmp = Path(tmp_name)
    os.close(fd)
    try:
        last_exc: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                boundaries = asyncio.run(_stream_edge(voice, text, rel_rate, tmp))
                if tmp.stat().st_size == 0:
                    raise EdgeEngineError("Edge TTS wrote an empty file")
                return _decode_mp3(tmp, sr), boundaries
            except Exception as exc:  # network/service errors: retry, then raise EdgeEngineError below
                last_exc = exc
                print(f"[edge] {speaker} attempt {attempt}/{attempts} failed: {type(exc).__name__}: {exc}")
                time.sleep(3 * attempt)
        raise EdgeEngineError(f"Edge TTS failed after {attempts} attempts: {last_exc}") from last_exc
    finally:
        tmp.unlink(missing_ok=True)


def synth_edge(speaker: str, text: str, sr: int, rate: str = "95%", attempts: int = 5) -> np.ndarray:
    """Synthesize one utterance with an Edge neural voice. Returns mono float32 at sr. Raises EdgeEngineError."""
    audio, _ = synth_edge_with_timings(speaker, text, sr, rate=rate, attempts=attempts)
    return audio
