"""DUP Presenter — visual sourcing layer (Stage 3), fail-closed.

Pipeline (each step is a separate command, so a human can inspect the plan before download):

  plan   director script  -> work/visual_sources/<slug>/plan.json
         search free archives per scene (archive_sources.py), filter by licence / relevance /
         resolution / format, rank, keep the best N candidates per scene. No downloads.
  fetch  plan.json        -> public/visual/<slug>/<scene>_<sha12>.<ext>
         walk candidates in rank order (bounded attempts): resolve asset URL, download with
         size cap, sniff magic bytes, probe real dimensions/duration, then move into place.
  apply  plan + deck      -> decks/<slug>.json (or --out)
         cinema_clip slides get cinema.src = local asset (background_query removed so no hidden
         Pexels/Pixabay dependency); broll_cinematic slides get broll.image. Missing assets fail
         closed unless --allow-missing. The result is validated with validate_deck(check_assets=True).

Attribution: every fetched asset gets a credit line in out/<slug>_visual_credits.txt.
Nothing here uses API keys. Pillow (images) and ffprobe (video) are required for probing.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))

import archive_sources as arc  # noqa: E402
import httpx  # noqa: E402
from archive_sources import ArchiveSourceError  # noqa: E402
from build_deck import PUBLIC_DIR, DeckValidationError, validate_deck  # noqa: E402
from idea_engine import SLUG_RE  # noqa: E402
from stock_media import StockMediaError, validate_query  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WORK_DIR = ROOT / "work" / "visual_sources"
OUT_DIR = ROOT / "out"
PUBLIC_VISUAL_DIR = PUBLIC_DIR / "visual"
PLAN_SCHEMA = "dup-visual-plan/1"

# Scene visual_type -> which kind of asset may fill it. Graphic slides need no background.
SCENE_KIND: dict[str, str] = {"cinema_clip": "any", "broll_cinematic": "image"}
SKIPPED_TYPES = frozenset({"stat_burst", "kpi"})

MAX_QUERIES_PER_SCENE = 3
SEARCH_LIMIT_PER_QUERY = 8
KEEP_CANDIDATES_PER_SCENE = 8
MAX_ASSET_ATTEMPTS = 8  # archives contain dead links (OpenVerse 404 seen live); the pool must absorb them

MAX_IMAGE_BYTES = 25 * 1024 * 1024
MAX_VIDEO_BYTES = 80 * 1024 * 1024
MIN_ASSET_BYTES = 20_000
IMAGE_MIN_LONG = 1280
IMAGE_MIN_SHORT = 720
IMAGE_MAX_LONG = 8192
IMAGE_RATIO = (1.0, 2.4)
VIDEO_MIN_W = 1280
VIDEO_MIN_H = 720
VIDEO_RATIO = (1.3, 2.5)
VIDEO_MIN_SEC = 1.0
VIDEO_MAX_SEC = 120.0

ALLOWED_EXT: dict[str, frozenset[str]] = {
    "image": frozenset({".jpg", ".jpeg", ".png", ".webp"}),
    "video": frozenset({".mp4", ".webm"}),
}
SNIFF_EXT = {"jpeg": ".jpg", "png": ".png", "webp": ".webp", "mp4": ".mp4", "webm": ".webm"}
SNIFF_KIND = {"jpeg": "image", "png": "image", "webp": "image", "mp4": "video", "webm": "video"}

STOPWORDS = frozenset(
    {"the", "and", "of", "with", "for", "from", "a", "an", "in", "on", "to", "at", "by", "is", "are", "its", "into"}
)
NEGATIVE_TOKENS = frozenset({"logo", "icon", "signature", "stamp", "banknote", "emblem", "vector", "svg"})
LICENCE_LABEL = {
    "cc0": "CC0 1.0 (public domain dedication)",
    "pdm": "Public Domain Mark 1.0",
    "by": "CC BY (attribution required)",
    "by-sa": "CC BY-SA (attribution + share-alike required)",
    "nasa-media": "NASA media guidelines (public domain unless noted; credit NASA)",
}


class VisualSourcingError(RuntimeError):
    """A sourcing step failed closed; the message says exactly why."""


# --------------------------------------------------------------------------- helpers


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VisualSourcingError(f"cannot read JSON {path}: {exc}") from exc


def _save_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def tokens(text: str) -> set[str]:
    """Lower-case latin tokens, minimal plural folding, stopwords removed."""
    out: set[str] = set()
    for t in re.findall(r"[a-z0-9]+", text.lower()):
        if len(t) < 3 or t in STOPWORDS:
            continue
        if len(t) > 4 and t.endswith("ies"):
            t = t[:-3] + "y"
        elif len(t) > 4 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]
        out.add(t)
    return out


def relevance(query: str, cand: dict[str, Any]) -> tuple[float, bool]:
    """Relevance score and whether it clears the bar.

    Strong evidence = query tokens in the title or keywords (weight 1.0).
    Weak evidence = tokens only in a long description (weight 0.5, never enough on its own).
    The bar: 1-2 token queries must match every token strongly; longer queries need two thirds.
    """
    q = tokens(query)
    if not q:
        return 0.0, False
    strong = tokens(" ".join([cand.get("title", "")] + list(cand.get("keywords") or [])))
    weak = tokens(cand.get("description", ""))
    strong_hit = q & strong
    weak_only = (q & weak) - strong_hit
    score = (len(strong_hit) + 0.5 * len(weak_only)) / len(q)
    required = len(q) if len(q) <= 2 else math.ceil(0.66 * len(q))
    return round(min(score, 1.0), 4), len(strong_hit) >= required


def _url_ext(url: str) -> str:
    return Path(urlsplit(url).path).suffix.lower()


def _dims_ok(kind: str, w: int | None, h: int | None) -> str | None:
    """Return a rejection reason, or None. Unknown dimensions pass here and are checked after download."""
    if not w or not h:
        return None
    ratio = w / h
    if kind == "image":
        if max(w, h) < IMAGE_MIN_LONG or min(w, h) < IMAGE_MIN_SHORT:
            return "too_small"
        if max(w, h) > IMAGE_MAX_LONG:
            return "too_large"  # decode/memory cost in the renderer; Ken Burns does not need more
        if not (IMAGE_RATIO[0] <= ratio <= IMAGE_RATIO[1]):
            return "aspect"
    else:
        if w < VIDEO_MIN_W or h < VIDEO_MIN_H:
            return "too_small"
        if not (VIDEO_RATIO[0] <= ratio <= VIDEO_RATIO[1]):
            return "aspect"
    return None


def filter_candidate(query: str, cand: dict[str, Any], want_kind: str) -> tuple[bool, str, float]:
    """Metadata-only gate. Returns (accepted, reason, score)."""
    if cand.get("license") not in arc.ALLOWED_LICENSES:
        return False, "licence_not_allowed", 0.0
    kind = cand.get("kind")
    if kind not in ALLOWED_EXT:
        return False, "unknown_kind", 0.0
    if want_kind != "any" and kind != want_kind:
        return False, "kind_mismatch", 0.0
    words = tokens(cand.get("title", "")) | tokens(" ".join(cand.get("keywords") or []))
    if words & NEGATIVE_TOKENS:
        return False, "negative_keyword", 0.0
    rel, ok = relevance(query, cand)
    if not ok:
        return False, "low_relevance", rel
    reason = _dims_ok(kind, cand.get("width"), cand.get("height"))
    if reason:
        return False, reason, rel
    if cand.get("asset_url"):
        if _url_ext(cand["asset_url"]) not in ALLOWED_EXT[kind]:
            return False, "unsupported_format", rel
        if not arc.asset_host_allowed(cand["source"], cand["asset_url"]):
            return False, "asset_host_not_allowed", rel
    long_side = max(cand.get("width") or 0, cand.get("height") or 0)
    # Tie-breakers: resolution, then closeness to 16:9 (0 when dimensions are unknown).
    aspect_pref = 0.0
    if cand.get("width") and cand.get("height"):
        aspect_pref = 1.0 - min(1.0, abs((cand["width"] / cand["height"]) - (16 / 9)) / 1.0)
    # A cinema_clip prefers real motion: video gets a small bonus when both kinds are allowed.
    video_pref = 0.05 if (want_kind == "any" and kind == "video") else 0.0
    score = round(rel + 0.1 * min(1.0, long_side / 1920.0) + 0.02 * aspect_pref + video_pref, 4)
    return True, "accepted", score


def _title_key(cand: dict[str, Any]) -> str:
    """Cross-source duplicate key: the same photo is often indexed by several archives."""
    return " ".join(re.findall(r"[a-z0-9]+", cand.get("title", "").lower()))[:80]


def select_top(pool: list[dict[str, Any]], want: str, limit: int) -> list[dict[str, Any]]:
    """Pick the best `limit` candidates. For mixed (`any`) scenes, reserve up to half the slots for video."""
    pool = sorted(pool, key=lambda c: (-c["score"], c["source"], c["source_id"]))
    seen_titles: set[str] = set()
    unique: list[dict[str, Any]] = []
    for c in pool:
        key = _title_key(c)
        if key and key in seen_titles:
            continue
        seen_titles.add(key)
        unique.append(c)
    if want != "any":
        return unique[:limit]
    videos = [c for c in unique if c["kind"] == "video"][: max(1, limit // 2)]
    chosen_ids = {(c["source"], c["source_id"]) for c in videos}
    rest = [c for c in unique if (c["source"], c["source_id"]) not in chosen_ids]
    merged = videos + rest[: max(0, limit - len(videos))]
    return sorted(merged, key=lambda c: (-c["score"], c["source"], c["source_id"]))


# --------------------------------------------------------------------------- plan


def _plan_scene(scene: dict[str, Any], sources: list[str], per_scene: int) -> dict[str, Any]:
    vt = scene["visual_type"]
    entry: dict[str, Any] = {
        "id": scene["id"],
        "act": scene["act"],
        "visual_type": vt,
        "queries": [],
        "status": "",
        "candidates": [],
        "rejected_counts": {},
        "source_errors": [],
        "asset": None,
    }
    if vt in SKIPPED_TYPES:
        entry["status"] = "skipped"
        entry["reason"] = "graphic slide: no background needed"
        return entry
    if vt not in SCENE_KIND:
        raise VisualSourcingError(f"scene {scene['id']}: visual_type {vt!r} has no sourcing rule")
    want = SCENE_KIND[vt]
    queries = [q for q in (scene.get("stock_queries_en") or []) if q][:MAX_QUERIES_PER_SCENE]
    if not queries:
        entry["status"] = "no_queries"
        entry["reason"] = "scene has no stock_queries_en; nothing to search"
        return entry

    rejected: Counter[str] = Counter()
    seen: set[tuple[str, str]] = set()
    pool: list[dict[str, Any]] = []
    for raw_q in queries:
        try:
            q = validate_query(raw_q)
        except StockMediaError as exc:
            raise VisualSourcingError(f"scene {scene['id']}: {exc}") from exc
        entry["queries"].append(q)
        for src in sources:
            kinds = [want] if want != "any" else ["video", "image"]
            for kind in kinds:
                if src == "openverse" and kind == "video":
                    continue  # Openverse has no video index; this is a documented capability gap
                try:
                    found = arc.SEARCHERS[src](q, kind, SEARCH_LIMIT_PER_QUERY)
                except ArchiveSourceError as exc:
                    entry["source_errors"].append({"source": src, "query": q, "kind": kind, "error": str(exc)})
                    continue
                for cand in found:
                    key = (cand["source"], cand["source_id"])
                    if key in seen:
                        continue
                    seen.add(key)
                    ok, reason, score = filter_candidate(q, cand, want)
                    if not ok:
                        rejected[reason] += 1
                        continue
                    cand["query"] = q
                    cand["score"] = score
                    pool.append(cand)

    entry["candidates"] = select_top(pool, want, per_scene)
    entry["rejected_counts"] = dict(rejected)
    entry["status"] = "candidates" if entry["candidates"] else "no_candidates"
    return entry


def build_plan(script: dict[str, Any], *, sources: list[str], per_scene: int) -> dict[str, Any]:
    unknown = [s for s in sources if s not in arc.SEARCHERS]
    if unknown or not sources:
        raise VisualSourcingError(f"unknown or empty sources {unknown or sources!r}; allowed: {list(arc.SOURCES)}")
    slug = str(script.get("slug") or "")
    if not SLUG_RE.match(slug):
        raise VisualSourcingError(f"script slug {slug!r} is not a valid slug")
    scenes = [_plan_scene(s, sources, per_scene) for s in script.get("scenes") or []]
    counts = Counter(s["status"] for s in scenes)
    return {
        "schema": PLAN_SCHEMA,
        "slug": slug,
        "title": script.get("title", ""),
        "lang": script.get("lang", ""),
        "created_at": _utc_now(),
        "sources": sources,
        "scenes": scenes,
        "summary": dict(counts),
    }


def plan_path_for(slug: str) -> Path:
    return WORK_DIR / slug / "plan.json"


# --------------------------------------------------------------------------- fetch


def _sniff(head: bytes) -> str | None:
    if head[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head[4:8] == b"ftyp":
        return "mp4"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "webm"
    return None


def _download(source: str, url: str, kind: str, tmp: Path) -> tuple[str, int, str]:
    """Stream to tmp with a size cap. Returns (sha256, bytes, sniffed_format). Fails closed."""
    cap = MAX_VIDEO_BYTES if kind == "video" else MAX_IMAGE_BYTES
    if not url.startswith("https://"):
        raise VisualSourcingError(f"refusing non-https asset URL from {source}")
    digest = hashlib.sha256()
    written = 0
    head = b""
    try:
        with httpx.Client(
            timeout=120.0, headers={"User-Agent": arc.USER_AGENT}, follow_redirects=True, verify=True
        ) as client:
            with client.stream("GET", url) as r:
                r.raise_for_status()
                if not arc.asset_host_allowed(source, str(r.url)):
                    raise VisualSourcingError(f"{source}: redirected to a host outside the allow-list")
                ctype = (r.headers.get("content-type") or "").lower()
                if "html" in ctype or "json" in ctype:
                    raise VisualSourcingError(f"{source}: asset URL returned {ctype!r}, not media")
                declared = r.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > cap:
                    raise VisualSourcingError(f"{source}: declared size {declared} exceeds {cap} bytes")
                with tmp.open("wb") as f:
                    for chunk in r.iter_bytes(256 * 1024):
                        if not head:
                            head = chunk[:16]
                        written += len(chunk)
                        if written > cap:
                            raise VisualSourcingError(f"{source}: download exceeds {cap} bytes")
                        digest.update(chunk)
                        f.write(chunk)
    except httpx.HTTPStatusError as exc:
        tmp.unlink(missing_ok=True)
        raise VisualSourcingError(f"{source}: asset HTTP {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        tmp.unlink(missing_ok=True)
        raise VisualSourcingError(f"{source}: asset download failed: {type(exc).__name__}") from exc
    except VisualSourcingError:
        tmp.unlink(missing_ok=True)
        raise
    if written < MIN_ASSET_BYTES:
        tmp.unlink(missing_ok=True)
        raise VisualSourcingError(f"{source}: asset too small ({written} bytes)")
    fmt = _sniff(head)
    if fmt is None:
        tmp.unlink(missing_ok=True)
        raise VisualSourcingError(f"{source}: content is not a recognised image/video (magic bytes)")
    return digest.hexdigest(), written, fmt


def _probe_image(path: Path) -> dict[str, Any]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise VisualSourcingError("Pillow is required to probe images (pip install pillow)") from exc
    try:
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            w, h = im.size
    except Exception as exc:  # noqa: BLE001 - any decoder failure is a rejection, reported with its type
        raise VisualSourcingError(f"image decode failed: {type(exc).__name__}") from exc
    return {"width": int(w), "height": int(h), "duration_sec": None}


def _find_ffprobe() -> str:
    from audio_fx import find_ffprobe

    return str(find_ffprobe())


def _probe_video(path: Path) -> dict[str, Any]:
    cmd = [
        _find_ffprobe(), "-v", "error", "-print_format", "json",
        "-show_entries", "stream=codec_type,width,height:format=duration", str(path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VisualSourcingError(f"ffprobe could not run: {type(exc).__name__}") from exc
    if proc.returncode != 0:
        raise VisualSourcingError(f"ffprobe rejected the file (exit {proc.returncode})")
    try:
        info = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise VisualSourcingError("ffprobe returned unreadable output") from exc
    streams = [s for s in info.get("streams") or [] if s.get("codec_type") == "video"]
    if not streams:
        raise VisualSourcingError("file has no video stream")
    w, h = int(streams[0].get("width") or 0), int(streams[0].get("height") or 0)
    try:
        dur = float((info.get("format") or {}).get("duration"))
    except (TypeError, ValueError) as exc:
        raise VisualSourcingError("video duration unreadable") from exc
    return {"width": w, "height": h, "duration_sec": round(dur, 3)}


def _validate_probe(kind: str, probe: dict[str, Any]) -> None:
    reason = _dims_ok(kind, probe["width"], probe["height"])
    if reason:
        raise VisualSourcingError(f"downloaded {kind} rejected after probe: {reason} ({probe['width']}x{probe['height']})")
    if kind == "video":
        dur = probe["duration_sec"]
        if not (VIDEO_MIN_SEC <= dur <= VIDEO_MAX_SEC):
            raise VisualSourcingError(f"video duration {dur}s outside {VIDEO_MIN_SEC}..{VIDEO_MAX_SEC}s")


def fetch_candidate(scene_id: str, slug: str, cand: dict[str, Any]) -> dict[str, Any]:
    """Resolve, download, verify and place one candidate. Returns the asset record. Raises on any failure."""
    cand = arc.resolve_asset(cand)
    url = cand["asset_url"]
    if not arc.asset_host_allowed(cand["source"], url):
        raise VisualSourcingError(f"{cand['source']}: asset host not allowed")
    PUBLIC_VISUAL_DIR.joinpath(slug).mkdir(parents=True, exist_ok=True)
    tmp = PUBLIC_VISUAL_DIR / slug / f".{scene_id}.part"
    try:
        sha, nbytes, fmt = _download(cand["source"], url, cand["kind"], tmp)
        kind = SNIFF_KIND[fmt]
        if kind != cand["kind"]:
            raise VisualSourcingError(f"content is {kind}, candidate declared {cand['kind']}")
        ext = SNIFF_EXT[fmt]
        if ext not in ALLOWED_EXT[kind]:
            raise VisualSourcingError(f"sniffed extension {ext} not allowed for {kind}")
        probe = _probe_image(tmp) if kind == "image" else _probe_video(tmp)
        _validate_probe(kind, probe)
    except VisualSourcingError:
        tmp.unlink(missing_ok=True)
        raise
    final_name = f"{scene_id}_{sha[:12]}{ext}"
    final = PUBLIC_VISUAL_DIR / slug / final_name
    os.replace(tmp, final)
    return {
        "file": f"visual/{slug}/{final_name}",
        "kind": kind,
        "sha256": sha,
        "bytes": nbytes,
        "width": probe["width"],
        "height": probe["height"],
        "duration_sec": probe["duration_sec"],
        "source": cand["source"],
        "source_id": cand["source_id"],
        "title": cand["title"],
        "creator": cand["creator"],
        "license": cand["license"],
        "license_url": cand.get("license_url", ""),
        "page_url": cand["page_url"],
        "asset_url": url,
    }


def fetch_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Fill scene.asset for every scene that has candidates. Failed scenes keep their errors.

    The same archive item is never used in two scenes of one film (it would repeat on screen).
    """
    slug = plan["slug"]
    used: set[tuple[str, str]] = set()
    for scene in plan["scenes"]:
        if scene.get("asset"):
            used.add((scene["asset"]["source"], scene["asset"]["source_id"]))
    for scene in plan["scenes"]:
        if scene["status"] != "candidates":
            continue
        errors: list[dict[str, str]] = []
        for attempt, cand in enumerate(scene["candidates"][:MAX_ASSET_ATTEMPTS], start=1):
            key = (cand["source"], cand["source_id"])
            if key in used:
                errors.append({"attempt": str(attempt), "source": cand["source"], "source_id": cand["source_id"],
                               "error": "already used by another scene of this film"})
                continue
            try:
                scene["asset"] = fetch_candidate(scene["id"], slug, cand)
                scene["status"] = "fetched"
                used.add(key)
                break
            except (VisualSourcingError, ArchiveSourceError) as exc:
                errors.append({"attempt": str(attempt), "source": cand["source"], "source_id": cand["source_id"], "error": str(exc)})
        if scene["asset"] is None:
            scene["status"] = "failed"
            scene["fetch_errors"] = errors
    plan["summary"] = dict(Counter(s["status"] for s in plan["scenes"]))
    plan["fetched_at"] = _utc_now()
    return plan


