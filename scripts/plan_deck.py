"""DUP Presenter - deck planner (local LLM via Ollama).

The model only chooses what to say and which sources to cite. It never writes
code: code excerpts are read from the project files by line range, after
redaction. Every plan is validated fail-closed; invalid plans are repaired once
per attempt with the concrete validation errors, then the run fails.

Versions live in work/<slug>/versions/vN.json (plan), deck is assembled to decks/<slug>.json.

Usage:
    python scripts/plan_deck.py --slug radar --facts work/radar/facts.json
    python scripts/plan_deck.py --slug radar --feedback "больше про paper-режим, меньше кода"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from analyze_project import read_lines, redact_line  # noqa: E402
from stock_media import StockMediaError, validate_query  # noqa: E402
from ru_speech import LATIN_RU  # noqa: E402

OLLAMA_HOST = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen2.5:7b"
NUM_CTX = 12288
MAX_ATTEMPTS = 3
FACTS_BUDGET_CHARS = 18_000
CODE_MAX_SPAN = 14
CODE_LINE_CAP = 110
PALETTE = ["#00f5d4", "#38bdf8", "#c084fc", "#f472b6"]
SLIDE_TYPES = {"hero_3d", "code_split", "screen_split", "arch_flow", "timeline", "terminal", "kpi", "quote", "outro_3d"}
CODE_TYPES = {"code_split", "terminal"}
from theme_catalog import THEME_IDS as THEMES  # noqa: E402
ASPECTS = {"16:9": (1920, 1080), "9:16": (1080, 1920)}
VOICE_BLOCK_RU = {
    "engine": "edge_tts", "lang": "ru", "speaker": "dmitry", "fallback_speaker": "eugene",
    "rate": "95%", "ambient_volume": 0.16,
}
VOICE_BLOCK_EN = {"engine": "kokoro_v1", "lang": "en", "speaker": "am_michael", "rate": "95%", "ambient_volume": 0.16}

SYSTEM_PROMPT_EN = """You are an editor of short technical presentations about an engineering project. Write strictly in English.

Hard rules:
1. Use ONLY facts from FACTS. Never invent numbers, files, functions, statuses, audits, or mainnet claims.
2. Preserve caveats from FACTS ("R&D", "paper", "dry_run", "not audited", "experimental").
3. Every slide lists source_ids — IDs of facts (D*, C*, I*) it is based on.
4. NEVER write code. For code_split set code_ref: {"symbol": "name"} — ONE symbol name copied verbatim from SYMBOLS. Every code_split must use a unique symbol. Title, subtitle, and bullets of code_split must describe that symbol.
5. Screenshots: screen_split and screen_ids are allowed ONLY if section I has images. If section I is empty, do not use screen_split.
6. ALL text (title, subtitle, bullets, voice_text) must be in clear English. voice_text is 2-3 short spoken sentences, no markdown, no emoji, no lists.
7. Limits: title <= 6 words; subtitle <= 12 words; up to 3 bullets; bullet.title <= 5 words; bullet.desc <= 14 words.
8. Structure: first slide hero_3d, last slide outro_3d, middle slides code_split, arch_flow (architecture diagram, up to 1 slide), screen_split, timeline (2-6 bullets = ordered steps taken from FACTS, e.g. roadmap or pipeline stages) and/or terminal (same code_ref rule as code_split, shown as a typed terminal), kpi (rule 12).
9. For arch_flow set arch: {"nodes": [{"id": "n1", "label": "Module", "path": "exact path from C"}], "edges": [{"from": "n1", "to": "n2", "label": "flow"}]}. 3-6 nodes; every path MUST match a real path from section C or D.
10. Reply with JSON ONLY matching the schema.
11. background_query (optional): 2-4 English words describing a free stock video for the slide, e.g. "server room" or "code on screen". Latin letters and spaces only; empty string if no fit.
12. kpi slide: kpis = 1-4 items {"value": "...", "label": "...", "quote": "..."}. value is a measurable identifier, count, size, version, or duration. quote is one EXACT sentence copied from FACTS that contains the value; the value must refer to the same thing as the label. Never round, compute, or invent. KPI labels must NOT claim health, soak, audit, pass/fail, mainnet, production, stable or proven; put such claims in bullets with source_ids. If FACTS has no fitting numbers, do not use kpi.
13. quote slide: title is ONE EXACT sentence copied verbatim from FACTS (at most 220 characters), shown as a quotation; subtitle is the source name (for example README or a file path from FACTS). Never paraphrase or invent a quote. The same claim rules as KPI apply: no health, soak, audit, pass/fail, mainnet, production, stable or proven statements in a quote. If no suitable sentence exists, do not use quote.

