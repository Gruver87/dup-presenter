"""Drag-and-drop asset store, metadata inspector, smart slide binder, and archive search helper.

Stores user-dropped files and fetched archive media under `public/uploads/<slug>/` with:
  - 100 MB per-file cap (fail-closed)
  - magic-byte validation (JPEG, PNG, WebP, MP4, WebM)
  - real dimension/duration probing (PIL / ffprobe)
  - per-deck metadata manifest at `work/<slug>/assets_meta.json` (license, creator, source)
    which `publish_pack.py` automatically reads for CC BY / CC BY-SA attributions.
"""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DIR = ROOT / "public"
UPLOADS_DIR = PUBLIC_DIR / "uploads"
WORK_DIR = ROOT / "work"

MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB per file
URL_TIMEOUT_SEC = 20.0
ALLOWED_META_LICENCES = frozenset({"", "own", "cc0", "pdm", "by", "by-sa", "nasa-media", "unknown"})
CREDIT_LICENCES = frozenset({"by", "by-sa"})
# Licence values that mean "we do not know the rights holder's terms".
UNLICENSED_VALUES = frozenset({"", "unknown"})


class AssetStoreError(ValueError):
    """Raised when an asset fails validation, size cap, binding, or download."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_rel_path(rel_file: str) -> Path:
    """Resolve a relative path under PUBLIC_DIR, refusing traversal or absolute paths."""
    cleaned = str(rel_file or "").strip().replace("\\", "/")
    if not cleaned or cleaned.startswith("/") or ".." in cleaned.split("/"):
        raise AssetStoreError(f"Unsafe asset path: {rel_file!r}")
    full = (PUBLIC_DIR / cleaned).resolve()
    pub_resolved = PUBLIC_DIR.resolve()
    if pub_resolved not in full.parents:
        raise AssetStoreError(f"Asset path escapes public/: {rel_file!r}")
    return full


def sniff_media(head: bytes) -> tuple[str, str] | None:
    """Return (kind, ext) from magic bytes, or None if unsupported."""
    if len(head) < 12:
        return None
    if head[:3] == b"\xff\xd8\xff":
        return ("image", ".jpg")
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return ("image", ".png")
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ("image", ".webp")
    if head[4:8] == b"ftyp":
        return ("video", ".mp4")
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return ("video", ".webm")
    return None


def probe_media_file(path: Path, kind: str) -> dict[str, Any]:
    """Probe real dimensions, format, and (for video) duration on disk."""
    size = path.stat().st_size
    if kind == "image":
        from PIL import Image

        try:
            with Image.open(path) as img:
                img.verify()
            with Image.open(path) as img:
                w, h = img.size
                fmt = (img.format or path.suffix.lstrip(".")).upper()
        except Exception as exc:
            raise AssetStoreError(f"Файл не является корректной картинкой: {exc}") from exc
        return {"bytes": size, "width": int(w), "height": int(h), "duration_sec": None, "format": fmt}

    from audio_fx import find_ffprobe

    ffprobe = find_ffprobe()
    proc = subprocess.run(
        [
            ffprobe,
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,codec_name:format=duration,format_name",
            "-of", "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )
    if proc.returncode != 0:
        raise AssetStoreError(f"ffprobe отклонил видеофайл (exit {proc.returncode})")
    try:
        info = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise AssetStoreError(f"ffprobe вернул некорректный JSON: {exc}") from exc
    streams = info.get("streams") or []
    if not streams:
        raise AssetStoreError("Видеофайл не содержит видеодорожки")
    v0 = streams[0]
    dur_raw = (info.get("format") or {}).get("duration")
    dur = round(float(dur_raw), 2) if dur_raw is not None else None
    return {
        "bytes": size,
        "width": int(v0.get("width") or 0),
        "height": int(v0.get("height") or 0),
        "duration_sec": dur,
        "format": str(v0.get("codec_name") or path.suffix.lstrip(".")).upper(),
    }


def meta_path_for(slug: str) -> Path:
    return WORK_DIR / slug / "assets_meta.json"


def deck_upload_refs(deck: Any) -> set[str]:
    """Every `uploads/...` asset path referenced anywhere inside a deck (any slide field)."""
    refs: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif isinstance(node, str):
            s = node.replace("\\", "/")
            if s.startswith("uploads/"):
                refs.add(s)

    walk(deck)
    return refs


def unlicensed_deck_assets(slug: str, deck: Any) -> list[str]:
    """Uploaded assets used by `deck` whose licence was never set (blocks TikTok upload).

    Only files with a metadata record are checked: every file dropped or downloaded through the
    console gets one. Hand-placed files under public/ (no record) are outside this gate.
    """
    meta = load_assets_meta(slug)
    bad: list[str] = []
    for rel in sorted(deck_upload_refs(deck)):
        rec = meta.get(rel)
        if rec is None:
            continue
        lic = str(rec.get("license") or "").strip().lower()
        if lic in UNLICENSED_VALUES:
            bad.append(rel)
    return bad


def load_assets_meta(slug: str) -> dict[str, dict[str, Any]]:
    """Load work/<slug>/assets_meta.json.

    A corrupt file raises instead of returning {}: the next save would otherwise
    overwrite it and silently drop CC BY attribution for every other asset.
    """
    path = meta_path_for(slug)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AssetStoreError(f"Файл метаданных повреждён или недоступен: {path} ({exc})") from exc
    if not isinstance(data, dict):
        raise AssetStoreError(f"Файл метаданных имеет неверный формат (ожидается объект): {path}")
    return data


def save_assets_meta(slug: str, data: dict[str, dict[str, Any]]) -> Path:
    path = meta_path_for(slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def save_uploaded_bytes(
    slug: str,
    raw_bytes: bytes,
    filename: str = "",
    *,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate and save raw bytes into public/uploads/<slug>/ and record metadata."""
    if not raw_bytes:
        raise AssetStoreError("Пустой файл")
    if len(raw_bytes) > MAX_UPLOAD_BYTES:
        mb = round(len(raw_bytes) / (1024 * 1024), 1)
        raise AssetStoreError(f"Файл слишком большой ({mb} МБ; лимит {MAX_UPLOAD_BYTES // (1024 * 1024)} МБ)")
    sniffed = sniff_media(raw_bytes[:32])
    if sniffed is None:
        raise AssetStoreError("Неподдерживаемый формат файла. Разрешены: JPG, PNG, WebP, MP4, WebM.")
    kind, ext = sniffed
    all_meta = load_assets_meta(slug)

    digest = hashlib.sha256(raw_bytes).hexdigest()[:12]
    dest_dir = UPLOADS_DIR / slug
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{digest}{ext}"
    tmp = dest.with_suffix(ext + ".tmp")
    tmp.write_bytes(raw_bytes)
    try:
        probed = probe_media_file(tmp, kind)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(dest)

    rel_file = f"uploads/{slug}/{dest.name}"
    m = meta or {}
    lic = str(m.get("license") or "").strip().lower()
    if lic not in ALLOWED_META_LICENCES:
        lic = "unknown"
    record = {
        "file": rel_file,
        "kind": kind,
        "bytes": probed["bytes"],
        "width": probed["width"],
        "height": probed["height"],
        "duration_sec": probed["duration_sec"],
        "format": probed["format"],
        "title": str(m.get("title") or Path(filename).stem or dest.stem).strip()[:200],
        "creator": str(m.get("creator") or "").strip()[:160],
        "source": str(m.get("source") or "local-upload").strip()[:80],
        "license": lic,
        "license_url": str(m.get("license_url") or "").strip()[:300],
        "page_url": str(m.get("page_url") or "").strip()[:400],
        "needs_credit": lic in CREDIT_LICENCES,
        "updated_at": _utc_now(),
    }
    all_meta[rel_file] = record
    save_assets_meta(slug, all_meta)
    return record