# --------------------------------------------------------------------------- apply


def apply_to_deck(deck: dict[str, Any], plan: dict[str, Any], *, allow_missing: bool = False) -> dict[str, Any]:
    """Return a copy of deck with local assets wired into cinema_clip / broll_cinematic slides."""
    import copy

    out = copy.deepcopy(deck)
    by_id = {s.get("id"): s for s in out.get("slides") or []}
    missing: list[str] = []
    cinema_missing: list[str] = []
    wired: list[str] = []
    for scene in plan["scenes"]:
        if scene["visual_type"] not in SCENE_KIND:
            continue
        slide = by_id.get(scene["id"])
        if slide is None:
            raise VisualSourcingError(f"plan scene {scene['id']} has no matching slide in the deck")
        asset = scene.get("asset")
        if asset is None:
            missing.append(f"{scene['id']} ({scene['status']})")
            if scene["visual_type"] == "cinema_clip":
                cinema_missing.append(scene["id"])
            continue
        if scene["visual_type"] == "cinema_clip":
            cinema = slide.get("cinema")
            if not isinstance(cinema, dict):
                raise VisualSourcingError(f"slide {scene['id']}: cinema_clip without cinema object")
            if cinema.get("shots") is not None:
                raise VisualSourcingError(f"slide {scene['id']}: cinema.shots already set; refusing to override")
            cinema["src"] = asset["file"]
            slide.pop("background_query", None)
        else:
            if asset["kind"] != "image":
                raise VisualSourcingError(f"slide {scene['id']}: broll_cinematic needs an image asset")
            broll = slide.get("broll")
            if not isinstance(broll, dict):
                raise VisualSourcingError(f"slide {scene['id']}: broll_cinematic without broll object")
            broll["image"] = asset["file"]
        wired.append(scene["id"])
    # cinema_clip must carry media: with background disabled, an unfilled cinema slide would render empty.
    # --allow-missing only relaxes broll_cinematic (where the image is optional decoration).
    if cinema_missing:
        raise VisualSourcingError(
            "cinema_clip scene(s) have no local media and cannot be left empty: " + ", ".join(cinema_missing)
        )
    if missing and not allow_missing:
        raise VisualSourcingError(
            "no local asset for scene(s): " + ", ".join(missing) + " (use --allow-missing to keep them unfilled)"
        )
    validate_deck(out, check_assets=True)
    return {"deck": out, "wired": wired, "missing": missing}


