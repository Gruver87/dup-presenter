"""DUP Presenter — free archive providers for visual sourcing (fail-closed).

Four free public archives. NONE of them needs an API key:
  - NASA Images        https://images-api.nasa.gov/search           (images + video, NASA media guidelines)
  - Wikimedia Commons  https://commons.wikimedia.org/w/api.php      (images + webm video, per-file licence)
  - Internet Archive   https://archive.org/advancedsearch.php       (movies + images, per-item licence URL)
  - Openverse          https://api.openverse.org/v1/images/         (images only, aggregated CC licences)

Licence policy (fail-closed): only CC0, Public Domain Mark, CC BY, CC BY-SA and NASA media are
accepted. Any NC / ND / unknown / missing licence is rejected. Each candidate carries its licence,
licence URL, creator and source page so that attribution can be written out.

Providers only SEARCH and describe candidates. Asset URLs are resolved lazily (`resolve_asset`)
for the few candidates that survive filtering, so that we do not hammer archives with per-item calls.
Every network failure raises `ArchiveSourceError`; callers record it. Nothing is swallowed.
"""

from __future__ import annotations

import html
import re
from typing import Any, Callable
from urllib.parse import quote, urlsplit

import httpx

# Wikimedia's robot policy returns 403 to generic agents; a descriptive UA with a project URL is accepted.
USER_AGENT = "DUP-Presenter/1.0 (https://github.com/Gruver87/dup-presenter; visual sourcing) httpx/0.28"
HTTP_TIMEOUT_SEC = 25.0

NASA_SEARCH = "https://images-api.nasa.gov/search"
NASA_ASSET = "https://images-api.nasa.gov/asset/{nasa_id}"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
ARCHIVE_SEARCH = "https://archive.org/advancedsearch.php"
ARCHIVE_META = "https://archive.org/metadata/{identifier}"
ARCHIVE_DOWNLOAD = "https://archive.org/download/{identifier}/{name}"
OPENVERSE_IMAGES = "https://api.openverse.org/v1/images/"

SOURCES = ("nasa", "wikimedia", "archive_org", "openverse")
ALLOWED_LICENSES = frozenset({"cc0", "pdm", "by", "by-sa", "nasa-media"})
# Hosts that the asset download may be redirected to for the sources that have a known host set.
# Openverse links point to many third-party origins, so for it only https + magic bytes + size apply.
ASSET_HOST_SUFFIXES: dict[str, tuple[str, ...]] = {
    "nasa": ("images-assets.nasa.gov", "images-api.nasa.gov", "nasa.gov"),
    "wikimedia": ("upload.wikimedia.org",),
    "archive_org": ("archive.org",),
}

_LICENSE_URL_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"creativecommons\.org/publicdomain/zero/1\.0"), "cc0"),
    (re.compile(r"creativecommons\.org/publicdomain/mark/1\.0"), "pdm"),
    (re.compile(r"creativecommons\.org/licenses/by-sa/[\d.]+/?$"), "by-sa"),
    (re.compile(r"creativecommons\.org/licenses/by/[\d.]+/?$"), "by"),
)
_LICENSE_NAME_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^(cc0|cc0 1\.0|cc zero)$"), "cc0"),
    (re.compile(r"^(public domain mark|public domain mark 1\.0|pdm|public domain|pd)$"), "pdm"),
    (re.compile(r"^cc[ -]by[ -]sa( \d\.\d)?$"), "by-sa"),
    (re.compile(r"^cc[ -]by( \d\.\d)?$"), "by"),
)


class ArchiveSourceError(RuntimeError):
    """A provider request failed or returned an unusable response."""


# --------------------------------------------------------------------------- HTTP


