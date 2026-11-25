"""Pre-render diagnostics for DUP Presenter decks (fail-closed).

`diagnose_deck` never renders anything. It reports:
- errors (render must not start): schema violations, Cyrillic text in an English deck,
  missing screenshot/music assets, and an output MP4 that a render would overwrite
  (only when `overwrite=False`);
- warnings (render may proceed): estimated length and render time;
- estimates: duration from deck or word count, and render time from observed runs.

Render-time estimate is a heuristic calibrated on our own builds (about 18 rendered
frames per second on the reference workstation). It is guidance, not a guarantee.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DIR = ROOT / "public"
MUSIC_DIR = ROOT / "assets" / "music"
OUT_DIR = ROOT / "out"

CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
# Observed on the reference build machine: ~5334 frames took ~5 minutes of Remotion render.
RENDER_SEC_PER_FRAME = 0.055
# Speech length per slide = a + b * words(voice). Least-squares fit on 31 slides from our build logs
# (en: 19 slides, ru: 12 slides; mean abs error ~1.5 s). Refit with scripts/calibrate_speech.py when voices change.
VOICE_FIT = {"en": (-1.50, 0.514), "ru": (-1.73, 0.558)}
LONG_VIDEO_WARN_SEC = 240.0
TAG_RE = re.compile(r"<[^>]+>")


class DeckDoctorError(Exception):
    """Raised when a deck cannot be inspected at all (unreadable or not a JSON object)."""


def _slide_text(slide: dict) -> str:
    parts: list[str] = []
    for key in ("title", "subtitle", "tag", "tagline", "url", "voice_text"):
        if slide.get(key):
            parts.append(str(slide[key]))
    for b in slide.get("bullets") or []:
        parts.append(str(b.get("title", "")))
        parts.append(str(b.get("desc", "")))
    for k in slide.get("kpis") or []:
        parts.append(str(k.get("label", "")))
    for c in slide.get("captions") or []:
        parts.append(str(c.get("text", "")))
    return " ".join(parts)


def _voice_words(slide: dict) -> int:
    """Words the TTS will speak. Only narration decides speech length; on-screen text is not spoken."""
    text = slide.get("voice_text") or TAG_RE.sub(" ", str(slide.get("voice_ssml") or ""))
    if not text.strip():
        # Dialogue or unknown shape: fall back to all slide text so the estimate never silently drops to zero.
        text = _slide_text(slide)
    return len(text.split())


def estimate_speech_sec(words: int, lang: str) -> float:
    """Modelled TTS length of a slide's narration, from the fitted line for the deck language."""
    a, b = VOICE_FIT.get(lang, VOICE_FIT["en"])
    return max(1.0, a + b * words)


def _estimate_slide_sec(slide: dict, probe_media: Callable[[Path], float], lang: str = "en") -> float:
    """Slide length guess. Same rule as build_deck: slide = ceil(speech) + 1 s; a `ui_recording` slide is at least its clip + 1 s."""
    if isinstance(slide.get("duration_sec"), (int, float)) and slide["duration_sec"] > 0:
        base = float(slide["duration_sec"])
    else:
        base = float(math.ceil(estimate_speech_sec(_voice_words(slide), lang)) + 1)
    if slide.get("type") == "ui_recording":
        src = str((slide.get("recording") or {}).get("src", ""))
        if src:
            clip_sec = probe_media(PUBLIC_DIR / src)
            base = max(base, float(math.ceil(clip_sec) + 1))
    return round(base, 2)


