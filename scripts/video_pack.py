"""DUP Presenter — Multi-Format Video Pack Builder (Phase D).

Builds a coordinated multi-format release pack from a single source deck:
  - Primary 16:9 video (`build_deck.py --render`)
  - Optional 9:16 vertical Short (`make_cutdown.py` + `build_deck.py --render`)
  - Optional translated sibling deck (`translate_deck.py` + `build_deck.py --render`)
  - Optional 1280x720 clickable cover (`thumbnail_studio.py`)
  - Unified fail-closed manifest: `out/<slug>_pack_manifest.json`
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from build_deck import validate_deck  # noqa: E402
from director_presets import apply_director_preset  # noqa: E402
from idea_engine import critique_deck  # noqa: E402
from make_cutdown import build_short_cutdown  # noqa: E402
from thumbnail_studio import build_thumbnail_props, render_thumbnail  # noqa: E402


class VideoPackError(RuntimeError):
    """Fail-closed error raised when pack planning or execution fails."""


def pack_cli_args(
    deck_path: Path | str,
    *,
    include_short: bool = True,
    include_thumbnail: bool = True,
    translate_to: str = "",
    overwrite: bool = False,
) -> list[str]:
    """Return argv (after the script path) for a `video_pack.py` run.

    Overwrite is opt-in only: an existing MP4 is never replaced unless `overwrite=True`.
    """
    args = [str(deck_path)]
    if overwrite:
        args.append("--overwrite")
    if not include_short:
        args.append("--no-short")
    if not include_thumbnail:
        args.append("--no-thumbnail")
    if translate_to in {"ru", "en"}:
        args.extend(["--translate-to", translate_to])
    return args


def plan_video_pack(
    deck_path: Path,
    *,
    include_short: bool = True,
    include_thumbnail: bool = True,
    translate_to: str = "",
    preset: str = "",
    overwrite: bool = False,
) -> dict[str, Any]:
    """Validate source deck and return an explicit multi-format build plan."""
    dp = deck_path.resolve()
    if not dp.is_file():
        raise VideoPackError(f"Source deck not found: {dp}")
    deck = json.loads(dp.read_text(encoding="utf-8"))
    if preset:
        deck = apply_director_preset(deck, preset)
    validate_deck(deck)

    slug = str(deck["slug"])
    lang = str(deck.get("lang") or "ru")
    if translate_to and translate_to not in {"ru", "en"}:
        raise VideoPackError(f"Unsupported --translate-to {translate_to!r}; expected 'ru' or 'en'")
    if translate_to == lang:
        raise VideoPackError(f"Source deck is already in lang={lang!r}; cannot translate to the same language")

    targets: list[dict[str, Any]] = [
        {
            "role": "primary",
            "slug": slug,
            "aspect": deck.get("aspect", "16:9"),
            "lang": lang,
            "deck": str(dp),
            "mp4": str(ROOT / "out" / f"{slug}.mp4"),
            "qa": str(ROOT / "out" / f"{slug}_qa.json"),
        }
    ]

    if include_short:
        short_slug = f"{slug}-short"
        targets.append(
            {
                "role": "short_9x16",
                "slug": short_slug,
                "aspect": "9:16",
                "lang": lang,
                "preset": "fast_shorts",
                "deck": str(ROOT / "decks" / f"{short_slug}.json"),
                "mp4": str(ROOT / "out" / f"{short_slug}.mp4"),
                "qa": str(ROOT / "out" / f"{short_slug}_qa.json"),
            }
        )

    if translate_to:
        tr_slug = f"{slug}-{translate_to}"
        targets.append(
            {
                "role": f"translated_{translate_to}",
                "slug": tr_slug,
                "aspect": deck.get("aspect", "16:9"),
                "lang": translate_to,
                "deck": str(ROOT / "decks" / f"{tr_slug}.json"),
                "mp4": str(ROOT / "out" / f"{tr_slug}.mp4"),
                "qa": str(ROOT / "out" / f"{tr_slug}_qa.json"),
            }
        )

    cover = None
    if include_thumbnail:
        cover = {
            "role": "thumbnail_1280x720",
            "out": str(ROOT / "out" / f"{slug}_cover.png"),
            "props": build_thumbnail_props(deck=deck),
        }

    preflight = critique_deck(deck)
    est_minutes = round(len(targets) * max(1.5, len(deck.get("slides") or []) * 0.45), 1)

    return {
        "ok": True,
        "source_deck": str(dp),
        "slug": slug,
        "preset": preset or None,
        "overwrite": overwrite,
        "preflight": {
            "director_score": preflight["score"],
            "add": preflight["add"],
            "remove": preflight["remove"],
            "upgrade": preflight["upgrade"],
            "estimated_render_minutes": est_minutes,
        },
        "targets": targets,
        "thumbnail": cover,
        "manifest_path": str(ROOT / "out" / f"{slug}_pack_manifest.json"),
    }


def _run_step(cmd: list[str], label: str) -> None:
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise VideoPackError(f"Step {label!r} failed (exit {proc.returncode}): {proc.stderr[-400:] or proc.stdout[-400:]}")


def execute_video_pack(plan: dict[str, Any]) -> dict[str, Any]:
    """Execute a validated pack plan and write out/<slug>_pack_manifest.json."""
    overwrite = bool(plan.get("overwrite"))
    src_deck = json.loads(Path(plan["source_deck"]).read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []
    total_hard_fails = 0

    for tgt in plan["targets"]:
        role = tgt["role"]
        deck_file = Path(tgt["deck"])

        if role == "short_9x16":
            short_deck = build_short_cutdown(src_deck, max_slides=4)
            short_preset = str(tgt.get("preset") or "fast_shorts")
            short_deck = apply_director_preset(short_deck, short_preset, override_existing=True)
            deck_file.write_text(json.dumps(short_deck, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        elif role.startswith("translated_"):
            target_lang = tgt["lang"]
            _run_step(
                [sys.executable, str(ROOT / "scripts" / "translate_deck.py"), plan["source_deck"], "--to", target_lang],
                f"translate_{target_lang}",
            )

        # Video Pack publishes master MP4s: every target must be storyboard-approved (fail-closed).
        cmd = [sys.executable, str(ROOT / "scripts" / "build_deck.py"), str(deck_file), "--render", "--require-storyboard"]
        if overwrite:
            cmd.append("--overwrite")
        _run_step(cmd, f"render_{tgt['slug']}")

        qa_path = Path(tgt["qa"])
        if not qa_path.is_file():
            raise VideoPackError(f"Expected Media QA report missing after render: {qa_path}")
        qa = json.loads(qa_path.read_text(encoding="utf-8"))
        hf = int(qa.get("hard_fails", 1))
        total_hard_fails += hf
        results.append(
            {
                "role": role,
                "slug": tgt["slug"],
                "mp4": tgt["mp4"],
                "qa_ok": bool(qa.get("ok")) and hf == 0,
                "hard_fails": hf,
                "integrated_lufs": (qa.get("audio") or {}).get("integrated_lufs"),
            }
        )

    thumb_result = None
    if plan.get("thumbnail"):
        th = plan["thumbnail"]
        thumb_result = render_thumbnail(Path(th["out"]), th["props"], dry_run=False)

    manifest = {
        "ok": total_hard_fails == 0 and all(r["qa_ok"] for r in results),
        "slug": plan["slug"],
        "hard_fails": total_hard_fails,
        "artifacts": results,
        "thumbnail": thumb_result,
    }
    m_path = Path(plan["manifest_path"])
    m_path.parent.mkdir(parents=True, exist_ok=True)
    m_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not manifest["ok"]:
        raise VideoPackError(f"Video pack completed with hard_fails={total_hard_fails}")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DUP Presenter Multi-Format Video Pack Builder")
    parser.add_argument("deck", help="Path to source deck JSON")
    parser.add_argument("--no-short", action="store_true", help="Skip 9:16 vertical Short cutdown")
    parser.add_argument("--no-thumbnail", action="store_true", help="Skip 1280x720 cover render")
    parser.add_argument("--translate-to", choices=["", "ru", "en"], default="", help="Also build translated deck")
    parser.add_argument("--preset", default="", help="Optional director preset ID")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing MP4s")
    parser.add_argument("--plan-only", action="store_true", help="Validate and print pack plan without rendering")
    args = parser.parse_args(argv)

    try:
        plan = plan_video_pack(
            Path(args.deck),
            include_short=not args.no_short,
            include_thumbnail=not args.no_thumbnail,
            translate_to=args.translate_to,
            preset=args.preset,
            overwrite=args.overwrite,
        )
        if args.plan_only:
            print(json.dumps(plan, ensure_ascii=False, indent=2))
            return 0
        manifest = execute_video_pack(plan)
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