def http_json(url: str, params: dict[str, Any] | None = None) -> Any:
    """GET a JSON document over https with TLS verification on. Raises ArchiveSourceError."""
    if not url.startswith("https://"):
        raise ArchiveSourceError(f"refusing non-https URL for {urlsplit(url).netloc or url!r}")
    host = urlsplit(url).netloc
    try:
        with httpx.Client(
            timeout=HTTP_TIMEOUT_SEC, headers={"User-Agent": USER_AGENT}, follow_redirects=True, verify=True
        ) as client:
            r = client.get(url, params=params)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as exc:
        raise ArchiveSourceError(f"{host} answered HTTP {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise ArchiveSourceError(f"{host} request failed: {type(exc).__name__}") from exc
    except ValueError as exc:
        raise ArchiveSourceError(f"{host} returned non-JSON content") from exc


def _strip_html(text: object) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", str(text or ""))).split())


# --------------------------------------------------------------------------- licences


def normalize_license(*, url: str = "", name: str = "") -> str | None:
    """Map a licence URL or short name to an allowed key, or None (reject).

    A licence URL, when present, is authoritative: a URL that matches no allowed pattern
    (e.g. ...by-nc-sa...) is rejected even if the name looks permissive.
    """
    u = (url or "").strip().lower()
    if u:
        for pattern, key in _LICENSE_URL_PATTERNS:
            if pattern.search(u):
                return key
        return None
    n = " ".join((name or "").strip().lower().replace("_", " ").split())
    for pattern, key in _LICENSE_NAME_PATTERNS:
        if pattern.match(n):
            return key
    return None


# --------------------------------------------------------------------------- candidate shape


def _candidate(
    *,
    source: str,
    source_id: str,
    kind: str,
    title: str,
    description: str,
    keywords: list[str],
    creator: str,
    license_key: str | None,
    license_url: str,
    page_url: str,
    asset_url: str | None,
    width: int | None,
    height: int | None,
    duration_sec: float | None = None,
) -> dict[str, Any]:
    return {
        "source": source,
        "source_id": source_id,
        "kind": kind,
        "title": title[:300],
        "description": description[:1000],
        "keywords": keywords[:40],
        "creator": (creator or "Unknown")[:200],
        "license": license_key,
        "license_url": license_url,
        "attribution_required": license_key != "cc0" and license_key != "pdm",
        "page_url": page_url,
        "asset_url": asset_url,
        "width": width,
        "height": height,
        "duration_sec": duration_sec,
    }


# --------------------------------------------------------------------------- NASA


def search_nasa(query: str, kind: str, limit: int) -> list[dict[str, Any]]:
    data = http_json(NASA_SEARCH, {"q": query, "media_type": "video" if kind == "video" else "image", "page_size": limit})
    items = (((data or {}).get("collection") or {}).get("items")) or []
    out: list[dict[str, Any]] = []
    for item in items:
        meta = (item.get("data") or [{}])[0]
        nasa_id = str(meta.get("nasa_id") or "")
        if not nasa_id:
            continue
        out.append(
            _candidate(
                source="nasa",
                source_id=nasa_id,
                kind=kind,
                title=str(meta.get("title") or ""),
                description=_strip_html(meta.get("description")),
                keywords=[str(k) for k in (meta.get("keywords") or []) if isinstance(k, str)],
                creator=str(meta.get("photographer") or meta.get("center") or "NASA"),
                license_key="nasa-media",
                license_url="https://www.nasa.gov/nasa-brand-center/images-and-media/",
                page_url=f"https://images.nasa.gov/details/{quote(nasa_id)}",
                asset_url=None,
                width=None,
                height=None,
            )
        )
    return out


def _pick_nasa_asset(hrefs: list[str], kind: str) -> str | None:
    """Prefer ~large, then ~medium, then ~orig (size-capped later). Only the right extension family."""
    exts = (".mp4",) if kind == "video" else (".jpg", ".jpeg", ".png")
    for tag in ("~large", "~medium", "~orig"):
        for href in hrefs:
            low = href.lower()
            if tag in low and low.endswith(exts) and href.startswith("https://"):
                return href
    return None


def resolve_nasa_asset(candidate: dict[str, Any]) -> dict[str, Any]:
    data = http_json(NASA_ASSET.format(nasa_id=quote(candidate["source_id"])))
    hrefs = [str(i.get("href") or "") for i in ((data or {}).get("collection") or {}).get("items") or []]
    asset = _pick_nasa_asset(hrefs, candidate["kind"])
    if not asset:
        raise ArchiveSourceError(f"NASA {candidate['source_id']}: no {candidate['kind']} asset file in manifest")
    return {**candidate, "asset_url": asset}


# --------------------------------------------------------------------------- Wikimedia Commons


def search_wikimedia(query: str, kind: str, limit: int) -> list[dict[str, Any]]:
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": 6,
        "gsrlimit": limit,
        "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata",
        "format": "json",
        "formatversion": 2,
    }
    data = http_json(COMMONS_API, params)
    pages = (((data or {}).get("query") or {}).get("pages")) or []
    out: list[dict[str, Any]] = []
    for page in pages:
        infos = page.get("imageinfo") or []
        if not infos:
            continue
        info = infos[0]
        mime = str(info.get("mime") or "")
        if kind == "image" and not mime.startswith("image/"):
            continue
        if kind == "video" and mime != "video/webm":
            continue
        ext = (info.get("extmetadata") or {})

        def _val(key: str) -> str:
            return _strip_html(((ext.get(key) or {}).get("value")) or "")

        title = str(page.get("title") or "").removeprefix("File:")
        out.append(
            _candidate(
                source="wikimedia",
                source_id=str(page.get("pageid") or title),
                kind=kind,
                title=title,
                description=_val("ImageDescription") or _val("ObjectName"),
                keywords=[],
                creator=_val("Artist") or "Wikimedia Commons contributor",
                license_key=normalize_license(
                    url=_val("LicenseUrl"), name="" if _val("LicenseUrl") else _val("LicenseShortName")
                ),
                license_url=_val("LicenseUrl"),
                page_url=str(info.get("descriptionurl") or ""),
                asset_url=str(info.get("url") or "") or None,
                width=int(info["width"]) if info.get("width") else None,
                height=int(info["height"]) if info.get("height") else None,
            )
        )
    return out


