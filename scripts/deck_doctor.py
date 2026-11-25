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
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DIR = ROOT / "public"
MUSIC_DIR = ROOT / "assets" / "music"
OUT_DIR = ROOT / "out"

CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
# Observed on the reference build machine: ~5334 frames took ~5 minutes of Remotion render.
RENDER_SEC_PER_FRAME = 0.055
# Fallback speech pacing when a slide has no explicit duration_sec.
WORDS_PER_SEC = 2.4
SLIDE_PAD_SEC = 1.5
LONG_VIDEO_WARN_SEC = 240.0


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


def _estimate_slide_sec(slide: dict) -> float:
    if isinstance(slide.get("duration_sec"), (int, float)) and slide["duration_sec"] > 0:
        return float(slide["duration_sec"])
    words = len(_slide_text(slide).split())
    return round(words / WORDS_PER_SEC + SLIDE_PAD_SEC, 2)


def diagnose_deck(deck: dict, *, overwrite: bool = False) -> dict:
    """Return {"ok", "errors", "warnings", "estimates"} for a deck dict.

    `ok` is False when there is any error. Callers must refuse to render in that case.
    """
    if not isinstance(deck, dict):
        raise DeckDoctorError("deck must be a JSON object")

    from build_deck import ALLOWED_THEMES, deck_lang, validate_deck  # noqa: E402  (lazy: avoids circular import)

    errors: list[str] = []
    warnings: list[str] = []

    try:
        validate_deck(deck)
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

    for s in slides:
        for scr in s.get("screens") or []:
            src = str(scr.get("src", ""))
            if not (PUBLIC_DIR / src).is_file():
                errors.append(f"slide {s.get('id')}: screenshot not found: public/{src}")

    music = deck.get("music") or {}
    if music.get("enabled"):
        if music.get("file"):
            chosen = MUSIC_DIR / Path(str(music["file"])).name
            if not chosen.is_file():
                errors.append(f"music file not found: assets/music/{chosen.name}")
        elif not any(p.is_file() for p in MUSIC_DIR.glob("*")):
            errors.append("music enabled but assets/music is empty")

    slide_secs = [_estimate_slide_sec(s) for s in slides]
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
            "estimate_basis": "deck duration_sec when set, else word count; render ~0.055 s/frame (our builds)",
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
