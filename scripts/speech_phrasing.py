"""Phrase-level voice assembly with explicit, measured silences.

Why: Silero RU ignores most punctuation and SSML <break> tags for pauses. The
measured effect on a 14.6 s slide was only 4 pauses >= 150 ms (A/B test), so the
narration read as one unbroken stream. Here each phrase is synthesized on its own
and joined with real digital silence chosen from the punctuation mark that ends it.

Pure functions only (no torch import) so they are unit-testable.
"""

from __future__ import annotations

import re

import numpy as np

# Silence (seconds) appended after a phrase, by the punctuation mark that ends it.
PAUSE_SEC: dict[str, float] = {
    ".": 0.42,
    "!": 0.5,
    "?": 0.5,
    "…": 0.45,
    ";": 0.32,
    ":": 0.32,
    "—": 0.28,
    ",": 0.18,
}
# Pause after a paragraph / hard break with no terminal mark.
DEFAULT_PAUSE_SEC = 0.3

_PHRASE_RE = re.compile(r"[^.!?…;:,—]+[.!?…;:,—]?")


def split_phrases(text: str) -> list[tuple[str, float]]:
    """Split text into (phrase, pause_after_sec) pairs. Empty fragments are dropped."""
    out: list[tuple[str, float]] = []
    for m in _PHRASE_RE.finditer(text.strip()):
        chunk = m.group(0).strip()
        if not chunk:
            continue
        # Keep the terminal mark out of the synthesized text when it is a pure separator.
        mark = chunk[-1] if chunk[-1] in PAUSE_SEC else ""
        body = chunk[:-1].strip() if mark else chunk
        if not body:
            continue
        out.append((body, PAUSE_SEC.get(mark, DEFAULT_PAUSE_SEC)))
    if not out:
        raise ValueError("speech_phrasing: no speakable phrases in text")
    return out


def assemble(
    phrases: list[tuple[str, float]],
    synth_fn,
    sample_rate: int,
    lead_sec: float = 0.12,
    tail_sec: float = 0.25,
) -> np.ndarray:
    """Synthesize each phrase with `synth_fn(text) -> np.ndarray` and join with measured silences.

    `lead_sec` / `tail_sec` pad the slide so speech never starts or ends hard against the cut.
    Returns mono float32 at `sample_rate`.
    """
    parts: list[np.ndarray] = [np.zeros(int(sample_rate * lead_sec), dtype=np.float32)]
    for idx, (text, pause) in enumerate(phrases):
        audio = np.asarray(synth_fn(text), dtype=np.float32).reshape(-1)
        if audio.size == 0:
            raise RuntimeError(f"speech_phrasing: empty synthesis for phrase {idx}: {text[:40]!r}")
        parts.append(audio)
        is_last = idx == len(phrases) - 1
        parts.append(np.zeros(int(sample_rate * (tail_sec if is_last else pause)), dtype=np.float32))
    return np.concatenate(parts)


def pause_profile(audio: np.ndarray, sample_rate: int, floor_db: float = -40.0, min_sec: float = 0.15) -> list[float]:
    """Lengths (s) of silent runs >= min_sec, measured on 20 ms RMS frames. Used by QA and tests."""
    frame = max(1, int(sample_rate * 0.02))
    n = len(audio) // frame
    if n == 0:
        return []
    rms = np.sqrt((audio[: n * frame].reshape(n, frame) ** 2).mean(axis=1) + 1e-12)
    silent = 20 * np.log10(rms + 1e-12) < floor_db
    runs: list[float] = []
    cur = 0
    for s in silent:
        if s:
            cur += 1
        else:
            if cur * 0.02 >= min_sec:
                runs.append(round(cur * 0.02, 3))
            cur = 0
    if cur * 0.02 >= min_sec:
        runs.append(round(cur * 0.02, 3))
    return runs
