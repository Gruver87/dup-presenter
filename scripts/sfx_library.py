"""Named SFX library (Stage 5): deck cues can reference effects by ``name`` instead of a file path.

Every effect is synthesized locally and deterministically (fixed RNG seed, no third-party audio, so
there is no licence to track). Files live in ``public/sfx/library/`` with a manifest that records
sha256 and duration. A cue ``{"name": "impact", "at_sec": 0.4}`` is resolved to
``{"src": "sfx/library/impact.wav", ...}`` before validation and rendering.

Fail-closed: unknown names are refused; a cue must have exactly one of ``src`` or ``name``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

import numpy as np

from audio_fx import SR, _synth_ui_pop, _synth_whoosh, _write_wav_mono

ROOT = Path(__file__).resolve().parent.parent
LIBRARY_DIR = ROOT / "public" / "sfx" / "library"
MANIFEST_PATH = LIBRARY_DIR / "manifest.json"
MANIFEST_SCHEMA = "dup-sfx-library/1"
LIBRARY_REL_PREFIX = "sfx/library"
RNG_SEED = 20260401  # fixed: the same library bytes on every machine


class SfxLibraryError(ValueError):
    """Unknown library name or malformed cue (fail-closed)."""


def _fade(x: np.ndarray, sr: int, fade_in: float = 0.004, fade_out: float = 0.012) -> np.ndarray:
    n = x.shape[0]
    t = np.arange(n) / sr
    env = np.minimum(1.0, t / max(fade_in, 1e-6)) * np.minimum(1.0, (n / sr - t) / max(fade_out, 1e-6))
    return x * np.clip(env, 0.0, 1.0)


def _normalize(x: np.ndarray, peak: float) -> np.ndarray:
    m = float(np.max(np.abs(x))) if x.size else 0.0
    if m <= 0.0:
        raise SfxLibraryError("synthesized an empty/silent effect")
    return (x / m) * peak


def _synth_impact(sr: int, duration: float = 0.9) -> np.ndarray:
    n = int(sr * duration)
    t = np.arange(n) / sr
    freq = 38.0 + 55.0 * np.exp(-t * 4.0)  # pitch drop: the "thud" of a heavy hit
    body = np.sin(2.0 * np.pi * np.cumsum(freq) / sr) * np.exp(-t * 4.0)
    rng = np.random.default_rng(RNG_SEED)
    click = rng.standard_normal(n) * np.exp(-t * 220.0) * 0.6
    return _fade(_normalize(body + click, 0.85), sr)


def _synth_tick(sr: int, duration: float = 0.03) -> np.ndarray:
    n = int(sr * duration)
    t = np.arange(n) / sr
    rng = np.random.default_rng(RNG_SEED + 1)
    tone = np.sin(2.0 * np.pi * 1800.0 * t) * np.exp(-t * 160.0)
    noise = rng.standard_normal(n) * np.exp(-t * 400.0) * 0.3
    return _fade(_normalize(tone + noise, 0.6), sr)


def _synth_riser(sr: int, duration: float = 1.6) -> np.ndarray:
    n = int(sr * duration)
    t = np.arange(n) / sr
    u = t / duration
    freq = 180.0 * (1800.0 / 180.0) ** u  # exponential sweep 180 Hz -> 1.8 kHz
    tone = np.sin(2.0 * np.pi * np.cumsum(freq) / sr)
    rng = np.random.default_rng(RNG_SEED + 2)
    air = rng.standard_normal(n) * 0.15 * (u ** 2)
    return _fade(_normalize((tone * (u ** 2) * 0.6) + air, 0.6), sr)


def _synth_ding(sr: int, duration: float = 1.4) -> np.ndarray:
    n = int(sr * duration)
    t = np.arange(n) / sr
    bell = np.sin(2.0 * np.pi * 880.0 * t) * np.exp(-t * 3.0)
    partial = 0.5 * np.sin(2.0 * np.pi * 1760.0 * t) * np.exp(-t * 5.0)
    return _fade(_normalize(bell + partial, 0.6), sr)


# name -> (synthesizer(sr) -> samples, description)
LIBRARY: dict[str, tuple[Callable[[int], np.ndarray], str]] = {
    "whoosh": (_synth_whoosh, "transition whoosh (same as the built-in transition sound)"),
    "pop": (_synth_ui_pop, "soft UI pop (same as the built-in pop sound)"),
    "impact": (_synth_impact, "low thud with a short transient for hard cuts and reveals"),
    "tick": (_synth_tick, "short high tick for counters, bullets and list steps"),
    "riser": (_synth_riser, "rising sweep that leads into a reveal (use before the slide ends)"),
    "ding": (_synth_ding, "bell chime for a finished point or a KPI reveal"),
}
LIBRARY_NAMES: frozenset[str] = frozenset(LIBRARY)


def library_src(name: str) -> str:
    """Public-relative path of a library effect. Refuses unknown names."""
    if not isinstance(name, str) or name not in LIBRARY:
        raise SfxLibraryError(f"unknown SFX name {name!r}; library: {sorted(LIBRARY_NAMES)}")
    return f"{LIBRARY_REL_PREFIX}/{name}.wav"


def ensure_library(sr: int = SR) -> dict[str, Any]:
    """(Re)generate every library effect and write the manifest. Deterministic: same bytes each run."""
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []
    for name in sorted(LIBRARY):
        synth, description = LIBRARY[name]
        samples = synth(sr)
        path = LIBRARY_DIR / f"{name}.wav"
        _write_wav_mono(path, samples, sr)
        items.append({
            "name": name,
            "src": library_src(name),
            "description": description,
            "duration_sec": round(samples.shape[0] / float(sr), 4),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "origin": "procedural (project-generated, no third-party audio)",
        })
    manifest = {"schema": MANIFEST_SCHEMA, "sample_rate": sr, "items": items}
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def resolve_deck_sfx(deck: dict[str, Any]) -> dict[str, Any]:
    """Resolve every ``name`` cue into a ``src`` path (generates the library once if needed). Mutates ``deck``."""
    names_used: set[str] = set()
    for slide in deck.get("slides") or []:
        for cue in slide.get("sfx") or []:
            if isinstance(cue, dict) and cue.get("name") is not None:
                names_used.add(str(cue["name"]))
    if names_used:
        ensure_library()
    for slide in deck.get("slides") or []:
        for cue in slide.get("sfx") or []:
            if isinstance(cue, dict) and cue.get("name") is not None:
                if cue.get("src") is not None:
                    raise SfxLibraryError("sfx cue must have exactly one of src or name, not both")
                # Replace the name with the resolved path so the validated deck carries one source only.
                cue["src"] = library_src(cue.pop("name"))
    return deck