def attribution_lines(plan: dict[str, Any]) -> list[str]:
    lines = [f"Visual credits — {plan.get('title', plan['slug'])} ({plan['slug']})", ""]
    for scene in plan["scenes"]:
        a = scene.get("asset")
        if not a:
            continue
        lines.append(
            f"- {scene['id']} [{a['kind']}] {a['creator']} — \"{a['title']}\" — "
            f"{LICENCE_LABEL.get(a['license'], a['license'])} — {a.get('license_url') or 'no licence URL'} — "
            f"source: {a['page_url']}"
        )
    return lines


def write_attribution(plan: dict[str, Any]) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{plan['slug']}_visual_credits.txt"
    path.write_text("\n".join(attribution_lines(plan)) + "\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------- CLI


def _parse_sources(text: str) -> list[str]:
    return [s.strip() for s in text.split(",") if s.strip()]


def cmd_search(args: argparse.Namespace) -> int:
    q = validate_query(args.query)
    sources = _parse_sources(args.sources)
    for src in sources:
        if src not in arc.SEARCHERS:
            raise VisualSourcingError(f"unknown source {src!r}")
    rows = []
    for src in sources:
        for kind in (["video", "image"] if args.kind == "any" else [args.kind]):
            if src == "openverse" and kind == "video":
                continue
            try:
                found = arc.SEARCHERS[src](q, kind, args.limit)
            except ArchiveSourceError as exc:
                print(f"[ERROR] {src}/{kind}: {exc}")
                continue
            for c in found:
                ok, reason, score = filter_candidate(q, c, "any" if args.kind == "any" else args.kind)
                rows.append((score, src, kind, ok, reason, c))
    rows.sort(key=lambda r: -r[0])
    for score, src, kind, ok, reason, c in rows:
        flag = "KEEP" if ok else f"skip:{reason}"
        print(f"[{flag}] {src}/{kind} score={score} lic={c.get('license')} | {c['title'][:70]} | {c['page_url']}")
    print(f"[OK] {len(rows)} candidates, {sum(1 for r in rows if r[3])} pass filters")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    script = _load_json(Path(args.script))
    plan = build_plan(script, sources=_parse_sources(args.sources), per_scene=args.per_scene)
    path = plan_path_for(plan["slug"])
    _save_json(path, plan)
    print(f"[OK] plan {path}")
    print(f"[OK] scenes: {plan['summary']}")
    for s in plan["scenes"]:
        errs = f", source_errors={len(s['source_errors'])}" if s["source_errors"] else ""
        print(f"  {s['id']} {s['visual_type']:<16} {s['status']:<14} candidates={len(s['candidates'])}{errs}")
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    path = Path(args.plan)
    plan = _load_json(path)
    if plan.get("schema") != PLAN_SCHEMA:
        raise VisualSourcingError(f"{path} is not a {PLAN_SCHEMA} plan")
    fetch_plan(plan)
    _save_json(path, plan)
    print(f"[OK] fetch summary: {plan['summary']}")
    for s in plan["scenes"]:
        if s["status"] == "fetched":
            a = s["asset"]
            print(f"  {s['id']} fetched {a['file']} {a['kind']} {a['width']}x{a['height']} lic={a['license']} by {a['creator']}")
        elif s["status"] == "failed":
            print(f"  {s['id']} FAILED: {s.get('fetch_errors')}")
    return 0 if plan["summary"].get("failed", 0) == 0 else 1


def cmd_apply(args: argparse.Namespace) -> int:
    plan = _load_json(Path(args.plan))
    deck = _load_json(Path(args.deck))
    result = apply_to_deck(deck, plan, allow_missing=args.allow_missing)
    out = Path(args.out) if args.out else ROOT / "decks" / f"{plan['slug']}.json"
    if out.exists() and not args.overwrite:
        raise VisualSourcingError(f"{out} exists; pass --overwrite to replace it")
    _save_json(out, result["deck"])
    credits = write_attribution(plan)
    print(f"[OK] wired {len(result['wired'])} scene(s): {result['wired']}")
    if result["missing"]:
        print(f"[WARN] unfilled scenes (allowed): {result['missing']}")
    print(f"[OK] deck {out} (validated with check_assets=True)")
    print(f"[OK] credits {credits}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Free archive visual sourcing (fail-closed).")
    sub = parser.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search", help="quick search across free archives (no plan written)")
    s.add_argument("--query", required=True)
    s.add_argument("--kind", choices=["any", "image", "video"], default="any")
    s.add_argument("--sources", default=",".join(arc.SOURCES))
    s.add_argument("--limit", type=int, default=5)

    p = sub.add_parser("plan", help="search + filter per scene from a director script")
    p.add_argument("--script", required=True)
    p.add_argument("--sources", default=",".join(arc.SOURCES))
    p.add_argument("--per-scene", type=int, default=KEEP_CANDIDATES_PER_SCENE)

    f = sub.add_parser("fetch", help="download + verify the best candidate per scene")
    f.add_argument("--plan", required=True)

    a = sub.add_parser("apply", help="wire fetched assets into a deck and validate it")
    a.add_argument("--plan", required=True)
    a.add_argument("--deck", required=True)
    a.add_argument("--out", default="")
    a.add_argument("--overwrite", action="store_true")
    a.add_argument("--allow-missing", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "search":
            return cmd_search(args)
        if args.cmd == "plan":
            return cmd_plan(args)
        if args.cmd == "fetch":
            return cmd_fetch(args)
        return cmd_apply(args)
    except (VisualSourcingError, DeckValidationError, StockMediaError, ArchiveSourceError) as exc:
        print(f"[FAIL] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