def save_from_url(
    slug: str,
    url: str,
    *,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Download an https:// image/video URL (<=100 MB, TLS verified) and save it as a project upload."""
    clean_url = str(url or "").strip()
    parsed = urllib.parse.urlparse(clean_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise AssetStoreError("Разрешены только https:// ссылки на изображения и видео.")

    req = urllib.request.Request(
        clean_url,
        headers={"User-Agent": "DUP-Presenter/1.3 (https://github.com/Gruver87/dup-presenter)"},
    )
    chunks: list[bytes] = []
    total = 0
    try:
        with urllib.request.urlopen(req, timeout=URL_TIMEOUT_SEC) as resp:
            if urllib.parse.urlparse(resp.geturl()).scheme != "https":
                raise AssetStoreError("Ссылка перенаправила на небезопасный адрес (не https://).")
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise AssetStoreError(
                        f"Файл по ссылке превышает лимит {MAX_UPLOAD_BYTES // (1024 * 1024)} МБ"
                    )
                chunks.append(chunk)
    except AssetStoreError:
        raise
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AssetStoreError(f"Не удалось скачать файл по ссылке: {exc}") from exc

    raw = b"".join(chunks)
    m = dict(meta or {})
    m.setdefault("source", parsed.netloc)
    m.setdefault("page_url", clean_url)
    fname = Path(urllib.parse.unquote(parsed.path)).name or "remote_asset"
    return save_uploaded_bytes(slug, raw, fname, meta=m)


def bind_asset_to_slide(deck: dict[str, Any], slide_id: str, asset: dict[str, Any]) -> dict[str, Any]:
    """Return a validated copy of `deck` with `asset` bound to `slide_id` (smart binding by slide type)."""
    from build_deck import DeckValidationError, validate_deck

    out = copy.deepcopy(deck)
    target = next((s for s in (out.get("slides") or []) if s.get("id") == slide_id), None)
    if target is None:
        raise AssetStoreError(f"Слайд {slide_id!r} не найден в колоде")

    stype = str(target.get("type") or "")
    kind = str(asset.get("kind") or "")
    rel_file = str(asset.get("file") or "")
    if not rel_file:
        raise AssetStoreError("Отсутствует путь к файлу ассета")

    if stype == "cinema_clip":
        cc = target.setdefault("cinema", {})
        if not isinstance(cc, dict):
            cc = {}
            target["cinema"] = cc
        if kind == "video":
            cc.pop("shots", None)
            cc["src"] = rel_file
            target.pop("background_query", None)
        elif kind == "image":
            cc.pop("src", None)
            cc["shots"] = [{"src": rel_file, "kind": "image", "zoom": 1.06}]
            target.pop("background_query", None)
        else:
            raise AssetStoreError(f"Неподдерживаемый тип ассета: {kind!r}")
    elif stype == "broll_cinematic":
        if kind != "image":
            raise AssetStoreError("Слайд broll_cinematic принимает только картинки. Для видео используй cinema_clip.")
        br = target.setdefault("broll", {})
        if not isinstance(br, dict):
            br = {}
            target["broll"] = br
        br["image"] = rel_file
        target.pop("background_query", None)
    elif stype == "screenshot":
        if kind != "image":
            raise AssetStoreError("Слайд screenshot принимает только картинки.")
        sc = target.setdefault("screenshot", {})
        if not isinstance(sc, dict):
            sc = {}
            target["screenshot"] = sc
        sc["image"] = rel_file
    else:
        raise AssetStoreError(
            f"Слайд типа '{stype}' не поддерживает привязку медиа. "
            "Перетаскивай видео/картинки на cinema_clip, broll_cinematic или screenshot."
        )

    try:
        validate_deck(out, check_assets=True)
    except DeckValidationError as exc:
        raise AssetStoreError(f"Колода не прошла валидацию после привязки: {exc}") from exc
    return out


def inspect_asset(slug: str, rel_file: str) -> dict[str, Any]:
    """Return full metadata for an asset under public/, merging assets_meta.json, sourcing plan, and disk probe."""
    full = _safe_rel_path(rel_file)
    norm_rel = str(full.relative_to(PUBLIC_DIR.resolve())).replace("\\", "/")

    meta = dict(load_assets_meta(slug).get(norm_rel) or {})
    if not meta:
        plan_p = WORK_DIR / "visual_sources" / slug / "plan.json"
        if plan_p.is_file():
            try:
                plan = json.loads(plan_p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise AssetStoreError(f"План визуалов повреждён или недоступен: {plan_p} ({exc})") from exc
            if isinstance(plan, dict):
                for sc in plan.get("scenes") or []:
                    a = sc.get("asset")
                    if isinstance(a, dict) and str(a.get("file") or "").replace("\\", "/") == norm_rel:
                        meta = {
                            "file": norm_rel,
                            "kind": a.get("kind", "image"),
                            "title": a.get("title", ""),
                            "creator": a.get("creator", ""),
                            "source": a.get("source", ""),
                            "license": a.get("license", ""),
                            "license_url": a.get("license_url", ""),
                            "page_url": a.get("page_url", ""),
                            "width": a.get("width"),
                            "height": a.get("height"),
                        }
                        break

    exists = full.is_file()
    probe_error = ""
    if exists and (not meta.get("bytes") or not meta.get("width")):
        head = full.read_bytes()[:32]
        sn = sniff_media(head)
        kind = sn[0] if sn else ("video" if full.suffix.lower() in {".mp4", ".webm", ".mov"} else "image")
        try:
            probed = probe_media_file(full, kind)
        except AssetStoreError as exc:
            probe_error = str(exc)
            probed = {"bytes": full.stat().st_size, "width": 0, "height": 0, "duration_sec": None, "format": full.suffix.lstrip(".").upper()}
        meta.setdefault("kind", kind)
        meta.update({k: v for k, v in probed.items() if v is not None or k not in meta})

    lic = str(meta.get("license") or "").strip().lower()
    return {
        "file": norm_rel,
        "exists": exists,
        "kind": meta.get("kind") or "image",
        "bytes": meta.get("bytes") or (full.stat().st_size if exists else 0),
        "width": meta.get("width") or 0,
        "height": meta.get("height") or 0,
        "duration_sec": meta.get("duration_sec"),
        "format": meta.get("format") or full.suffix.lstrip(".").upper(),
        "title": meta.get("title") or full.stem,
        "creator": meta.get("creator") or "",
        "source": meta.get("source") or ("local" if exists else ""),
        "license": lic,
        "license_url": meta.get("license_url") or "",
        "page_url": meta.get("page_url") or "",
        "needs_credit": lic in CREDIT_LICENCES,
        "probe_error": probe_error,
    }


def update_asset_meta(slug: str, rel_file: str, patch: dict[str, Any]) -> dict[str, Any]:
    """Update editable attribution/license metadata for an asset in work/<slug>/assets_meta.json."""
    cur = inspect_asset(slug, rel_file)
    lic = str(patch.get("license", cur.get("license") or "")).strip().lower()
    if lic not in ALLOWED_META_LICENCES:
        raise AssetStoreError(f"Неизвестная лицензия {lic!r}; допустимо: {sorted(ALLOWED_META_LICENCES)}")
    cur["title"] = str(patch.get("title", cur["title"])).strip()[:200]
    cur["creator"] = str(patch.get("creator", cur["creator"])).strip()[:160]
    cur["source"] = str(patch.get("source", cur["source"])).strip()[:80]
    cur["license"] = lic
    cur["license_url"] = str(patch.get("license_url", cur["license_url"])).strip()[:300]
    cur["page_url"] = str(patch.get("page_url", cur["page_url"])).strip()[:400]
    cur["needs_credit"] = lic in CREDIT_LICENCES
    cur["updated_at"] = _utc_now()
    probe_error = cur.pop("probe_error", "")

    all_meta = load_assets_meta(slug)
    all_meta[cur["file"]] = cur
    save_assets_meta(slug, all_meta)
    return {**cur, "probe_error": probe_error}


def search_free_archives(
    query: str,
    *,
    kind: str = "any",
    sources: list[str] | None = None,
    limit: int = 8,
) -> dict[str, Any]:
    """Search Wikimedia, NASA, and Openverse (no API keys) and return ranked, licence-checked results."""
    import archive_sources as arc
    import visual_sourcing as vs

    q = " ".join(str(query or "").split())
    if len(q) < 2:
        raise AssetStoreError("Запрос должен содержать минимум 2 символа")
    want = kind if kind in {"any", "image", "video"} else "any"
    src_list = sources or ["wikimedia", "nasa", "openverse"]
    per_src = max(3, min(int(limit), 12))

    search_fn = {
        "wikimedia": arc.search_wikimedia,
        "nasa": arc.search_nasa,
        "openverse": arc.search_openverse,
        "archive_org": arc.search_archive_org,
    }

    pool: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for src in src_list:
        fn = search_fn.get(src)
        if fn is None:
            continue
        kinds_to_try = ["image", "video"] if want == "any" else [want]
        for k in kinds_to_try:
            if src == "openverse" and k == "video":
                continue
            try:
                raw = fn(q, k, per_src)
            except Exception as exc:
                errors.append({"source": src, "kind": k, "error": str(exc)})
                continue
            for c in raw:
                ok, _reason, score = vs.filter_candidate(q, c, want)
                if not ok:
                    continue
                asset_url = c.get("asset_url") or ""
                if not asset_url and src in {"nasa", "archive_org"}:
                    try:
                        c = arc.resolve_asset(c)
                        asset_url = c.get("asset_url") or ""
                    except Exception:
                        continue
                if not asset_url:
                    continue
                c_out = {
                    "source": c.get("source", src),
                    "source_id": c.get("source_id", ""),
                    "kind": c.get("kind", k),
                    "title": c.get("title", ""),
                    "creator": c.get("creator", ""),
                    "license": c.get("license", ""),
                    "license_url": c.get("license_url", ""),
                    "page_url": c.get("page_url", ""),
                    "asset_url": asset_url,
                    "thumb_url": c.get("thumb_url") or c.get("preview_url") or asset_url,
                    "width": c.get("width") or 0,
                    "height": c.get("height") or 0,
                    "score": score,
                    "needs_credit": c.get("license") in CREDIT_LICENCES,
                }
                pool.append(c_out)

    # Deduplicate by (source, source_id) and sort by score desc.
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for item in sorted(pool, key=lambda x: (-x["score"], x["source"], x["source_id"])):
        key = (item["source"], item["source_id"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return {
        "ok": True,
        "query": q,
        "kind": want,
        "results": deduped[: max(1, min(int(limit), 20))],
        "source_errors": errors,
    }
