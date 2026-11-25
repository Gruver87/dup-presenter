"""DUP Presenter — Thumbnail Studio (1280x720 clickable cover generator via Remotion).

Renders standalone high-contrast YouTube/presentation thumbnails from any deck JSON
or custom title/subtitle/theme inputs using the `DupThumbnail` Remotion composition.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from theme_catalog import THEME_IDS  # noqa: E402


class ThumbnailError(RuntimeError):
    """Fail-closed error when thumbnail props or rendering fail."""


def build_thumbnail_props(
    *,
    deck: dict[str, Any] | None = None,
    title: str = "",
    subtitle: str = "",
    kicker: str = "",
    accent_badge: str = "",
    theme: str = "",
    preview_image: str = "",
) -> dict[str, str]:
    """Build validated props for the `DupThumbnail` Remotion composition."""
    first_slide = (deck.get("slides") or [{}])[0] if isinstance(deck, dict) else {}
    final_title = (title or str(first_slide.get("title") or "")).strip()
    if not final_title:
        raise ThumbnailError("Thumbnail title cannot be empty (provide --title or a deck with slides[0].title)")
    final_subtitle = (subtitle or str(first_slide.get("subtitle") or "")).strip()
    final_brand = str((deck or {}).get("brand") or "DUP LABS").strip()
    final_kicker = (kicker or str(first_slide.get("tag") or "DUP PRESENTER")).strip().upper()
    final_theme = (theme or str((deck or {}).get("theme") or "quantum_ledger")).strip()
    if final_theme not in THEME_IDS:
        raise ThumbnailError(f"Unknown theme {final_theme!r}; allowed: {', '.join(THEME_IDS)}")
    if preview_image and ".." in preview_image:
        raise ThumbnailError("preview_image must not contain path traversal ('..')")
    if preview_image and not (ROOT / "public" / preview_image).is_file():
        raise ThumbnailError(f"preview_image not found under public/: {preview_image}")

    badge = accent_badge.strip()
    if not badge:
        lang = str((deck or {}).get("lang") or "ru").upper()
        badge = f"{lang} · 1080P · -16 LUFS"

    return {
        "title": final_title[:72],
        "subtitle": final_subtitle[:140],
        "kicker": final_kicker[:40],
        "accentBadge": badge[:32],
        "brand": final_brand[:28],
        "theme": final_theme,
        "previewImage": preview_image.strip(),
    }


def render_thumbnail(
    out_path: Path,
    props: dict[str, str],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Render `DupThumbnail` to `out_path` via `npx remotion still`."""
    out_resolved = out_path.resolve()
    out_resolved.parent.mkdir(parents=True, exist_ok=True)
    npx = "npx.cmd" if os.name == "nt" else "npx"
    cmd = [
        npx,
        "remotion",
        "still",
        "DupThumbnail",
        str(out_resolved),
        f"--props={json.dumps(props, ensure_ascii=False)}",
    ]
    if dry_run:
        return {"ok": True, "dry_run": True, "out": str(out_resolved), "props": props, "cmd": cmd}

    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0 or not out_resolved.is_file():
        raise ThumbnailError(f"Remotion thumbnail render failed (exit {proc.returncode}): {proc.stderr[-400:]}")
    return {
        "ok": True,
        "out": str(out_resolved),
        "bytes": out_resolved.stat().st_size,
        "props": props,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DUP Presenter Thumbnail Studio (1280x720)")
    parser.add_argument("--deck", default="", help="Optional source deck JSON path")
    parser.add_argument("--title", default="", help="Override thumbnail title")
    parser.add_argument("--subtitle", default="", help="Override thumbnail subtitle")
    parser.add_argument("--kicker", default="", help="Top pill kicker text")
    parser.add_argument("--badge", default="", help="Top-right accent badge")
    parser.add_argument("--theme", default="", help="Theme ID override")
    parser.add_argument("--preview", default="", help="Optional image path relative to public/")
    parser.add_argument("--out", required=True, help="Output PNG path (e.g. out/my-thumb.png)")
    parser.add_argument("--dry-run", action="store_true", help="Validate props and print command without rendering")
    args = parser.parse_args(argv)

    try:
        deck_data = None
        if args.deck:
            dp = Path(args.deck)
            if not dp.is_file():
                raise ThumbnailError(f"Deck file not found: {dp}")
            deck_data = json.loads(dp.read_text(encoding="utf-8"))
        props = build_thumbnail_props(
            deck=deck_data,
            title=args.title,
            subtitle=args.subtitle,
            kicker=args.kicker,
            accent_badge=args.badge,
            theme=args.theme,
            preview_image=args.preview,
        )
        res = render_thumbnail(Path(args.out), props, dry_run=args.dry_run)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    except ThumbnailError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
