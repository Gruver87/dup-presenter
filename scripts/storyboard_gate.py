#!/usr/bin/env python3
"""Storyboard approval gate (Stage 4): draft preview -> storyboard -> human approval -> master MP4.

Fail-closed rules:
- A master render (``build_deck.py --render`` without ``--draft``) that passes
  ``--require-storyboard`` is refused unless ``work/<slug>/storyboard/approval.json`` binds the
  CURRENT deck content (sha256 of canonical JSON) AND the CURRENT draft MP4 (sha256) that a human
  reviewed through a storyboard built from that same draft.
- Any deck edit or any new draft build invalidates a previous approval (hash mismatch).
- The storyboard is only built from a fresh draft (its build record must match the deck and the
  draft file). Approval is never written without a storyboard for the same deck + draft.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = "dup-storyboard/1"
SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
SLIDE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
FRAME_WIDTH = 480
FRAME_OFFSET_CAP_SEC = 2.5  # same frame rule as build_deck --preview-stills
FRAME_OFFSET_RATIO = 0.4
MIN_FRAME_BYTES = 1024

FrameExtractor = Callable[[Path, float, Path], None]


class StoryboardGateError(RuntimeError):
    """Raised when the storyboard gate refuses an action (fail-closed)."""


# --------------------------------------------------------------------------- hashing / io


def deck_fingerprint(deck: dict[str, Any]) -> str:
    """Stable sha256 of the deck content (key order independent)."""
    canonical = json.dumps(deck, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_json(path: Path) -> Any | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StoryboardGateError(f"corrupt record {path.name}: {exc}") from exc


def _save_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


class _Layout:
    """On-disk locations for one deck slug under a repo root."""

    def __init__(self, slug: str, root: Path) -> None:
        s = (slug or "").strip()
        if not SLUG_RE.match(s):
            raise StoryboardGateError(f"invalid slug {slug!r}")
        self.slug = s
        self.root = root
        self.deck_file = root / "decks" / f"{s}.json"
        self.draft_mp4 = root / "out" / f"{s}_draft.mp4"
        self.sb_dir = root / "work" / s / "storyboard"
        self.draft_meta = self.sb_dir / "draft_meta.json"
        self.index = self.sb_dir / "index.json"
        self.approval = self.sb_dir / "approval.json"
        self.plan = root / "work" / "visual_sources" / s / "plan.json"

    def read_deck(self) -> dict[str, Any]:
        if not self.deck_file.is_file():
            raise StoryboardGateError(f"deck not found: decks/{self.slug}.json")
        return json.loads(self.deck_file.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- draft record


def record_draft_build(slug: str, deck_sha256: str, slides: list[dict[str, Any]], *, root: Path = ROOT) -> dict[str, Any]:
    """Bind the freshly rendered draft MP4 to the deck content and slide timings.

    Called by ``build_deck.py --draft`` after a successful render and QA.
    """
    lay = _Layout(slug, root)
    if not lay.draft_mp4.is_file():
        raise StoryboardGateError(f"draft MP4 missing: out/{lay.slug}_draft.mp4")
    clean: list[dict[str, Any]] = []
    for sl in slides:
        sid = str(sl.get("id", ""))
        if not SLIDE_ID_RE.match(sid):
            raise StoryboardGateError(f"invalid slide id for storyboard: {sid!r}")
        dur = float(sl["duration_sec"])
        if dur <= 0:
            raise StoryboardGateError(f"slide {sid}: non-positive duration")
        clean.append({
            "id": sid,
            "type": str(sl.get("type") or ""),
            "title": str(sl.get("title") or ""),
            "start_sec": round(float(sl.get("start_sec", 0.0)), 3),
            "duration_sec": round(dur, 3),
        })
    meta = {
        "schema": SCHEMA,
        "slug": lay.slug,
        "deck_sha256": deck_sha256,
        "draft_mp4_sha256": file_sha256(lay.draft_mp4),
        "built_at": _now(),
        "slides": clean,
    }
    _save_json(lay.draft_meta, meta)
    return meta


# --------------------------------------------------------------------------- status / gate


def gate_status(slug: str, *, root: Path = ROOT, deck_sha256: str | None = None) -> dict[str, Any]:
    """Current gate state. ``can_master`` is True only when every link of the chain matches."""
    lay = _Layout(slug, root)
    fp = deck_sha256 or deck_fingerprint(lay.read_deck())
    draft_exists = lay.draft_mp4.is_file()
    draft_sha = file_sha256(lay.draft_mp4) if draft_exists else None
    st: dict[str, Any] = {
        "slug": lay.slug,
        "deck_sha256": fp,
        "draft_exists": draft_exists,
        "draft_fresh": False,
        "storyboard_ready": False,
        "approved": False,
        "can_master": False,
        "approved_at": None,
        "reason": "",
    }
    meta = _load_json(lay.draft_meta)
    if not draft_exists:
        st["reason"] = "нет черновика: сначала собери черновик (draft)"
    elif meta is None:
        st["reason"] = "у черновика нет записи сборки: пересобери черновик"
    elif meta.get("deck_sha256") != fp or meta.get("draft_mp4_sha256") != draft_sha:
        st["reason"] = "колода изменилась после черновика: пересобери черновик"
    else:
        st["draft_fresh"] = True
        index = _load_json(lay.index)
        if index is None or index.get("deck_sha256") != fp or index.get("draft_mp4_sha256") != draft_sha:
            st["reason"] = "раскадровка отсутствует или устарела: собери раскадровку"
        else:
            st["storyboard_ready"] = True
            approval = _load_json(lay.approval)
            if approval is None or approval.get("deck_sha256") != fp or approval.get("draft_mp4_sha256") != draft_sha:
                st["reason"] = "раскадровка не одобрена: просмотри и одобри"
            else:
                st["approved"] = True
                st["can_master"] = True
                st["approved_at"] = approval.get("approved_at")
    return st


def assert_master_allowed(slug: str, *, root: Path = ROOT, deck_sha256: str | None = None) -> dict[str, Any]:
    st = gate_status(slug, root=root, deck_sha256=deck_sha256)
    if not st["can_master"]:
        raise StoryboardGateError(f"мастер-сборка заблокирована: {st['reason']}")
    return st


def approve(slug: str, *, root: Path = ROOT, approved_by: str = "console") -> dict[str, Any]:
    lay = _Layout(slug, root)
    fp = deck_fingerprint(lay.read_deck())
    st = gate_status(slug, root=root, deck_sha256=fp)
    if not st["storyboard_ready"]:
        raise StoryboardGateError(f"нельзя одобрить: {st['reason']}")
    record = {
        "schema": SCHEMA,
        "slug": lay.slug,
        "deck_sha256": fp,
        "draft_mp4_sha256": file_sha256(lay.draft_mp4),
        "approved_at": _now(),
        "approved_by": approved_by,
    }
    _save_json(lay.approval, record)
    return gate_status(slug, root=root)


def revoke(slug: str, *, root: Path = ROOT) -> dict[str, Any]:
    lay = _Layout(slug, root)
    if lay.approval.is_file():
        lay.approval.unlink()
    return gate_status(slug, root=root)


# --------------------------------------------------------------------------- storyboard build


def _default_extract_frame(mp4: Path, t_sec: float, out_jpg: Path) -> None:
    from audio_fx import find_ffmpeg  # lazy: keeps module import cheap for the gate

    cmd = [
        str(find_ffmpeg()), "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{t_sec:.3f}", "-i", str(mp4), "-frames:v", "1",
        "-vf", f"scale={FRAME_WIDTH}:-2", "-q:v", "4", str(out_jpg),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if proc.returncode != 0 or not out_jpg.is_file() or out_jpg.stat().st_size < MIN_FRAME_BYTES:
        raise StoryboardGateError(f"frame extraction failed at {t_sec:.2f}s: {(proc.stderr or '').strip()[-300:]}")


def _visual_for_slide(deck_slide: dict[str, Any], asset: dict[str, Any] | None) -> dict[str, Any] | None:
    cinema = deck_slide.get("cinema") or {}
    broll = deck_slide.get("broll") or {}
    ref = cinema.get("src") or broll.get("image")
    if not ref and asset is None:
        return None
    out: dict[str, Any] = {"file": ref or None, "source": None, "creator": None, "license": None,
                           "license_url": None, "page_url": None, "title": None, "kind": None}
    if asset is not None:
        out.update({
            "source": asset.get("source"),
            "creator": asset.get("creator"),
            "license": asset.get("license"),
            "license_url": asset.get("license_url"),
            "page_url": asset.get("page_url"),
            "title": asset.get("title"),
            "kind": asset.get("kind"),
        })
    return out


def build_storyboard(slug: str, *, root: Path = ROOT, extract_frame: FrameExtractor | None = None) -> dict[str, Any]:
    """Extract one still per slide from the fresh draft and write ``index.json``."""
    lay = _Layout(slug, root)
    deck = lay.read_deck()
    fp = deck_fingerprint(deck)
    st = gate_status(slug, root=root, deck_sha256=fp)
    if not st["draft_fresh"]:
        raise StoryboardGateError(f"нельзя собрать раскадровку: {st['reason']}")
    meta = _load_json(lay.draft_meta) or {}
    extractor = extract_frame or _default_extract_frame
    lay.sb_dir.mkdir(parents=True, exist_ok=True)
    deck_by_id = {s.get("id"): s for s in deck.get("slides") or []}
    plan = _load_json(lay.plan) or {}
    assets = {s["id"]: s["asset"] for s in plan.get("scenes") or [] if s.get("asset")}
    draft_sha = meta["draft_mp4_sha256"]

    slides_out: list[dict[str, Any]] = []
    for sl in meta.get("slides") or []:
        sid = sl["id"]
        if not SLIDE_ID_RE.match(sid):
            raise StoryboardGateError(f"invalid slide id in draft record: {sid!r}")
        start = float(sl["start_sec"])
        dur = float(sl["duration_sec"])
        t = start + min(FRAME_OFFSET_CAP_SEC, dur * FRAME_OFFSET_RATIO)
        frame = lay.sb_dir / f"{sid}.jpg"
        extractor(lay.draft_mp4, t, frame)
        if not frame.is_file() or frame.stat().st_size < MIN_FRAME_BYTES:
            raise StoryboardGateError(f"frame for slide {sid} was not written")
        src = deck_by_id.get(sid) or {}
        slides_out.append({
            "id": sid,
            "type": sl.get("type", ""),
            "title": sl.get("title", ""),
            "start_sec": round(start, 3),
            "duration_sec": round(dur, 3),
            "frame_sec": round(t, 3),
            "frame": frame.name,
            "voice_text": str(src.get("voice_text") or "")[:400],
            "visual": _visual_for_slide(src, assets.get(sid)),
        })

    index = {
        "schema": SCHEMA,
        "slug": lay.slug,
        "deck_sha256": fp,
        "draft_mp4_sha256": draft_sha,
        "built_at": _now(),
        "slides": slides_out,
    }
    _save_json(lay.index, index)
    return index


def storyboard_view(slug: str, *, root: Path = ROOT) -> dict[str, Any]:
    """Status + storyboard index for the console. Index is returned only if it matches the gate."""
    st = gate_status(slug, root=root)
    index = _load_json(_Layout(slug, root).index)
    return {"status": st, "index": index if st["storyboard_ready"] else None}


# --------------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DUP Presenter storyboard approval gate")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, text in (
        ("status", "Print gate status as JSON"),
        ("build", "Extract storyboard frames from the fresh draft"),
        ("approve", "Approve the storyboard for the current deck + draft"),
        ("revoke", "Revoke the approval"),
        ("check", "Exit 0 only if master render is allowed (fail-closed)"),
    ):
        sp = sub.add_parser(name, help=text)
        sp.add_argument("slug")
    args = parser.parse_args(argv)

    try:
        if args.cmd == "build":
            index = build_storyboard(args.slug)
            print(f"[OK] storyboard: {len(index['slides'])} slide frame(s) -> work/{args.slug}/storyboard/")
            out: Any = gate_status(args.slug)
        elif args.cmd == "approve":
            out = approve(args.slug)
        elif args.cmd == "revoke":
            out = revoke(args.slug)
        else:
            out = gate_status(args.slug)
    except StoryboardGateError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2

    print(json.dumps(out, ensure_ascii=False, indent=2))
    if args.cmd == "check":
        if out["can_master"]:
            return 0
        print(f"[BLOCKED] {out['reason']}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