JSON schema:
{
  "title": "short presentation title",
  "brand": "BRAND IN CAPS up to 3 words",
  "slides": [
    {
      "type": "hero_3d | code_split | screen_split | arch_flow | timeline | terminal | kpi | quote | outro_3d",
      "tag": "TAG IN CAPS up to 3 words",
      "title": "...",
      "subtitle": "...",
      "bullets": [{"title": "...", "desc": "..."}],
      "code_ref": null,
      "screen_ids": [],
      "arch": null,
      "kpis": [{"value": "...", "label": "...", "quote": "exact sentence from FACTS"}],
      "voice_text": "...",
      "background_query": "2-4 english words or empty",
      "source_ids": ["D1"]
    }
  ]
}
"""

SYSTEM_PROMPT = """Ты редактор коротких обзорных презентаций об инженерном проекте. Ты пишешь по-русски.

Жёсткие правила:
1. Используй ТОЛЬКО факты из раздела FACTS. Не выдумывай цифры, файлы, функции, статусы, метрики, аудит, mainnet, продакшен.
2. Если в фактах написано «R&D», «paper», «dry_run», «не аудит», «экспериментально» — сохраняй эту оговорку.
3. Каждый слайд перечисляет source_ids — ID фактов (D*, C*, I*), на которых он основан.
4. Код НЕ пиши. Для показа кода в code_split укажи code_ref: {"symbol": "имя"} — имя ОДНОГО символа строго из раздела SYMBOLS. Копируй имя дословно. Каждый code_split — свой символ, символы не повторяются между слайдами.
   Заголовок, подзаголовок и буллеты code_split-слайда должны описывать то, что сделано в символе (см. doc в SYMBOLS). Если doc нет — описывай только имя и путь файла, без выдуманных деталей.
5. Скриншоты: screen_split и screen_ids допустимы ТОЛЬКО если в разделе I есть изображения. Если раздел I пуст — screen_split не используй.
6. ВЕСЬ текст на русском: title, subtitle, bullets, voice_text. Латиница только в названиях технологий и команд (KuCoin, Python, Rust, API, Docker). voice_text — 2–3 коротких предложения для озвучки, без markdown, без эмодзи, без списков. В voice_text ВСЕ английские слова пиши кириллицей, как произносятся: GitHub → гитхаб, Radar → радар, Telegram → телеграм. Не переводи английские термины через транслитерацию-кашу: watchlist → список наблюдения, ingest → загрузка данных, native → нативный, scoring → скоринг, dashboard → дашборд, alert → алерт.
7. Лимиты: title до 6 слов; subtitle до 12 слов; до 3 bullets; bullet.title до 5 слов; bullet.desc до 14 слов.
8. Структура: первый слайд hero_3d, последний outro_3d, между ними code_split, arch_flow (схема модулей проекта — до 1 слайда), screen_split, timeline (2–6 bullets = шаги по фактам, например этапы конвейера или дорожная карта) и/или terminal (то же правило code_ref, что у code_split, показывается как печатающийся терминал).
9. Для arch_flow заполни arch: {"nodes": [{"id": "n1", "label": "Название", "path": "путь из C"}], "edges": [{"from": "n1", "to": "n2", "label": "связь"}]}. 3–6 узлов, path — ТОЛЬКО реальный путь файла из раздела C или D.
10. Ответ — ТОЛЬКО JSON по схеме, без пояснений.
11. background_query (необязательно): 2–4 английских слова для бесплатного стокового видео к слайду, например "server room" или "code on screen". Только латиница и пробелы; пустая строка, если подходящего нет.
12. kpi-слайд: kpis = 1–4 элемента {"value": "...", "label": "...", "quote": "..."}. value — измеряемый идентификатор, количество, размер, версия или длительность. quote — ОДНО точное предложение из FACTS, содержащее value; value должно относиться именно к тому, что написано в label. Не округляй, не вычисляй, не выдумывай. В label kpi НЕ пиши заявления о здоровье, soak, аудите, pass/fail, mainnet, production, stable, proven — такие утверждения выноси в bullets с source_ids. Если подходящих чисел в FACTS нет — kpi не используй.
13. quote-слайд: title — ОДНО точное предложение из FACTS, дословно (не длиннее 220 символов), показывается как цитата; subtitle — название источника (например README или путь к файлу из FACTS). Не перефразируй и не выдумывай цитату. Для quote действуют те же запреты, что и для kpi: никаких заявлений о здоровье, soak, аудите, pass/fail, mainnet, production, stable, proven. Если подходящего предложения нет — quote не используй.

