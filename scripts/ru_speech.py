"""Russian TTS input normalization: Latin tokens become Russian phonetic spellings before Silero v5 RU.

Silero v5 RU has no Latin alphabet: it mumbles or drops tokens such as GitHub, KuCoin or dry_run.
We respell them deterministically. SSML tags and XML entities are passed through untouched.
"""

from __future__ import annotations

import re

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


def transliterate(token: str) -> str:
    """Known term -> dictionary spelling; unknown token -> letter-by-letter phonetic fallback."""
    key = token.lower()
    if key in LATIN_RU:
        return LATIN_RU[key]
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
