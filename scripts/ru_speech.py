"""Russian TTS input normalization: Latin tokens become Russian phonetic spellings before Silero v5 RU.

Silero v5 RU has no Latin alphabet: it mumbles or drops tokens such as GitHub, KuCoin or dry_run.
We respell them deterministically. SSML tags and XML entities are passed through untouched.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRONUNCIATION_CONFIG = ROOT / "config" / "pronunciation.json"

# Known terms from DUP projects. Keys are lowercase; matching is case-insensitive.
LATIN_RU: dict[str, str] = {
    "dup": "дап",
    "labs": "лабс",
    "radar": "радар",
    "market": "маркет",
    "python": "пайтон",
    "rust": "раст",
    "kucoin": "кукоин",
    "telegram": "телеграм",
    "github": "гитхаб",
    "api": "эй пи ай",
    "fastapi": "фаст эй пи ай",
    "usdt": "ю эс ди ти",
    "btc": "би ти си",
    "mtf": "эм ти эф",
    "kpi": "кей пи ай",
    "json": "джейсон",
    "url": "ю ар эл",
    "docker": "докер",
    "spot": "спот",
    "flush": "флаш",
    "push": "пуш",
    "ingest": "инжест",
    "native": "нейтив",
    "buy": "бай",
    "sell": "сэлл",
    "off": "офф",
    "dry_run": "драй ран",
    "baraggregator": "бар аггрегейтор",
    "split_equal_micros": "сплит экуал микрос",
    "uladzimir": "Владимир",
    "dabranski": "Добранский",
    "libp2p": "либ пи два пи",
    "pyo3": "пай о три",
    "tcp": "ти си пи",
    "tls": "ти эл эс",
    "mesh": "меш",
    "prod": "прод",
    "false": "фолс",
    "true": "тру",
    "top": "топ",
}

_LATIN_TO_CYR = {
    "a": "а", "b": "б", "c": "к", "d": "д", "e": "е", "f": "ф", "g": "г", "h": "х", "i": "и",
    "j": "дж", "k": "к", "l": "л", "m": "м", "n": "н", "o": "о", "p": "п", "q": "к", "r": "р",
    "s": "с", "t": "т", "u": "у", "v": "в", "w": "в", "x": "кс", "y": "и", "z": "з",
}

# Skip tags and entities; everything else that starts with a Latin letter is a token.
_TOKEN_RE = re.compile(r"<[^>]+>|&[#A-Za-z0-9]+;|[A-Za-z][A-Za-z0-9_]*")


def load_pronunciation_overrides() -> dict[str, str]:
    """Load user-editable pronunciation overrides from config/pronunciation.json (if present)."""
    if not PRONUNCIATION_CONFIG.is_file():
        return {}
    try:
        data = json.loads(PRONUNCIATION_CONFIG.read_text(encoding="utf-8"))
        raw = data.get("overrides") if isinstance(data, dict) else {}
        if not isinstance(raw, dict):
            return {}
        return {str(k).strip().lower(): str(v).strip() for k, v in raw.items() if str(k).strip() and str(v).strip()}
    except Exception:
        return {}


def save_pronunciation_overrides(overrides: dict[str, str]) -> Path:
    """Persist validated user pronunciation overrides to config/pronunciation.json."""
    clean = {
        str(k).strip().lower(): str(v).strip()
        for k, v in overrides.items()
        if str(k).strip() and str(v).strip()
    }
    PRONUNCIATION_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_comment": "Custom Russian TTS pronunciation overrides (lowercase token -> Cyrillic phonetic spelling). Edited via console or directly.",
        "overrides": dict(sorted(clean.items())),
    }
    PRONUNCIATION_CONFIG.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return PRONUNCIATION_CONFIG


def get_latin_ru() -> dict[str, str]:
    """Merged pronunciation dictionary (built-in LATIN_RU + live config/pronunciation.json overrides)."""
    merged = dict(LATIN_RU)
    merged.update(load_pronunciation_overrides())
    return merged


def transliterate(token: str) -> str:
    """Known term -> dictionary spelling; unknown token -> letter-by-letter phonetic fallback."""
    key = token.lower()
    table = get_latin_ru()
    if key in table:
        return table[key]
    parts = token.replace("_", " ").split(" ")
    out = []
    for part in parts:
        res = []
        i = 0
        low = part.lower()
        while i < len(low):
            pair = low[i:i + 2]
            if pair in ("sh", "ch", "th", "ph", "ck", "ee", "oo"):
                res.append({"sh": "ш", "ch": "ч", "th": "т", "ph": "ф", "ck": "к", "ee": "и", "oo": "у"}[pair])
                i += 2
                continue
            res.append(_LATIN_TO_CYR.get(low[i], low[i]))
            i += 1
        out.append("".join(res))
    return " ".join(p for p in out if p)


def normalize_ru_ssml(payload: str) -> str:
    """Replace Latin tokens in SSML/plain text; tags and entities are preserved byte-for-byte."""

    def repl(match: re.Match[str]) -> str:
        text = match.group(0)
        if text.startswith("<") or text.startswith("&"):
            return text
        return transliterate(text)

    return _TOKEN_RE.sub(repl, payload)
