"""Markdown -> deck JSON importer (fail-closed).

Lets a presenter write a talk as plain text instead of hand-writing deck JSON.

Format:

    ---
    slug: my-talk
    lang: en
    theme: cosmic_radar
    caption_style: karaoke
    ---
    ## [hero_3d] Title of the slide
    tag: OVERVIEW
    subtitle: Optional subtitle
    voice: Narration for this slide. It can continue
    on the next line until the next key, bullet or heading.

    ## [kpi] Numbers
    voice: Narration.
    - 4488 :: instruments
    - 0 :: float money in the ledger

Supported slide types: hero_3d, outro_3d (keys: tag, subtitle, url, tagline), kpi and timeline
(bullets as `- value :: label` for kpi, `- title :: description` for timeline). Other types need
assets or code symbols and must be written as JSON. Anything unknown is refused with its line number.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

FRONT_KEYS = {"slug", "lang", "theme", "aspect", "caption_style", "burn_captions"}
SLIDE_KEYS = {"tag", "subtitle", "url", "tagline"}
MD_SLIDE_TYPES = {"hero_3d", "outro_3d", "kpi", "timeline"}
HEADING_RE = re.compile(r"^## \[([a-z0-9_]+)\]\s+(.+?)\s*$")
KEY_RE = re.compile(r"^([a-z_]+):\s*(.*)$")
BULLET_RE = re.compile(r"^- (.+?) :: (.+?)\s*$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")

DEFAULT_VOICE = {
    "en": {"engine": "kokoro_v1", "lang": "en", "speaker": "am_michael", "rate": "95%", "ambient_volume": 0.12, "mode": "single"},
    "ru": {
        "engine": "edge_tts",
        "lang": "ru",
        "speaker": "dmitry",
        "rate": "95%",
        "ambient_volume": 0.16,
        "mode": "single",
        "fallback_speaker": "eugene",
    },
}


class MarkdownDeckError(Exception):
    """Raised when the Markdown source cannot be converted safely; carries the line number when known."""


def _fail(lineno: int | None, msg: str) -> MarkdownDeckError:
    where = f"line {lineno}: " if lineno is not None else ""
    return MarkdownDeckError(where + msg)


def _parse_front_matter(lines: list[str]) -> tuple[dict, int]:
    """Return (front matter values, index of the first line after it)."""
    if not lines or lines[0].strip() != "---":
        raise _fail(1, "file must start with a '---' front matter block (slug, lang, ...)")
    values: dict = {}
    for i in range(1, len(lines)):
        raw = lines[i].rstrip("\n")
        if raw.strip() == "---":
            return values, i + 1
        if not raw.strip():
            continue
        m = KEY_RE.match(raw.strip())
        if not m:
            raise _fail(i + 1, f"invalid front matter line {raw!r}")
        key, val = m.group(1), m.group(2).strip()
        if key not in FRONT_KEYS:
            raise _fail(i + 1, f"unknown front matter key {key!r}; allowed: {sorted(FRONT_KEYS)}")
        if key in values:
            raise _fail(i + 1, f"duplicate front matter key {key!r}")
        values[key] = val
    raise _fail(None, "front matter is not closed by '---'")


def _to_bool(value: str, lineno: int) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    raise _fail(lineno, f"burn_captions must be true or false, got {value!r}")


def parse_markdown_deck(text: str) -> dict:
    """Convert Markdown text into a deck dict. Raises MarkdownDeckError on anything it cannot map exactly."""
    lines = text.splitlines()
    front, body_start = _parse_front_matter(lines)

    slug = front.get("slug", "")
    if not SLUG_RE.fullmatch(slug):
        raise _fail(None, f"slug must match {SLUG_RE.pattern}, got {slug!r}")
    lang = front.get("lang", "en")
    if lang not in DEFAULT_VOICE:
        raise _fail(None, f"lang must be one of {sorted(DEFAULT_VOICE)}, got {lang!r}")

    deck: dict = {
        "slug": slug,
        "lang": lang,
        "theme": front.get("theme", "neon_cyber"),
        "aspect": front.get("aspect", "16:9"),
        "fps": 30,
        "width": 1920,
        "height": 1080,
        "brand": "DUP LABS",
        "burn_captions": True,
        "voice": dict(DEFAULT_VOICE[lang]),
        "music": {"enabled": False},
        "background": {"enabled": False, "provider": "pixabay"},
        "slides": [],
    }
    if "caption_style" in front:
        deck["caption_style"] = front["caption_style"]
    if "burn_captions" in front:
        deck["burn_captions"] = _to_bool(front["burn_captions"], 1)

    current: dict | None = None
    voice_open = False
    slide_lineno = 0

    def close_current() -> None:
        nonlocal current
        if current is None:
            return
        if not current.get("voice_text", "").strip():
            raise _fail(slide_lineno, f"slide {current['id']} has no 'voice:' narration")
        deck["slides"].append(current)
        current = None

    for idx in range(body_start, len(lines)):
        lineno = idx + 1
        raw = lines[idx].rstrip()
        stripped = raw.strip()

        if stripped.startswith("## "):
            close_current()
            m = HEADING_RE.match(stripped)
            if not m:
                raise _fail(lineno, f"slide heading must look like '## [type] Title', got {stripped!r}")
            stype, title = m.group(1), m.group(2)
            if stype not in MD_SLIDE_TYPES:
                raise _fail(lineno, f"type {stype!r} is not supported in Markdown; allowed: {sorted(MD_SLIDE_TYPES)}")
            current = {"id": f"s{len(deck['slides']) + 1}", "type": stype, "title": title}
            slide_lineno = lineno
            voice_open = False
            continue

        if current is None:
            if stripped:
                raise _fail(lineno, "text before the first slide heading is not allowed")
            continue

        if not stripped:
            voice_open = False
            continue

        m_bullet = BULLET_RE.match(stripped)
        if m_bullet:
            voice_open = False
            a, b = m_bullet.group(1).strip(), m_bullet.group(2).strip()
            if current["type"] == "kpi":
                current.setdefault("kpis", []).append({"value": a, "label": b})
            elif current["type"] == "timeline":
                current.setdefault("bullets", []).append({"title": a, "desc": b})
            else:
                raise _fail(lineno, f"bullets are not used by {current['type']} slides")
            continue

        m_key = KEY_RE.match(stripped)
        if m_key and (m_key.group(1) in SLIDE_KEYS or m_key.group(1) == "voice"):
            key, val = m_key.group(1), m_key.group(2).strip()
            if key == "voice":
                current["voice_text"] = val
                voice_open = True
                continue
            if key in current:
                raise _fail(lineno, f"duplicate key {key!r} in slide {current['id']}")
            if key not in SLIDE_KEYS:
                raise _fail(lineno, f"key {key!r} not allowed here")
            if key == "url" and not val:
                raise _fail(lineno, "url must not be empty")
            current[key] = val
            voice_open = False
            continue

        if stripped.startswith("- "):
            raise _fail(lineno, f"bullet must be '- a :: b', got {stripped!r}")

        if voice_open:
            current["voice_text"] = (current.get("voice_text", "") + " " + stripped).strip()
            continue

        raise _fail(lineno, f"unrecognised line {stripped!r}; use 'key: value', 'voice:' or '- a :: b'")

    close_current()
    if not deck["slides"]:
        raise _fail(None, "no slides found; add at least one '## [type] Title' section")
    return deck


def convert_file(src: Path, out: Path | None = None, *, overwrite: bool = False) -> dict:
    """Parse, validate fail-closed (schema only; assets are checked at render time), then write the deck JSON.

    `out` defaults to decks/<slug>.json.
    """
    from build_deck import DeckValidationError, validate_deck

    if not src.is_file():
        raise MarkdownDeckError(f"source file not found: {src}")
    deck = parse_markdown_deck(src.read_text(encoding="utf-8"))
    try:
        validate_deck(deck, check_assets=False)
    except DeckValidationError as exc:
        raise MarkdownDeckError(f"deck schema: {exc}") from exc
    if out is None:
        out = ROOT / "decks" / f"{deck['slug']}.json"
    if out.exists() and not overwrite:
        raise MarkdownDeckError(f"{out} already exists; pass --overwrite to replace it")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(deck, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return deck


DECK_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
MAX_MARKDOWN_BYTES = 300_000


class MarkdownImportError(MarkdownDeckError):
    """Text-based import refused (size, slug or schema). Callers map this to a client error."""


class MarkdownDeckExists(MarkdownImportError):
    """The target deck file already exists; the caller should map this to a conflict."""


def write_deck_from_markdown(text: str, decks_dir: Path, *, overwrite: bool = False) -> dict:
    """Parse Markdown text, validate fail-closed, and write decks/<slug>.json. Used by the console import.

    Refuses oversized input, unsafe slugs, schema errors and overwriting an existing deck unless asked.
    Returns the written deck dict; its path is decks_dir / f"{deck['slug']}.json".
    """
    from build_deck import DeckValidationError, validate_deck

    if len(text.encode("utf-8")) > MAX_MARKDOWN_BYTES:
        raise MarkdownImportError(f"Markdown is larger than {MAX_MARKDOWN_BYTES // 1000} KB")
    deck = parse_markdown_deck(text)
    slug = str(deck.get("slug", ""))
    if not DECK_SLUG_RE.match(slug):
        raise MarkdownImportError(f"unsafe or empty slug {slug!r} (use letters, digits, '_' or '-')")
    try:
        validate_deck(deck, check_assets=False)
    except DeckValidationError as exc:
        raise MarkdownImportError(f"deck schema: {exc}") from exc
    out = decks_dir / f"{slug}.json"
    if out.exists() and not overwrite:
        raise MarkdownDeckExists(f"deck {slug!r} already exists; change the slug in the front matter")
    decks_dir.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(deck, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return deck


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Convert a Markdown talk into a DUP Presenter deck JSON (fail-closed)")
    parser.add_argument("source", help="Markdown file")
    parser.add_argument("-o", "--out", default="", help="Output deck JSON (default: decks/<slug>.json)")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    src = Path(args.source)
    out = Path(args.out) if args.out else None
    try:
        deck = convert_file(src, out, overwrite=args.overwrite)
    except MarkdownDeckError as exc:
        print(f"[md] REFUSED: {exc}", file=sys.stderr)
        return 2
    target = out or ROOT / "decks" / f"{deck['slug']}.json"
    print(f"[md] wrote {target} ({len(deck['slides'])} slides)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