# --------------------------------------------------------------------------- Internet Archive


def search_archive_org(query: str, kind: str, limit: int) -> list[dict[str, Any]]:
    mediatype = "movies" if kind == "video" else "image"
    params = {
        # Server-side licence pre-filter (CC/PD only, no NC/ND); the client-side check still runs.
        "q": f"({query}) AND mediatype:{mediatype} AND licenseurl:(*creativecommons*) "
        f"AND NOT licenseurl:(*-nc*) AND NOT licenseurl:(*-nd*)",
        "fl[]": ["identifier", "title", "description", "creator", "licenseurl", "mediatype"],
        "rows": limit,
        "page": 1,
        "output": "json",
    }
    data = http_json(ARCHIVE_SEARCH, params)
    docs = (((data or {}).get("response")) or {}).get("docs") or []
    out: list[dict[str, Any]] = []
    for doc in docs:
        identifier = str(doc.get("identifier") or "")
        if not identifier:
            continue
        lic_url = str(doc.get("licenseurl") or "")
        creator = doc.get("creator")
        if isinstance(creator, list):
            creator = creator[0] if creator else ""
        out.append(
            _candidate(
                source="archive_org",
                source_id=identifier,
                kind=kind,
                title=str(doc.get("title") or identifier),
                description=_strip_html(doc.get("description") if isinstance(doc.get("description"), str) else ""),
                keywords=[],
                creator=str(creator or "Internet Archive contributor"),
                license_key=normalize_license(url=lic_url),
                license_url=lic_url,
                page_url=f"https://archive.org/details/{quote(identifier)}",
                asset_url=None,
                width=None,
                height=None,
            )
        )
    return out


