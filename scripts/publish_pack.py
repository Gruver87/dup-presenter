"""Publication Pack generator for DUP Presenter.

Generates ready-to-paste release/upload artifacts from deck_resolved.json:
- out/<slug>_chapters.txt   (YouTube-compliant 00:00 chapter timestamps)
- out/<slug>_post_copy.md   (TikTok/Shorts <=150-char caption + YouTube description + hashtags)
- out/<slug>_linkedin.md    (LinkedIn post + first comment, checked against 3,000 / 1,250 character limits)
- out/<slug>_metadata.json  (structured manifest with sha256, duration, voice_used, chapters, QA)

Usage:
    python scripts/publish_pack.py src/generated/deck_resolved.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from linkedin_copy import build_linkedin_copy, render_linkedin_md

ROOT = Path(__file__).resolve().parent.parent

# CC BY and CC BY-SA require attribution regardless of commercial use. CC0 / PDM do not.
CREDIT_LICENCES = frozenset({"by", "by-sa"})


def visual_credit_lines(
    slug: str,
    plan_path: Path | None = None,
    assets_meta_path: Path | None = None,
) -> list[str]:
    """Attribution lines for CC BY / CC BY-SA visuals from the sourcing plan and DnD asset metadata.

    Reads:
      1. work/visual_sources/<slug>/plan.json (CLI visual sourcing)
      2. work/<slug>/assets_meta.json (console drag-and-drop / archive search uploads)
    Deduplicated by (title, page_url). CC0 / PDM / own assets are not listed.
    """
    from visual_sourcing import LICENCE_LABEL, plan_path_for

    lines: list[str] = []
    seen: set[tuple[str, str]] = set()

    def _add(asset: dict) -> None:
        if not asset or asset.get("license") not in CREDIT_LICENCES:
            return
        title = str(asset.get("title") or asset.get("file") or "Untitled").strip()
        creator = str(asset.get("creator") or "Unknown").strip()
        page_url = str(asset.get("page_url") or "").strip()
        key = (title, page_url)
        if key in seen:
            return
        seen.add(key)
        label = LICENCE_LABEL.get(asset["license"], asset["license"])
        licence_url = asset.get("license_url") or "no licence URL"
        src_part = f" — source: {page_url}" if page_url else ""
        lines.append(f'- "{title}" by {creator} — {label} — {licence_url}{src_part}')

    path = plan_path or plan_path_for(slug)
    if path.is_file():
        plan = json.loads(path.read_text(encoding="utf-8"))
        for scene in plan.get("scenes", []):
            _add(scene.get("asset") or {})

    meta_p = assets_meta_path if assets_meta_path is not None else (ROOT / "work" / slug / "assets_meta.json")
    if meta_p.is_file():
        meta_map = json.loads(meta_p.read_text(encoding="utf-8"))
        if isinstance(meta_map, dict):
            for rec in meta_map.values():
                if isinstance(rec, dict):
                    _add(rec)
    return lines


def _fmt_chapter_ts(sec: float) -> str:
    total = max(0, int(round(sec)))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_publish_pack(
    resolved: dict,
    mp4_path: Path | None = None,
    qa_report: dict | None = None,
    out_dir: Path | None = None,
) -> dict[str, Path]:
    """Write chapters.txt, post_copy.md, and metadata.json into out_dir."""
    dest = out_dir or (ROOT / "out")
    dest.mkdir(parents=True, exist_ok=True)
    slug = str(resolved["slug"])
    lang = str(resolved.get("lang") or (resolved.get("voice") or {}).get("lang") or "ru")
    slides = resolved.get("slides") or []

    # 1. YouTube chapters (first chapter MUST be 00:00)
    chapters: list[dict] = []
    running = 0.0
    for idx, s in enumerate(slides):
        start_s = 0.0 if idx == 0 else float(s.get("start_sec", running))
        title = " ".join(str(s.get("title") or s.get("tag") or s.get("id")).split())
        chapters.append({
            "time": _fmt_chapter_ts(start_s),
            "start_sec": round(start_s, 2),
            "id": s.get("id"),
            "title": title,
        })
        running = start_s + float(s.get("duration_sec") or 0.0)

    chapters_txt = "\n".join(f"{c['time']} {c['title']}" for c in chapters) + "\n"
    chapters_path = dest / f"{slug}_chapters.txt"
    chapters_path.write_text(chapters_txt, encoding="utf-8")

    # 2. Social & YouTube post copy
    hero = slides[0] if slides else {}
    outro = slides[-1] if slides else {}
    headline = " ".join(str(hero.get("title") or resolved.get("brand") or slug).split())
    subtitle = " ".join(str(hero.get("subtitle") or "").split())
    url = str(outro.get("url") or "").strip()

    if lang == "ru":
        disclaimer = "Не является финансовым советом."
        short_base = f"{headline} — {subtitle}" if subtitle else headline
        short_caption = (short_base[: 147 - len(disclaimer)] + " " + disclaimer).strip()
        tags = "#DUP #Python #Rust #DevTools #Tech"
        desc_hdr = "## Описание (YouTube / GitHub)"
        chap_hdr = "### Главы"
        short_hdr = "## Короткая подпись (TikTok / Reels / Shorts, <=150 симв.)"
    else:
        disclaimer = "Not financial advice."
        short_base = f"{headline} — {subtitle}" if subtitle else headline
        short_caption = (short_base[: 147 - len(disclaimer)] + " " + disclaimer).strip()
        tags = "#DUP #Python #Rust #DevTools #Engineering"
        desc_hdr = "## Description (YouTube / GitHub)"
        chap_hdr = "### Chapters"
        short_hdr = "## Short Caption (TikTok / Reels / Shorts, <=150 chars)"

    md_lines = [
        f"# Publish Pack — `{slug}`",
        "",
        short_hdr,
        "",
        short_caption[:150],
        "",
        desc_hdr,
        "",
        f"**{headline}**",
        "",
    ]
    if subtitle:
        md_lines += [subtitle, ""]
    if url:
        full_url = url if url.startswith("http") else f"https://{url}"
        md_lines += [f"Repository: {full_url}", ""]
    credit_lines = visual_credit_lines(slug)
    if credit_lines:
        credits_hdr = "## Источники визуалов" if lang == "ru" else "## Visual credits"
        md_lines += [credits_hdr, ""] + credit_lines + [""]
    md_lines += [chap_hdr, "", "```text", chapters_txt.strip(), "```", "", tags, "", disclaimer, ""]

    copy_path = dest / f"{slug}_post_copy.md"
    copy_path.write_text("\n".join(md_lines), encoding="utf-8")

    # 2b. LinkedIn post + first comment, checked against LinkedIn's character limits (see linkedin_copy).
    linkedin = build_linkedin_copy(resolved, chapters=chapters, qa_report=qa_report)
    linkedin_path = dest / f"{slug}_linkedin.md"
    linkedin_path.write_text(render_linkedin_md(slug, linkedin), encoding="utf-8")
    if linkedin["errors"]:
        print(f"[WARN] LinkedIn copy over limit ({'; '.join(linkedin['errors'])}) -> {linkedin_path.name}")

    # 3. Structured metadata.json
    meta: dict = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "slug": slug,
        "brand": resolved.get("brand"),
        "lang": lang,
        "aspect": resolved.get("aspect", "16:9"),
        "width": resolved.get("width"),
        "height": resolved.get("height"),
        "fps": resolved.get("fps", 30),
        "total_seconds": resolved.get("total_seconds"),
        "voice_used": resolved.get("voice_used"),
        "transition_style": resolved.get("transition_style"),
        "transition_frames": resolved.get("transition_frames"),
        "sfx_enabled": resolved.get("sfx_enabled"),
        "chapters": chapters,
        "short_caption": short_caption[:150],
        "linkedin": {
            "post_chars": linkedin["post_chars"],
            "comment_chars": linkedin["comment_chars"],
            "errors": linkedin["errors"],
        },
    }
    if mp4_path and mp4_path.is_file():
        meta["mp4"] = {
            "file": mp4_path.name,
            "bytes": mp4_path.stat().st_size,
            "sha256": _sha256_file(mp4_path),
        }
    if qa_report is not None:
        meta["qa"] = qa_report

    meta_path = dest / f"{slug}_metadata.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "chapters": chapters_path,
        "post_copy": copy_path,
        "linkedin": linkedin_path,
        "metadata": meta_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="DUP Presenter Publish Pack generator")
    parser.add_argument("resolved", help="Path to deck_resolved.json")
    parser.add_argument("--mp4", default="", help="Optional MP4 path to include size + sha256")
    args = parser.parse_args()

    rp = Path(args.resolved)
    if not rp.is_absolute():
        rp = ROOT / rp
    if not rp.is_file():
        print(f"[ERROR] resolved JSON not found: {rp}", file=sys.stderr)
        return 2
    resolved = json.loads(rp.read_text(encoding="utf-8"))
    mp4 = Path(args.mp4) if args.mp4 else (ROOT / "out" / f"{resolved['slug']}.mp4")
    files = build_publish_pack(resolved, mp4_path=mp4 if mp4.is_file() else None)
    for k, v in files.items():
        print(f"[pack] {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