Схема JSON:
{
  "title": "короткое название ролика",
  "brand": "БРЕНД КАПСОМ до 3 слов",
  "slides": [
    {
      "type": "hero_3d | code_split | screen_split | arch_flow | timeline | terminal | kpi | quote | outro_3d",
      "tag": "МЕТКА КАПСОМ до 3 слов",
      "title": "...",
      "subtitle": "...",
      "bullets": [{"title": "...", "desc": "..."}],
      "code_ref": null,
      "screen_ids": [],
      "arch": null,
      "kpis": [{"value": "...", "label": "...", "quote": "exact sentence from FACTS"}],
      "voice_text": "...",
      "background_query": "2-4 english words or empty",
      "source_ids": ["D1"]
    }
  ]
}
Для code_split: code_ref обязателен. Для screen_split: screen_ids обязательны. Для arch_flow: arch обязателен. Для kpi: kpis обязателен (1–4 элемента с точными числами из FACTS). Для quote: title — точное предложение из FACTS, subtitle — источник. Для остальных типов эти поля = null или [].
"""


class PlanError(RuntimeError):
    """Raised when the planner cannot produce a valid plan."""


def symbol_index(facts: dict) -> dict[str, dict]:
    """Map symbol name -> {file_id, path, start, end}. First occurrence wins (facts order)."""
    index: dict[str, dict] = {}
    for c in facts["code"]:
        for s in c["symbols"]:
            index.setdefault(s["name"], {
                "file": c["id"], "path": c["path"], "start": s["start"], "end": s["end"], "doc": s.get("doc", ""),
            })
    return index


def render_facts(facts: dict) -> str:
    head = [
        f"PROJECT: {facts['project']['name']}",
        f"DESCRIPTION: {facts['project']['description'] or 'none'}",
        f"GITHUB_URLS: {', '.join(facts.get('urls', [])) or 'none'}",
    ]
    symbols = [
        f"- {name} [{v['file']} {v['path']} L{v['start']}-{v['end']}] doc: {v['doc'] or 'none'}"
        for name, v in list(symbol_index(facts).items())[:50]
    ]
    code_lines = [f"[{c['id']}] {c['path']} ({c['line_count']} lines) - {c['summary'] or 'no summary'}" for c in facts["code"][:30]]
    images = [f"[{i['id']}] image {i['path']}" for i in facts["images"]]
    tail = (
        "\n\n=== SYMBOLS (the only valid code_ref.symbol values) ===\n" + ("\n".join(symbols) or "none")
        + "\n\n=== C: CODE FILES ===\n" + "\n".join(code_lines)
        + "\n\n=== I: IMAGES ===\n" + ("\n".join(images) or "none")
    )
    docs = "\n\n".join(f"[{d['id']}] {d['path']} (lines {d['lines']})\n{d['text']}" for d in facts["docs"])
    head_text = "=== FACTS ===\n" + "\n".join(head) + "\n\n"
    docs_room = FACTS_BUDGET_CHARS - len(head_text) - len(tail)
    if len(docs) > docs_room:
        print(f"[plan] WARNING docs trimmed {len(docs)} -> {max(docs_room, 0)} chars", file=sys.stderr)
        docs = docs[: max(docs_room, 0)] + "\n...[docs truncated]"
    return head_text + docs + tail


def openai_compatible_chat(messages: list[dict], model_override: str = "") -> str:
    """Cloud provider over the OpenAI-compatible chat API.

    Configuration comes only from environment variables (never from code or chat):
      DUP_LLM_BASE_URL  e.g. https://api.deepseek.com/v1 (must be https)
      DUP_LLM_MODEL     provider model id (can be overridden via --model)
      DUP_LLM_API_KEY   secret key; the process refuses to run without it
    """
    base = os.environ.get("DUP_LLM_BASE_URL", "").rstrip("/")
    model = (model_override or os.environ.get("DUP_LLM_MODEL", "")).strip()
    key = os.environ.get("DUP_LLM_API_KEY", "")
    if not base or not model or not key:
        raise PlanError("Cloud provider is not configured: set DUP_LLM_BASE_URL, DUP_LLM_MODEL and DUP_LLM_API_KEY.")
    if not base.startswith("https://"):
        raise PlanError("DUP_LLM_BASE_URL must use https:// (TLS verification is always on).")
    body = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise PlanError(f"Cloud provider returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise PlanError(f"Cloud provider unreachable: {exc.reason}") from exc
    return payload["choices"][0]["message"]["content"]


def ollama_chat(model: str, messages: list[dict], host: str) -> str:
    body = json.dumps({
        "model": model,
        "messages": messages,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.2, "num_ctx": NUM_CTX},
    }).encode("utf-8")
    req = urllib.request.Request(f"{host}/api/chat", data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=3600) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise PlanError(f"Ollama is not reachable at {host}: {exc}. Start Ollama and pull {model}.") from exc
    return payload["message"]["content"]


TECH_WORDS = {
    "kucoin", "binance", "bybit", "mexc", "python", "rust", "api", "docker", "fastapi", "http", "https",
    "json", "tls", "ssl", "telegram", "github", "ops", "mtf", "usdt", "spot", "rest", "ws", "websocket",
    "watchdog", "liveness", "readiness", "dry_run", "pyo3", "rocksdb", "dashboard", "soak", "lab", "live",
    "auto", "trade", "dup", "radar", "watchlist", "metrics", "ui", "cli", "git", "pr", "ci",
}
URL_RE = re.compile(r"https?://\S+|\S+\.(?:com|io|org|net)\S*")


def cyrillic_ratio(text: str) -> float:
    """Share of Cyrillic letters among Russian-prose letters.

    URLs, slash-commands and well-known technology names are ignored, because they are
    legitimately Latin. Silero ru cannot voice Latin prose, so voice_text is checked strictly.
    """
    text = URL_RE.sub(" ", text)
    words = re.findall(r"\S+", text)
    prose = [w for w in words if not w.startswith("/") and w.strip(".,:;!?()[]\"'").lower() not in TECH_WORDS]
    letters = [ch for w in prose for ch in w if ch.isalpha()]
    if not letters:
        return 1.0
    cyr = sum(1 for ch in letters if "\u0400" <= ch <= "\u04FF")
    return cyr / len(letters)


RU_MIN_RATIO = 0.6       # voice_text: Silero cannot voice Latin prose
RU_MIN_RATIO_TEXT = 0.5  # titles, bullets: Latin brand/tech terms allowed


IDENT_PATTERNS = [
    re.compile(r"\b[A-Za-z]+_[A-Za-z0-9_]+\b"),                       # snake_case, ENV_VARS, _private
    re.compile(r"\b[A-Z][a-z0-9]+(?:[A-Z][A-Za-z0-9]*)+\b"),         # CamelCase, KuCoin
    re.compile(r"\b[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+){2,}\b"),     # X-Radar-Api-Key (3+ parts)
    re.compile(r"(?<![\w/])/[\w\-./]+"),                              # /api/live
    re.compile(r"\b[\w\-]+\.(?:py|rs|ps1|ts|tsx|md|json|yaml|yml|toml|bat)\b"),  # file names
]
_CORPUS_CACHE: dict[str, str] = {}


def build_corpus(facts: dict) -> str:
    """Lowercased text of the project (redacted docs + indexed code). Used only for membership tests."""
    key = facts["root"]
    if key not in _CORPUS_CACHE:
        # Mirror exactly what the model sees in FACTS: doc headers, doc text, and the C-section lines
        # (path, line count, summary). Without these, real file names and line counts look "invented".
        parts = [f"[{d['id']}] {d['path']} (lines {d['lines']})\n{d['text']}" for d in facts["docs"]]
        parts += [
            f"[{c['id']}] {c['path']} ({c['line_count']} lines) - {c['summary'] or 'no summary'}"
            for c in facts["code"]
        ]
        root = Path(facts["root"])
        for c in facts["code"]:
            parts.append("\n".join(read_lines(root / c["path"], {"redacted_lines": 0})))
        _CORPUS_CACHE[key] = "\n".join(parts).lower()
    return _CORPUS_CACHE[key]


def extract_identifiers(text: str) -> set[str]:
    found: set[str] = set()
    for pattern in IDENT_PATTERNS:
        found.update(m.group(0) for m in pattern.finditer(text))
    return {tok.rstrip(".") for tok in found if len(tok.rstrip(".")) >= 3}


def unverified_identifiers(plan: dict, facts: dict) -> list[tuple[int, str]]:
    """Technical names used on slides that do not occur anywhere in the project sources."""
    corpus = build_corpus(facts)
    bad: list[tuple[int, str]] = []
    for idx, s in enumerate(plan.get("slides") or [], start=1):
        texts = [str(s.get("title", "")), str(s.get("subtitle", "")), str(s.get("voice_text", ""))]
        texts += [f"{b.get('title', '')} {b.get('desc', '')}" for b in (s.get("bullets") or [])]
        for text in texts:
            for tok in sorted(extract_identifiers(text)):
                if tok.lower() not in corpus and (idx, tok) not in bad:
                    bad.append((idx, tok))
    return bad


KPI_HEALTH_CLAIM_RE = re.compile(
    r"soak|audit|fail|pass|mainnet|production|prod\b|secur|uptime|stable|proven|verified|guarantee|safe|zero",
    re.IGNORECASE,
)


def validate_kpi_slide(s: dict, facts: dict, tag: str) -> list[str]:
    """KPI values must be presence-checked AND quoted: a verbatim FACTS quote that contains the value.

    Presence alone is not attribution (a bare '0' matches any fact), so every kpi carries a quote.
    Health/soak/audit claims are refused on KPI cards: they belong in bullets with source_ids.
    """
    errors: list[str] = []
    kpis = s.get("kpis") or []
    if not (1 <= len(kpis) <= 4):
        return [f"{tag}: kpi needs 1..4 kpis, got {len(kpis)}"]
    corpus = re.sub(r"\s+", " ", build_corpus(facts))
    for k in kpis:
        if not isinstance(k, dict):
            errors.append(f"{tag}: each kpi must be an object with value, label and quote")
            continue
        value = str(k.get("value", "")).strip()
        label = str(k.get("label", "")).strip()
        quote = re.sub(r"\s+", " ", str(k.get("quote", ""))).strip().lower()
        if not value or len(value) > 12 or len(value) < 2 or not label:
            errors.append(f"{tag}: each kpi needs value (2..12 chars) and label")
            continue
        if KPI_HEALTH_CLAIM_RE.search(label) or KPI_HEALTH_CLAIM_RE.search(value):
            errors.append(
                f"{tag}: kpi {label!r} is a health/soak/audit claim; KPI cards may only show measurable "
                "identifiers (counts, versions, IDs, sizes). Move the claim to bullets with source_ids"
            )
            continue
        if not quote:
            errors.append(f"{tag}: kpi {value!r} needs quote: an exact sentence copied from FACTS")
            continue
        if quote not in corpus:
            errors.append(f"{tag}: kpi quote for {value!r} is not verbatim in FACTS; copy it exactly")
            continue
        if not re.search(r"(?<!\w)" + re.escape(value.lower()) + r"(?!\w)", quote):
            errors.append(f"{tag}: kpi value {value!r} does not occur inside its quote")
    return errors


QUOTE_MIN_WORDS = 4


def validate_quote_slide(s: dict, facts: dict, tag: str) -> list[str]:
    """A quote slide shows one sentence copied verbatim from FACTS, so the wording is attributable to the project.

    Same claim refusal as KPI cards: a quotation must not carry health/soak/audit/mainnet claims.
    Length limit and attribution type mirror build_deck.validate_deck.
    """
    from build_deck import QUOTE_MAX_CHARS

    quote_raw = str(s.get("title", "")).strip()
    if not quote_raw or len(quote_raw) > QUOTE_MAX_CHARS:
        return [f"{tag}: quote title must be 1..{QUOTE_MAX_CHARS} chars"]
    if "subtitle" in s and not isinstance(s.get("subtitle"), str):
        return [f"{tag}: quote subtitle (source) must be a string"]
    if KPI_HEALTH_CLAIM_RE.search(quote_raw):
        return [f"{tag}: quote is a health/soak/audit claim; keep such statements in bullets with source_ids"]
    if not re.search(r"[.!?]$", quote_raw) or len(quote_raw.split()) < QUOTE_MIN_WORDS:
        return [
            f"{tag}: quote must be one full sentence ending with . ! or ? and at least "
            f"{QUOTE_MIN_WORDS} words (headings and fragments are refused)"
        ]
    corpus = re.sub(r"\s+", " ", build_corpus(facts))
    norm = re.sub(r"\s+", " ", quote_raw).lower()
    if norm not in corpus:
        return [f"{tag}: quote is not verbatim in FACTS; copy one sentence exactly"]
    return []


def validate_plan(plan: dict, facts: dict, lang: str = "ru") -> list[str]:
    errors: list[str] = []
    code_by_id = {c["id"]: c for c in facts["code"]}
    symbols = symbol_index(facts)
    image_ids = {i["id"] for i in facts["images"]}
    doc_ids = {d["id"] for d in facts["docs"]}
    all_ids = set(code_by_id) | image_ids | doc_ids

    slides = plan.get("slides")
    if not isinstance(slides, list) or not (3 <= len(slides) <= 12):
        return ["slides must be a list of 3..12 items"]
    if slides[0].get("type") != "hero_3d":
        errors.append("first slide must be hero_3d")
    if slides[-1].get("type") != "outro_3d":
        errors.append("last slide must be outro_3d")

    used_symbols: set[str] = set()
    for idx, s in enumerate(slides):
        tag = f"slide {idx + 1}"
        stype = s.get("type")
        if stype not in SLIDE_TYPES:
            errors.append(f"{tag}: unsupported type {stype!r}")
            continue
        if not str(s.get("title", "")).strip():
            errors.append(f"{tag}: empty title")
        bq = s.get("background_query")
        if bq not in (None, ""):
            try:
                validate_query(str(bq))
            except StockMediaError as exc:
                errors.append(f"{tag}: {exc}")
        voice = str(s.get("voice_text", ""))
        if not voice.strip():
            errors.append(f"{tag}: empty voice_text")
        elif lang == "ru" and cyrillic_ratio(voice) < RU_MIN_RATIO:
            errors.append(f"{tag}: voice_text must be Russian (Cyrillic ratio {cyrillic_ratio(voice):.2f} < {RU_MIN_RATIO}); rewrite it fully in Russian")
        elif lang == "ru" and [w for w in re.findall(r"[A-Za-z][A-Za-z0-9_]*", voice) if w.lower() not in LATIN_RU]:
            unknown = sorted({w for w in re.findall(r"[A-Za-z][A-Za-z0-9_]*", voice) if w.lower() not in LATIN_RU})
            errors.append(
                f"{tag}: voice_text has Latin words Silero cannot voice: {unknown}; "
                "write them in Cyrillic inside voice_text (e.g. GitHub -> гитхаб) and keep the Latin form only in title/bullets"
            )
        elif lang == "en" and cyrillic_ratio(voice) > 0.05:
            errors.append(f"{tag}: voice_text must be English (no Cyrillic letters); rewrite it fully in English")
        if lang == "ru":
            for field in ("title", "subtitle"):
                text = str(s.get(field, ""))
                if text and cyrillic_ratio(text) < RU_MIN_RATIO_TEXT and len(text) > 12:
                    errors.append(f"{tag}: {field} must be in Russian; rewrite it in Russian")
            for b in s.get("bullets") or []:
                desc = str(b.get("desc", ""))
                if desc and cyrillic_ratio(desc) < RU_MIN_RATIO_TEXT:
                    errors.append(f"{tag}: bullet description must be in Russian: {desc[:60]!r}")
        else:
            for field in ("title", "subtitle"):
                text = str(s.get(field, ""))
                if text and cyrillic_ratio(text) > 0.05:
                    errors.append(f"{tag}: {field} must be in English (no Cyrillic)")
        for sid in s.get("source_ids", []):
            if sid not in all_ids:
                errors.append(f"{tag}: unknown source id {sid!r}")
        if stype in CODE_TYPES:
            ref = s.get("code_ref") or {}
            symbol = ref.get("symbol")
            if symbol not in symbols:
                errors.append(
                    f"{tag}: code_split needs code_ref={{\"symbol\": \"<name from SYMBOLS>\"}}; "
                    f"received code_ref={ref!r}. Pick one of: {', '.join(list(symbols)[:15])}"
                )
            elif symbol in used_symbols:
                errors.append(
                    f"{tag}: symbol {symbol!r} is already shown on another slide; every code slide needs a different symbol"
                )
            else:
                used_symbols.add(symbol)
        if stype == "timeline":
            steps = s.get("bullets") or []
            if not (2 <= len(steps) <= 6):
                errors.append(f"{tag}: timeline needs 2..6 bullets (steps), got {len(steps)}")
        if stype == "kpi":
            errors.extend(validate_kpi_slide(s, facts, tag))
        if stype == "quote":
            errors.extend(validate_quote_slide(s, facts, tag))
        if stype == "arch_flow":
            arch = s.get("arch") or {}
            nodes = arch.get("nodes") or []
            if not (2 <= len(nodes) <= 6):
                errors.append(f"{tag}: arch_flow needs 2..6 nodes in arch.nodes")
            else:
                known_paths = {c["path"] for c in facts["code"]} | {d["path"] for d in facts["docs"]}
                node_ids = set()
                for n in nodes:
                    nid = str(n.get("id") or "").strip()
                    if not nid or nid in node_ids:
                        errors.append(f"{tag}: arch node missing/duplicate id {nid!r}")
                    node_ids.add(nid)
                    p = str(n.get("path") or "").strip()
                    if p and p not in known_paths:
                        errors.append(f"{tag}: arch node path {p!r} is not in FACTS code/docs; use an exact path from C")
                for e in arch.get("edges") or []:
                    if e.get("from") not in node_ids or e.get("to") not in node_ids:
                        errors.append(f"{tag}: arch edge {e!r} references unknown node id")
        ids = s.get("screen_ids") or []
        if stype == "screen_split" and not ids:
            errors.append(f"{tag}: screen_split requires screen_ids")
        if stype == "screen_split" and not image_ids:
            errors.append(f"{tag}: no images in FACTS section I; use code_split instead of screen_split")
        for iid in ids:
            if iid not in image_ids:
                errors.append(f"{tag}: unknown image id {iid!r}; allowed {sorted(image_ids) or 'none'}")
    bad = unverified_identifiers(plan, facts)
    for idx, tok in bad[:12]:
        errors.append(
            f"slide {idx}: name {tok!r} does not occur in the project sources; "
            "use only names from FACTS or rewrite the sentence without it"
        )
    return errors


def example_code_slide(facts: dict) -> str:
    """A concrete, valid code_split example built from real IDs, shown to the model on repair."""
    index = symbol_index(facts)
    if not index:
        return "(no code symbols available: do not use code_split)"
    name, hit = next(iter(index.items()))
    example = {
        "type": "code_split", "tag": "CODE", "title": "Пример", "subtitle": "...",
        "bullets": [{"title": "...", "desc": "..."}],
        "code_ref": {"symbol": name},
        "screen_ids": [], "voice_text": "...", "source_ids": [hit["file"]],
    }
    return json.dumps(example, ensure_ascii=False)


def ask_plan(facts: dict, model: str, host: str, feedback: str | None, previous: dict | None,
             slides_n: int | None, raw_dir: Path, provider: str = "ollama", lang: str = "ru") -> dict:
    raw_dir.mkdir(parents=True, exist_ok=True)
    facts_text = render_facts(facts)
    user_parts = [facts_text]
    if slides_n:
        user_parts.append(f"Нужно ровно {slides_n} слайдов." if lang == "ru" else f"Produce exactly {slides_n} slides.")
    if feedback and previous:
        user_parts.append("=== PREVIOUS PLAN ===\n" + json.dumps(previous, ensure_ascii=False, indent=2))
        user_parts.append(
            "=== USER FEEDBACK ===\n" + feedback +
            ("\nИзмени предыдущий план по замечанию. Слайды, которых замечание не касается, оставь без изменений. Верни полный JSON."
             if lang == "ru" else
             "\nRevise the previous plan per the feedback. Keep unrelated slides unchanged. Return full JSON.")
        )
    else:
        user_parts.append("Составь план презентации по этим фактам. Верни полный JSON." if lang == "ru" else "Build the presentation plan from these facts. Return full JSON.")
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT if lang == "ru" else SYSTEM_PROMPT_EN},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]
    last_errors: list[str] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if last_errors:
            messages.append({
                "role": "user",
                "content": (
                    "Ошибки в твоём JSON:\n- " + "\n- ".join(last_errors) +
                    "\nИсправь их и верни полный JSON заново. Пример ВАЛИДНОГО code_split слайда "
                    "(используй такой формат, подставив свой текст):\n" + example_code_slide(facts)
                ),
            })
        raw = ollama_chat(model, messages, host) if provider == "ollama" else openai_compatible_chat(messages, model_override=model if model != DEFAULT_MODEL else "")
        (raw_dir / f"attempt{attempt}.txt").write_text(raw, encoding="utf-8")
        messages.append({"role": "assistant", "content": raw})
        try:
            plan = json.loads(raw)
        except json.JSONDecodeError as exc:
            last_errors = [f"invalid JSON: {exc}"]
            print(f"[plan] attempt {attempt}: invalid JSON, retrying")
            continue
        last_errors = validate_plan(plan, facts, lang=lang)
        if not last_errors:
            print(f"[plan] attempt {attempt}: valid plan with {len(plan['slides'])} slides")
            return plan
        print(f"[plan] attempt {attempt}: {len(last_errors)} validation error(s), retrying")
        for err in last_errors:
            print(f"[plan]   - {err}")
    raise PlanError("Plan failed validation after retries:\n- " + "\n- ".join(last_errors))


def code_excerpt(ref: dict, facts: dict) -> tuple[str, list[dict], int, int]:
    """Return (display_path, colored_lines, start, end) for a symbol, read from the real file."""
    hit = symbol_index(facts)[ref["symbol"]]
    start = hit["start"]
    end = min(hit["end"], start + CODE_MAX_SPAN - 1)
    path = Path(facts["root"]) / hit["path"]
    raw = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return hit["path"], code_lines_for(raw, start, end), start, end


def derive_faces(s: dict) -> list[str]:
    words: list[str] = []
    for text in (s.get("tag", ""), s.get("title", "")):
        for w in re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", text):
            token = w.upper()[:8]
            if token not in words:
                words.append(token)
    return words[:6] or ["DUP"]


def code_lines_for(raw: list[str], start: int, end: int) -> list[dict]:
    out = []
    for ln in raw[start - 1: end]:
        clean, _ = redact_line(ln.rstrip())
        text = clean[:CODE_LINE_CAP]
        stripped = text.strip()
        if stripped.startswith(("#", "//")):
            color = "#64748b"
        elif re.search(r"\b(bail!|raise|Err|error|panic)\b", text):
            color = "#f472b6"
        elif re.search(r"\b(def|fn|class|struct|function|pub)\b", text):
            color = "#38bdf8"
        elif re.search(r"\b(return|Ok|yield)\b", text):
            color = "#00f5d4"
        else:
            color = "#f8fafc"
        out.append({"text": text, "color": color})
    return out


def voice_ssml(text: str, rate: str = "95%") -> str:
    body = escape(" ".join(text.split()))
    body = re.sub(r"([.!?])\s+", r'\1<break time="250ms"/> ', body)
    return f'<speak><prosody rate="{rate}">{body}</prosody></speak>'


def stage_screen(image: dict, facts: dict, slug: str) -> str:
    src_path = Path(facts["root"]) / image["path"]
    dest_dir = ROOT / "public" / "screens" / slug
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src_path.name
    shutil.copyfile(src_path, dest)
    return f"screens/{slug}/{src_path.name}"


def assemble_deck(
    plan: dict,
    facts: dict,
    slug: str,
    lang: str = "ru",
    speaker: str = "",
    theme: str = "neon_cyber",
    aspect: str = "16:9",
    voice_mode: str = "single",
    burn_captions: bool = True,
) -> dict:
    voice_cfg = dict(VOICE_BLOCK_EN if lang == "en" else VOICE_BLOCK_RU)
    if speaker:
        voice_cfg["speaker"] = speaker
    voice_cfg["mode"] = voice_mode
    w, h = ASPECTS.get(aspect, (1920, 1080))
    image_by_id = {i["id"]: i for i in facts["images"]}
    url = (facts.get("urls") or [f"github.com/{facts['project']['name']}"])[0].replace("https://", "")
    slides = []
    for idx, s in enumerate(plan["slides"], start=1):
        sid = f"s{idx}"
        # Timeline steps are validated as 2..6 items; every other type shows at most 3 bullets.
        bullet_limit = 6 if s["type"] == "timeline" else 3
        bullets = (s.get("bullets") or [])[:bullet_limit]
        item: dict = {
            "id": sid,
            "tag": str(s.get("tag") or "").upper()[:40] or "PROJECT",
            "type": s["type"],
            "title": s["title"],
            "subtitle": s.get("subtitle", ""),
            "voice_ssml": voice_ssml(s["voice_text"]),
        }
        if s["type"] == "hero_3d":
            item["pills"] = [{"name": b["title"][:28], "color": PALETTE[i % 4]} for i, b in enumerate(bullets)]
            item["cube_faces"] = derive_faces(s)
        elif s["type"] == "outro_3d":
            item["url"] = url
            item["tagline"] = s.get("subtitle", "")
            item["badges"] = [{"name": b["title"][:28], "color": PALETTE[i % 4]} for i, b in enumerate(bullets)]
            item["cube_faces"] = derive_faces(s)
        else:
            item["bullets"] = [
                {"title": b["title"], "desc": b["desc"], "accent": PALETTE[i % 4]} for i, b in enumerate(bullets)
            ]
        if s["type"] in CODE_TYPES:
            rel_path, lines, start, end = code_excerpt(s["code_ref"], facts)
            item["code"] = {"filename": f"{rel_path} · L{start}-{end}", "lines": lines}
        if s["type"] == "screen_split":
            screens = []
            for iid in s["screen_ids"]:
                img = image_by_id[iid]
                src = stage_screen(img, facts, slug)
                screens.append({"src": src, "caption": f"{s['title']} · {Path(img['path']).name}"})
            item["screens"] = screens
        if s["type"] == "arch_flow":
            item["arch"] = s.get("arch") or {"nodes": [], "edges": []}
        if s["type"] == "kpi":
            item["kpis"] = [
                {"value": str(k["value"]).strip(), "label": str(k["label"]).strip()}
                for k in (s.get("kpis") or [])[:4]
            ]
        item["voice_text"] = s["voice_text"]
        if s.get("background_query"):
            item["background_query"] = str(s["background_query"]).strip()
        slides.append(item)

    return {
        "slug": slug,
        "lang": lang,
        "theme": theme,
        "aspect": aspect,
        "burn_captions": burn_captions,
        "background": {"enabled": False, "provider": "pixabay"},
        "music": {"enabled": False, "volume": 0.12},
        "brand": plan.get("brand") or facts["project"]["name"].upper(),
        "fps": 30,
        "width": w,
        "height": h,
        "voice": voice_cfg,
        "slides": slides,
    }


def next_version(versions_dir: Path) -> int:
    nums = [int(p.stem[1:]) for p in versions_dir.glob("v*.json") if p.stem[1:].isdigit()]
    return max(nums, default=0) + 1


def latest_plan(versions_dir: Path) -> tuple[int, dict]:
    n = next_version(versions_dir) - 1
    if n < 1:
        raise PlanError(f"No previous plan in {versions_dir}; run without --feedback first.")
    return n, json.loads((versions_dir / f"v{n}.json").read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="DUP Presenter deck planner")
    parser.add_argument("--slug", required=True, help="Deck slug, e.g. radar")
    parser.add_argument("--facts", help="Path to facts.json (default: work/<slug>/facts.json)")
    parser.add_argument("--feedback", help="Natural-language change request for the latest plan")
    parser.add_argument("--slides", type=int, default=None, help="Exact number of slides")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model id (Ollama or cloud override)")
    parser.add_argument("--host", default=OLLAMA_HOST)
    parser.add_argument("--provider", choices=["ollama", "cloud"], default="ollama",
                        help="cloud reads DUP_LLM_BASE_URL / DUP_LLM_MODEL / DUP_LLM_API_KEY from the environment")
    parser.add_argument("--lang", choices=["ru", "en"], default="ru", help="Presentation and voice language")
    parser.add_argument("--speaker", default="", help="Speaker id (e.g. eugene/xenia for ru; am_michael/af_bella or en_1/en_0 for en)")
    parser.add_argument("--theme", choices=list(THEMES), default="neon_cyber")
    parser.add_argument("--aspect", choices=list(ASPECTS), default="16:9")
    parser.add_argument("--voice-mode", choices=["single", "podcast"], default="single")
    parser.add_argument("--no-captions", action="store_true", help="Disable burned-in captions on video")
    args = parser.parse_args()

    work = ROOT / "work" / args.slug
    versions_dir = work / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)
    facts_path = Path(args.facts) if args.facts else work / "facts.json"
    facts = json.loads(facts_path.read_text(encoding="utf-8"))

    previous = None
    if args.feedback:
        prev_n, previous = latest_plan(versions_dir)
        print(f"[plan] revising v{prev_n} with feedback (lang={args.lang})")
    raw_dir = work / "raw" / f"run_{next_version(versions_dir)}"
    plan = ask_plan(facts, args.model, args.host, args.feedback, previous, args.slides, raw_dir, args.provider, lang=args.lang)

    version = next_version(versions_dir)
    (versions_dir / f"v{version}.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    with (work / "history.jsonl").open("a", encoding="utf-8") as fh:
        used_model = args.model if args.provider == "ollama" else f"cloud:{args.model if args.model != DEFAULT_MODEL else os.environ.get('DUP_LLM_MODEL', '?')}"
        fh.write(json.dumps({"version": version, "feedback": args.feedback or "", "model": used_model, "lang": args.lang}, ensure_ascii=False) + "\n")

    deck = assemble_deck(
        plan, facts, args.slug,
        lang=args.lang,
        speaker=args.speaker,
        theme=args.theme,
        aspect=args.aspect,
        voice_mode=args.voice_mode,
        burn_captions=not args.no_captions,
    )
    deck_path = ROOT / "decks" / f"{args.slug}.json"
    deck_path.write_text(json.dumps(deck, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[plan] saved version v{version} -> {versions_dir / f'v{version}.json'}")
    print(f"[plan] deck -> {deck_path}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except PlanError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(2)