def resolve_archive_org_asset(candidate: dict[str, Any]) -> dict[str, Any]:
    """Pick the best file from the item metadata; re-check the licence from the authoritative metadata."""
    data = http_json(ARCHIVE_META.format(identifier=quote(candidate["source_id"])))
    meta = (data or {}).get("metadata") or {}
    lic_url = str(meta.get("licenseurl") or candidate.get("license_url") or "")
    lic = normalize_license(url=lic_url)
    if lic is None:
        raise ArchiveSourceError(f"archive.org {candidate['source_id']}: licence not allowed ({lic_url or 'none'})")
    files = (data or {}).get("files") or []
    best: dict[str, Any] | None = None
    for f in files:
        name = str(f.get("name") or "")
        fmt = str(f.get("format") or "").lower()
        w, h = _int_or_none(f.get("width")), _int_or_none(f.get("height"))
        if candidate["kind"] == "video":
            is_h264 = ("h.264" in fmt) or ("mpeg4" in fmt)
            if not (name.lower().endswith(".mp4") and is_h264):
                continue
        else:
            if not name.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
        if w is None or h is None:
            continue
        if best is None or w * h > int(best["w"]) * int(best["h"]):
            best = {"name": name, "w": w, "h": h}
    if best is None:
        raise ArchiveSourceError(f"archive.org {candidate['source_id']}: no suitable {candidate['kind']} file with known size")
    url = ARCHIVE_DOWNLOAD.format(identifier=quote(candidate["source_id"]), name=quote(best["name"]))
    return {**candidate, "license": lic, "license_url": lic_url, "asset_url": url, "width": best["w"], "height": best["h"]}


# --------------------------------------------------------------------------- Openverse


def search_openverse(query: str, kind: str, limit: int) -> list[dict[str, Any]]:
    if kind != "image":
        return []  # Openverse indexes images only; this is recorded by the caller, not hidden.
    params = {"q": query, "license": "cc0,pdm,by,by-sa", "page_size": limit, "mature": "false"}
    data = http_json(OPENVERSE_IMAGES, params)
    out: list[dict[str, Any]] = []
    for it in (data or {}).get("results") or []:
        lic_key = normalize_license(url=str(it.get("license_url") or "")) or normalize_license(
            name=str(it.get("license") or "")
        )
        tags = [str(t.get("name")) for t in (it.get("tags") or []) if isinstance(t, dict) and t.get("name")]
        out.append(
            _candidate(
                source="openverse",
                source_id=str(it.get("id") or ""),
                kind="image",
                title=str(it.get("title") or ""),
                description=_strip_html(it.get("description")),
                keywords=tags,
                creator=str(it.get("creator") or "Openverse contributor"),
                license_key=lic_key,
                license_url=str(it.get("license_url") or ""),
                page_url=str(it.get("foreign_landing_url") or it.get("detail_url") or ""),
                asset_url=str(it.get("url") or "") or None,
                width=_int_or_none(it.get("width")),
                height=_int_or_none(it.get("height")),
            )
        )
    return out


def _int_or_none(value: object) -> int | None:
    try:
        n = int(str(value))
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


# --------------------------------------------------------------------------- registry

SEARCHERS: dict[str, Callable[[str, str, int], list[dict[str, Any]]]] = {
    "nasa": search_nasa,
    "wikimedia": search_wikimedia,
    "archive_org": search_archive_org,
    "openverse": search_openverse,
}


def resolve_asset(candidate: dict[str, Any]) -> dict[str, Any]:
    """Return the candidate with a concrete https asset_url, or raise ArchiveSourceError."""
    if candidate.get("asset_url"):
        return candidate
    src = candidate["source"]
    if src == "nasa":
        return resolve_nasa_asset(candidate)
    if src == "archive_org":
        return resolve_archive_org_asset(candidate)
    raise ArchiveSourceError(f"{src}: asset_url missing and no resolver")


def asset_host_allowed(source: str, url: str) -> bool:
    """https-only; for sources with a known host set the host must match it."""
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        return False
    suffixes = ASSET_HOST_SUFFIXES.get(source)
    if suffixes is None:
        return True
    host = parts.hostname.lower()
    return any(host == s or host.endswith("." + s) for s in suffixes)
