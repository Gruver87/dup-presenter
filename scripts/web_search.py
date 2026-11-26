"""Fail-closed web search client for DUP Presenter Idea Engine (Serper / Brave).

Supports two providers selected by environment variables:
  1. SERPER_API_KEY -> https://google.serper.dev/search
  2. BRAVE_API_KEY  -> https://api.search.brave.com/res/v1/web/search

Fail-closed policy:
  - If neither key is configured, raises WebSearchError (never silently falls back).
  - Non-200 HTTP responses, timeouts, or malformed payloads raise WebSearchError.
  - TLS verification is always enabled.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

SERPER_URL = "https://google.serper.dev/search"
BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
DEFAULT_TIMEOUT_SEC = 10.0
DEFAULT_LIMIT = 6
MAX_PROMPT_CHARS = 2200


class WebSearchError(RuntimeError):
    """Raised when web search is requested but unavailable or fails (fail-closed)."""


def configured_provider() -> str | None:
    """Return 'serper', 'brave', or None based on environment variables."""
    if os.environ.get("SERPER_API_KEY", "").strip():
        return "serper"
    if os.environ.get("BRAVE_API_KEY", "").strip():
        return "brave"
    return None


def _clean_text(text: Any, limit: int = 280) -> str:
    s = " ".join(str(text or "").split())
    return s[:limit]


def _search_serper(query: str, *, lang: str, limit: int, timeout: float) -> list[dict[str, str]]:
    api_key = os.environ.get("SERPER_API_KEY", "").strip()
    if not api_key:
        raise WebSearchError("SERPER_API_KEY is not set")
    payload = {"q": query, "num": limit, "hl": "ru" if lang == "ru" else "en"}
    req = urllib.request.Request(
        SERPER_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "X-API-KEY": api_key,
            "Content-Type": "application/json",
            "User-Agent": "DUP-Presenter/1.3",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise WebSearchError(f"Serper search request failed: {exc}") from exc

    organic = data.get("organic")
    if not isinstance(organic, list):
        raise WebSearchError("Serper response missing 'organic' results list")
    out: list[dict[str, str]] = []
    for item in organic[:limit]:
        if not isinstance(item, dict):
            continue
        url = str(item.get("link") or "").strip()
        title = _clean_text(item.get("title"), 160)
        snippet = _clean_text(item.get("snippet"), 280)
        if title and url:
            out.append({"title": title, "snippet": snippet, "url": url})
    return out


def _search_brave(query: str, *, lang: str, limit: int, timeout: float) -> list[dict[str, str]]:
    api_key = os.environ.get("BRAVE_API_KEY", "").strip()
    if not api_key:
        raise WebSearchError("BRAVE_API_KEY is not set")
    params = urllib.parse.urlencode({
        "q": query,
        "count": limit,
        "search_lang": "ru" if lang == "ru" else "en",
    })
    req = urllib.request.Request(
        f"{BRAVE_URL}?{params}",
        headers={
            "Accept": "application/json",
            "X-Subscription-Token": api_key,
            "User-Agent": "DUP-Presenter/1.3",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise WebSearchError(f"Brave search request failed: {exc}") from exc

    results = ((data.get("web") or {}).get("results")) if isinstance(data, dict) else None
    if not isinstance(results, list):
        raise WebSearchError("Brave response missing 'web.results' list")
    out: list[dict[str, str]] = []
    for item in results[:limit]:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        title = _clean_text(item.get("title"), 160)
        snippet = _clean_text(item.get("description"), 280)
        if title and url:
            out.append({"title": title, "snippet": snippet, "url": url})
    return out


def search_snippets(
    query: str,
    *,
    lang: str = "ru",
    limit: int = DEFAULT_LIMIT,
    provider: str = "auto",
    timeout: float = DEFAULT_TIMEOUT_SEC,
) -> dict[str, Any]:
    """Run a fail-closed web search and return {'provider': str, 'query': str, 'results': list}."""
    q = " ".join(str(query or "").split())
    if len(q) < 2:
        raise WebSearchError("Search query must be at least 2 characters")
    capped = max(1, min(int(limit), 10))

    chosen = provider.strip().lower() if provider else "auto"
    if chosen == "auto":
        chosen = configured_provider() or ""
    if not chosen:
        raise WebSearchError(
            "Веб-поиск требует ключ SERPER_API_KEY или BRAVE_API_KEY в переменных окружения (fail-closed)."
        )
    if chosen == "serper":
        results = _search_serper(q, lang=lang, limit=capped, timeout=timeout)
    elif chosen == "brave":
        results = _search_brave(q, lang=lang, limit=capped, timeout=timeout)
    else:
        raise WebSearchError(f"Unsupported web search provider {provider!r}; expected 'serper', 'brave', or 'auto'")

    if not results:
        raise WebSearchError(f"Web search ({chosen}) returned 0 results for {q!r}")
    return {"provider": chosen, "query": q, "results": results}


def format_snippets_for_prompt(results: list[dict[str, str]], *, max_chars: int = MAX_PROMPT_CHARS) -> str:
    """Format normalized web snippets into a bounded context block for LLM prompts."""
    lines: list[str] = []
    used = 0
    for idx, item in enumerate(results, start=1):
        line = f"[{idx}] {item.get('title', '')} — {item.get('snippet', '')} ({item.get('url', '')})"
        if used + len(line) + 1 > max_chars and lines:
            break
        lines.append(line)
        used += len(line) + 1
    return "\n".join(lines)