def diagnose_deck(deck: dict, *, overwrite: bool = False, check_assets: bool = True) -> dict:
    """Return {"ok", "errors", "warnings", "estimates"} for a deck dict.

    `ok` is False when there is any error. Callers must refuse to render in that case.

    `check_assets=False` skips file-presence checks (screenshots, music, clip lengths) so that
    schema, language, theme and output checks can run on a clean machine (CI). It adds a warning,
    so a report without assets is never mistaken for a render-ready one.
    """
    if not isinstance(deck, dict):
        raise DeckDoctorError("deck must be a JSON object")

    from build_deck import (  # noqa: E402  (lazy: avoids circular import)
        ALLOWED_THEMES,
        DeckValidationError,
        _media_duration_sec,
        deck_lang,
        validate_deck,
    )

    errors: list[str] = []
    warnings: list[str] = []

    try:
        validate_deck(deck, check_assets=check_assets)
    except Exception as exc:  # DeckValidationError and friends: report, do not crash
        errors.append(f"schema: {exc}")
        return {"ok": False, "errors": errors, "warnings": warnings, "estimates": {}}

    lang = deck_lang(deck)
    slides = deck.get("slides") or []

    if lang == "en":
        for s in slides:
            hits = CYRILLIC_RE.findall(_slide_text(s))
            if hits:
                errors.append(f"slide {s.get('id')}: Cyrillic text in English deck ({hits[:3]})")

    if deck.get("theme") and deck["theme"] not in ALLOWED_THEMES:
        errors.append(f"unknown theme {deck['theme']!r}")

    if not check_assets:
        warnings.append("assets not checked (check_assets=false): screenshots, music and clip lengths are not verified")

    for s in slides:
        for scr in s.get("screens") or []:
            src = str(scr.get("src", ""))
            if check_assets and not (PUBLIC_DIR / src).is_file():
                errors.append(f"slide {s.get('id')}: screenshot not found: public/{src}")

    music = deck.get("music") or {}
    if music.get("enabled") and check_assets:
        if music.get("file"):
            chosen = MUSIC_DIR / Path(str(music["file"])).name
            if not chosen.is_file():
                errors.append(f"music file not found: assets/music/{chosen.name}")
        elif not any(p.is_file() for p in MUSIC_DIR.glob("*")):
            errors.append("music enabled but assets/music is empty")

    slide_secs: list[float] = []
    # Without assets the clip length is unknown: 0.0 leaves the word-based estimate in place.
    probe_media = _media_duration_sec if check_assets else (lambda _p: 0.0)
    for s in slides:
        try:
            slide_secs.append(_estimate_slide_sec(s, probe_media, lang))
        except DeckValidationError as exc:
            errors.append(f"slide {s.get('id')}: {exc}")
    total_sec = round(sum(slide_secs), 2)
    fps = int(deck.get("fps") or 30)
    frames = int(round(total_sec * fps))
    est_render_sec = round(frames * RENDER_SEC_PER_FRAME, 1)

    if total_sec > LONG_VIDEO_WARN_SEC:
        warnings.append(f"estimated length {total_sec:.0f}s is longer than {LONG_VIDEO_WARN_SEC:.0f}s; check retention")

    slug = str(deck.get("slug") or "")
    out_mp4 = OUT_DIR / f"{slug}.mp4"
    if out_mp4.exists():
        msg = f"out/{slug}.mp4 already exists"
        if overwrite:
            warnings.append(msg + " and will be overwritten (overwrite=true)")
        else:
            errors.append(msg + "; refusing to overwrite (pass overwrite=true or use a new slug)")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "estimates": {
            "slides": len(slides),
            "estimated_length_sec": total_sec,
            "frames": frames,
            "estimated_render_sec": est_render_sec,
            "estimate_basis": "deck duration_sec when set, else fitted speech length from narration words (ceil+1 s, as build_deck); ui_recording at least clip+1 s; render ~0.055 s/frame (our builds)",
        },
    }


def load_and_diagnose(path: "Path | str", *, overwrite: bool = False) -> dict:
    """Load a deck file and run diagnose_deck, turning read/parse failures into errors."""
    deck_path = Path(path)
    try:
        deck = json.loads(deck_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "errors": [f"cannot read deck {deck_path}: {exc}"], "warnings": [], "estimates": {}}
    return diagnose_deck(deck, overwrite=overwrite)

