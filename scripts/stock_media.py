"""DUP Presenter — free stock background video (Pexels / Pixabay), fail-closed.

Official free APIs only:
  - Pexels videos search: GET https://api.pexels.com/v1/videos/search  (header Authorization: KEY)
    Free key, 200 requests/hour. Attribution: show "Pexels" credit (we render it on-slide).
  - Pixabay videos search: GET https://pixabay.com/api/videos/          (param key=KEY)
    Free key. Attribution is requested, not required (we still render the author credit).

Keys live in secrets/media_keys.env (git-ignored) or env PEXELS_API_KEY / PIXABAY_API_KEY.
If a provider is selected and its key is missing, we RAISE. No silent fallback to another provider.
Downloads are cached under work/stock/ and never printed with the key.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SECRETS_ENV = ROOT / "secrets" / "media_keys.env"
CACHE_DIR = ROOT / "work" / "stock"
PUBLIC_STOCK_DIR = ROOT / "public" / "stock"

PEXELS_SEARCH = "https://api.pexels.com/v1/videos/search"
PIXABAY_SEARCH = "https://pixabay.com/api/videos/"
MAX_DOWNLOAD_BYTES = 80 * 1024 * 1024
QUERY_RE = re.compile(r"^[A-Za-z][A-Za-z \-]{1,59}$")
PROVIDERS = ("pexels", "pixabay")


class StockMediaError(RuntimeError):
    """Stock media could not be fetched; the build must stop."""


def load_media_keys() -> dict[str, str]:
    keys: dict[str, str] = {}
    if SECRETS_ENV.is_file():
        for raw in SECRETS_ENV.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.strip().strip('"').strip("'")
            if k.strip() in {"PEXELS_API_KEY", "PIXABAY_API_KEY"} and v:
                keys[k.strip()] = v
    for name in ("PEXELS_API_KEY", "PIXABAY_API_KEY"):
        if os.environ.get(name, "").strip():
            keys[name] = os.environ[name].strip()
    return keys


def validate_query(query: str) -> str:
    q = " ".join(str(query or "").split())
    if not QUERY_RE.match(q):
        raise StockMediaError(f"background_query {query!r} must be 2-60 latin letters/spaces/hyphens")
    return q


def _key_for(provider: str) -> str:
    if provider not in PROVIDERS:
        raise StockMediaError(f"Unknown stock provider {provider!r}; allowed: {list(PROVIDERS)}")
    name = "PEXELS_API_KEY" if provider == "pexels" else "PIXABAY_API_KEY"
    key = load_media_keys().get(name, "")
    if not key:
        raise StockMediaError(
            f"{name} is missing. Add it to secrets/media_keys.env (free key from {provider}.com) "
            f"or disable background video in the deck."
        )
    return key


def _pick_pexels_file(video: dict[str, Any], portrait: bool) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    for f in video.get("video_files") or []:
        w, h = int(f.get("width") or 0), int(f.get("height") or 0)
        if f.get("file_type") != "video/mp4" or not f.get("link"):
            continue
        if portrait and not (h >= 1280 and h >= w):
            continue
        if not portrait and not (w >= 1280 and w >= h):
            continue
        if best is None or abs((w * h) - 1920 * 1080) < abs((int(best["width"]) * int(best["height"])) - 1920 * 1080):
            best = f
    return best


def _pick_pixabay_file(hit: dict[str, Any], portrait: bool) -> dict[str, Any] | None:
    for size in ("large", "medium"):
        f = (hit.get("videos") or {}).get(size) or {}
        w, h = int(f.get("width") or 0), int(f.get("height") or 0)
        if not f.get("url") or w <= 0 or h <= 0:
            continue
        if portrait and h > w and h >= 1280:
            return {"link": f["url"], "width": w, "height": h}
        if not portrait and w > h and w >= 1280:
            return {"link": f["url"], "width": w, "height": h}
    return None


def search_clip(provider: str, query: str, aspect: str) -> dict[str, Any]:
    """Return {'id', 'url', 'author', 'page', 'provider', 'link', 'width', 'height'} for the best match."""
    import httpx

    q = validate_query(query)
    portrait = aspect == "9:16"
    key = _key_for(provider)
    orientation = "portrait" if portrait else "landscape"
    try:
        with httpx.Client(timeout=30.0) as client:
            if provider == "pexels":
                r = client.get(
                    PEXELS_SEARCH,
                    params={"query": q, "orientation": orientation, "size": "medium", "per_page": 15},
                    headers={"Authorization": key},
                )
                r.raise_for_status()
                for video in (r.json() or {}).get("videos") or []:
                    f = _pick_pexels_file(video, portrait)
                    if f:
                        return {
                            "id": str(video.get("id")),
                            "provider": "pexels",
                            "author": (video.get("user") or {}).get("name", "Unknown"),
                            "page": video.get("url", "https://www.pexels.com"),
                            "link": f["link"],
                            "width": int(f["width"]),
                            "height": int(f["height"]),
                        }
            else:
                r = client.get(
                    PIXABAY_SEARCH,
                    params={"key": key, "q": q, "per_page": 30, "safesearch": "true"},
                )
                r.raise_for_status()
                for hit in (r.json() or {}).get("hits") or []:
                    f = _pick_pixabay_file(hit, portrait)
                    if f:
                        return {
                            "id": str(hit.get("id")),
                            "provider": "pixabay",
                            "author": hit.get("user", "Unknown"),
                            "page": hit.get("pageURL", "https://pixabay.com"),
                            "link": f["link"],
                            "width": int(f["width"]),
                            "height": int(f["height"]),
                        }
    except httpx.HTTPStatusError as exc:
        raise StockMediaError(f"{provider} search HTTP {exc.response.status_code} for {q!r}") from exc
    except httpx.HTTPError as exc:
        raise StockMediaError(f"{provider} search failed for {q!r}: {type(exc).__name__}") from exc
    raise StockMediaError(f"No {orientation} HD clip found on {provider} for {q!r}")


def download_clip(clip: dict[str, Any]) -> Path:
    """Download to work/stock/<provider>/<id>.mp4 (cached). Returns local path."""
    import httpx

    target_dir = CACHE_DIR / clip["provider"]
    target_dir.mkdir(parents=True, exist_ok=True)
    tag = hashlib.sha1(f"{clip['id']}-{clip['width']}x{clip['height']}".encode()).hexdigest()[:12]
    path = target_dir / f"{clip['id']}_{tag}.mp4"
    if path.is_file() and path.stat().st_size > 100_000:
        return path
    tmp = path.with_suffix(".part")
    written = 0
    try:
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            with client.stream("GET", clip["link"]) as r:
                r.raise_for_status()
                with tmp.open("wb") as f:
                    for chunk in r.iter_bytes(1024 * 256):
                        written += len(chunk)
                        if written > MAX_DOWNLOAD_BYTES:
                            raise StockMediaError(f"Clip {clip['id']} exceeds {MAX_DOWNLOAD_BYTES // (1024 * 1024)} MB")
                        f.write(chunk)
    except httpx.HTTPError as exc:
        tmp.unlink(missing_ok=True)
        raise StockMediaError(f"Download failed for {clip['provider']} clip {clip['id']}: {type(exc).__name__}") from exc
    if written < 100_000:
        tmp.unlink(missing_ok=True)
        raise StockMediaError(f"Downloaded clip {clip['id']} is too small ({written} bytes)")
    tmp.replace(path)
    return path


def fetch_background(provider: str, query: str, aspect: str, slug: str, slide_id: str) -> dict[str, Any]:
    """Search, download and copy into public/stock/<slug>/<slide_id>.mp4 for Remotion staticFile()."""
    import shutil

    clip = search_clip(provider, query, aspect)
    cached = download_clip(clip)
    dest_dir = PUBLIC_STOCK_DIR / slug
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{slide_id}.mp4"
    shutil.copyfile(cached, dest)
    return {
        "video_file": f"stock/{slug}/{slide_id}.mp4",
        "credit": f"Video: {clip['author']} · {'Pexels' if clip['provider'] == 'pexels' else 'Pixabay'}",
        "credit_url": clip["page"],
        "provider": clip["provider"],
        "query": validate_query(query),
    }


def write_credits(slug: str, items: list[dict[str, Any]]) -> Path | None:
    """Write out/<slug>_credits.txt with author and source links for every stock clip used."""
    if not items:
        return None
    out = ROOT / "out" / f"{slug}_credits.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = ["Stock video credits (free licenses: Pexels / Pixabay)", ""]
    for it in items:
        lines.append(f"- slide {it['slide']}: {it['credit']} — {it['credit_url']}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def describe_for_log(obj: dict[str, Any]) -> str:
    return json.dumps({k: v for k, v in obj.items() if k != "link"}, ensure_ascii=False)
