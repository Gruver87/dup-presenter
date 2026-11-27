"""Automatic narration pacing (pipeline item 5). Pure math, no TTS imports.

Problem: every deck used to hand-tune `voice.rate` (and `playback_rate`) so RU and EN narration sounded
neither too fast nor too slow. Now a deck may declare a target pace:

    "pacing": {"target_wpm": 150, "tolerance": 0.04, "min_rate_pct": 70, "max_rate_pct": 110}

For each plain-text slide the builder measures words-per-minute on the synthesized audio and, if it is
outside the tolerance, re-synthesizes that slide with a corrected rate (bounded passes, clamped range).
The rate actually used is recorded per slide in the resolved deck, so the result is auditable.

Slides with `voice_ssml` fix their own prosody rate, so pacing does not override them; they are reported.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_PASSES = 2  # one correction plus one refinement; more passes add cost without measurable gain
_RATE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*%\s*$")


class PacingError(ValueError):
    """Invalid pacing configuration or rate string (fail-closed)."""


@dataclass(frozen=True)
class PacingSpec:
    target_wpm: float
    tolerance: float
    min_rate_pct: float
    max_rate_pct: float


def parse_pacing(cfg: object) -> PacingSpec | None:
    """Return a validated PacingSpec, or None when the deck does not opt in."""
    if cfg is None:
        return None
    if not isinstance(cfg, dict):
        raise PacingError("pacing must be an object")
    try:
        target = float(cfg["target_wpm"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PacingError("pacing.target_wpm is required and must be a number") from exc
    if not 60.0 <= target <= 260.0:
        raise PacingError(f"pacing.target_wpm must be within 60..260, got {target:g}")
    tol = float(cfg.get("tolerance", 0.04))
    if not 0.005 <= tol <= 0.25:
        raise PacingError(f"pacing.tolerance must be within 0.005..0.25, got {tol:g}")
    lo = float(cfg.get("min_rate_pct", 70))
    hi = float(cfg.get("max_rate_pct", 110))
    if not 30.0 <= lo < hi <= 200.0:
        raise PacingError(f"pacing rate bounds must satisfy 30 <= min < max <= 200, got {lo:g}..{hi:g}")
    return PacingSpec(target_wpm=target, tolerance=tol, min_rate_pct=lo, max_rate_pct=hi)


def rate_pct(rate: str) -> float:
    """Parse a deck rate string such as '86%' into 86.0."""
    m = _RATE_RE.match(str(rate))
    if not m:
        raise PacingError(f"voice rate must look like '86%', got {rate!r}")
    return float(m.group(1))


def format_rate(pct: float) -> str:
    return f"{round(pct):d}%"


def words_per_minute(text: str, dur_sec: float) -> float:
    """Words per minute of narration. Zero duration is an error, not a silent 0 wpm."""
    if dur_sec <= 0:
        raise PacingError("cannot measure pace of a zero-length clip")
    words = len(text.split())
    return words * 60.0 / dur_sec


def next_rate(current_pct: float, measured_wpm: float, spec: PacingSpec) -> float | None:
    """Corrected rate in percent, or None when the slide is within tolerance or already at a bound.

    Speech rate is proportional to the TTS rate, so the corrected rate scales by target/measured.
    """
    if measured_wpm <= 0:
        raise PacingError("measured wpm must be positive")
    ratio = spec.target_wpm / measured_wpm
    if abs(ratio - 1.0) <= spec.tolerance:
        return None
    proposed = current_pct * ratio
    clamped = min(max(proposed, spec.min_rate_pct), spec.max_rate_pct)
    if abs(clamped - current_pct) < 0.5:
        return None  # already at the allowed bound in the needed direction
    return round(clamped, 1)
