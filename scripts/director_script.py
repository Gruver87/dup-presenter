"""DUP Presenter — Director Script engine (Stage 2, fail-closed, DeepSeek only).

Turns one topic into a multi-act cinematic storyboard of 1..10 minutes:
  - `style_bible` (palette / lens / lighting / mood) shared by every scene for visual continuity;
  - `scenes` with narration (`voice_text`), on-screen `headline` / `caption`, a cinematic English
    shot description (`visual_prompt_en`), stock search phrases (`stock_queries_en`) and a
    `visual_type` that maps to a validated deck slide type.

The script is converted into a `decks/<slug>.json` deck that passes `build_deck.validate_deck`.

Honesty invariants:
  - The only LLM provider is DeepSeek (`DEEPSEEK_API_KEY` or `DUP_LLM_API_KEY`). A missing key,
    HTTP error, truncated or non-JSON response, or any validation failure raises
    `DirectorScriptError`. There is NO template fallback: nothing is ever labelled as LLM output
    when it was not produced by the LLM.
  - The API key is never printed, logged or written to any file.
  - Only https:// base URLs are accepted (TLS verification stays on, urllib default).
  - Scene durations are checked against the requested runtime (+/-15 %) and against a maximum
    speaking rate (words per second), so an impossible script cannot reach the renderer.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from build_deck import DEFAULT_SPEAKER_BY_LANG, DeckValidationError, validate_deck  # noqa: E402
from idea_engine import SLUG_RE, slugify_topic  # noqa: E402
from stock_media import StockMediaError, validate_query  # noqa: E402

DECKS_DIR = ROOT / "decks"
SCRIPTS_OUT_DIR = ROOT / "work" / "director_scripts"

DEEPSEEK_DEFAULT_BASE = "https://api.deepseek.com/v1"
DEEPSEEK_DEFAULT_MODEL = "deepseek-chat"
LLM_TIMEOUT_SEC = 180
LLM_MAX_TOKENS = 8192
LLM_TEMPERATURE = 0.7

MIN_MINUTES = 1
MAX_MINUTES = 10
ACT_MAX_SEC = 150
MAX_ACTS = 4
MAX_ACT_ATTEMPTS = 4  # schema-error repair attempts per act (transport errors are never retried); 3 was too few live
SCENES_PER_ACT_MAX = 14
SCENE_MIN_SEC = 4
SCENE_MAX_SEC = 40
# Upper bound 3.3: brisk but speakable; the real length is re-measured at render (slide grows, total is checked).
MAX_WORDS_PER_SEC = 3.3
# Lower bound: a scene whose narration is too short leaves dead air (the renderer pads it with silence).
# ~2.3 words/sec is normal speech; 1.8 is the floor that still sounds continuous.
MIN_WORDS_PER_SEC = 1.8
NARRATION_WORDS_PER_SEC_TARGET = 2.3
DURATION_TOLERANCE = 0.15
MIN_TOTAL_SCENES = 3

# `quote` is deliberately NOT allowed for LLM output: an LLM cannot verify attributions, and a
# fabricated quotation is a dishonest claim. Quotes can only come from a human-written deck.
ALLOWED_VISUAL_TYPES = frozenset({"cinema_clip", "broll_cinematic", "stat_burst", "kpi"})
FACT_STATUS = "unverified_llm_output"
ALLOWED_LANGS = frozenset({"ru", "en"})
ENGINE_BY_LANG = {"ru": "edge_tts", "en": "kokoro_v1"}
DEFAULT_THEME = "quantum_ledger"
STYLE_BIBLE_KEYS = ("palette", "lens", "lighting", "mood")

CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")

LLMCallable = Callable[[list[dict[str, str]]], dict[str, Any]]


class DirectorScriptError(RuntimeError):
    """Director script could not be generated or failed validation. The build must stop."""


# --------------------------------------------------------------------------- LLM transport


def _llm_config() -> tuple[str, str, str]:
    """Return (api_key, base_url, model). Never returns or logs the key outside this tuple."""
    api_key = (os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("DUP_LLM_API_KEY") or "").strip()
    if not api_key:
        raise DirectorScriptError(
            "DeepSeek key missing: set DEEPSEEK_API_KEY or DUP_LLM_API_KEY (the value is never printed)"
        )
    base = (
        os.environ.get("DEEPSEEK_BASE_URL") or os.environ.get("DUP_LLM_BASE_URL") or DEEPSEEK_DEFAULT_BASE
    ).strip().rstrip("/")
    if not base.startswith("https://"):
        raise DirectorScriptError("LLM base URL must start with https:// (TLS verification is required)")
    model = os.environ.get("DEEPSEEK_MODEL") or os.environ.get("DUP_LLM_MODEL") or DEEPSEEK_DEFAULT_MODEL
    return api_key, base, model


def chat_json(messages: list[dict[str, str]]) -> dict[str, Any]:
    """One DeepSeek chat call that must return a single JSON object. Fail-closed on every error."""
    api_key, base, model = _llm_config()
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": LLM_MAX_TOKENS,
        "temperature": LLM_TEMPERATURE,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=LLM_TIMEOUT_SEC) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise DirectorScriptError(f"DeepSeek HTTP {exc.code}: request refused, no fallback is used") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise DirectorScriptError(
            f"DeepSeek network error ({type(exc).__name__}): no fallback is used"
        ) from None
    except ValueError:
        raise DirectorScriptError("DeepSeek returned a non-JSON HTTP body") from None

    choices = data.get("choices") if isinstance(data, dict) else None
    if not choices or not isinstance(choices, list) or not isinstance(choices[0], dict):
        raise DirectorScriptError("DeepSeek response has no choices")
    if choices[0].get("finish_reason") == "length":
        raise DirectorScriptError("DeepSeek response was truncated (finish_reason=length); shorten the act")
    content = ((choices[0].get("message") or {}).get("content")) or ""
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, TypeError) as exc:
        raise DirectorScriptError(f"DeepSeek content is not valid JSON: {exc.__class__.__name__}") from None
    if not isinstance(parsed, dict):
        raise DirectorScriptError("DeepSeek JSON payload must be an object")
    return parsed


# --------------------------------------------------------------------------- prompts


def _system_prompt(lang: str) -> str:
    lang_label = "Russian" if lang == "ru" else "English"
    return (
        "You are a film director and screenwriter for a documentary-style science video. "
        "Return ONLY one valid JSON object. Rules: use only well-established facts; never invent numbers, "
        "dates, quotes or sources; "
        f"voice_text must be written in {lang_label} and must be easy to speak aloud; "
        f"voice_text length must fill target_sec: about {NARRATION_WORDS_PER_SEC_TARGET} words per second "
        f"(e.g. 12 s = about {round(12 * NARRATION_WORDS_PER_SEC_TARGET)} words); "
        "Never write direct quotations or attributions to named people: paraphrase facts only. "
        "Give only numbers you are certain of, and write 'about' or 'approximately' for rounded values. "
        "visual_prompt_en is a concrete English cinematic shot description (camera, subject, light); "
        "stock_queries_en are 2-4 word English search phrases using latin letters only; "
        f"visual_type must be exactly one of: {', '.join(sorted(ALLOWED_VISUAL_TYPES))}; "
        "kpi scenes need 'kpis': [{'value': <=12 chars, 'label': text}] with 1-4 items; "
        "'headline' is a short on-screen title (<=24 characters); 'caption' is optional on-screen text (<=200 chars)."
    )


def _act_user_prompt(
    topic: str,
    minutes: int,
    act_index: int,
    act_count: int,
    act_target_sec: int,
    style: str,
    style_bible: dict[str, str] | None,
    previous_headlines: list[str],
) -> str:
    spec: dict[str, Any] = {
        "topic": topic,
        "total_minutes": minutes,
        "act": act_index,
        "of_acts": act_count,
        "act_total_seconds": act_target_sec,
        "style": style,
        "scene_seconds_range": [SCENE_MIN_SEC, SCENE_MAX_SEC],
        "scene_count_range": [3, SCENES_PER_ACT_MAX],
        "previous_headlines": previous_headlines[-8:],
    }
    if style_bible is None:
        spec["return"] = {
            "title": "string (<=120 chars)",
            "style_bible": {k: "string (<=200 chars)" for k in STYLE_BIBLE_KEYS},
            "scenes": "array of scene objects",
        }
    else:
        spec["style_bible"] = style_bible
        spec["return"] = {"scenes": "array of scene objects"}
        spec["instruction"] = "Keep the given style_bible exactly for visual continuity."
    spec["scene_object"] = {
        "voice_text": "narration string",
        "target_sec": "integer in scene_seconds_range; scene durations must sum to act_total_seconds (+/-15%)",
        "visual_type": f"one of {sorted(ALLOWED_VISUAL_TYPES)}",
        "headline": "string <=24 chars",
        "caption": "optional string <=200 chars",
        "visual_prompt_en": "string 10..400 chars, English",
        "stock_queries_en": "array of 1-3 latin phrases (required for cinema_clip)",
        "kpis": "array 1-4 items, only for kpi scenes",
    }
    return json.dumps(spec, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------- validation


def _is_number(val: object) -> bool:
    return isinstance(val, (int, float)) and not isinstance(val, bool)


def _req_str(obj: dict[str, Any], key: str, lo: int, hi: int, where: str) -> str:
    val = obj.get(key)
    if not isinstance(val, str) or not (lo <= len(val.strip()) <= hi):
        raise DirectorScriptError(f"{where}: '{key}' must be a string of {lo}..{hi} characters")
    return val.strip()


def _opt_str(obj: dict[str, Any], key: str, hi: int, where: str) -> str:
    val = obj.get(key)
    if val is None:
        return ""
    if not isinstance(val, str) or len(val.strip()) > hi:
        raise DirectorScriptError(f"{where}: '{key}' must be a string of at most {hi} characters")
    return val.strip()


def _validate_style_bible(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise DirectorScriptError("style_bible must be an object")
    return {k: _req_str(raw, k, 1, 200, "style_bible") for k in STYLE_BIBLE_KEYS}


def _validate_scene(raw: object, act_index: int, idx: int, lang: str) -> dict[str, Any]:
    where = f"act {act_index} scene #{idx + 1}"
    if not isinstance(raw, dict):
        raise DirectorScriptError(f"{where}: scene must be an object")

    visual_type = raw.get("visual_type")
    if visual_type not in ALLOWED_VISUAL_TYPES:
        raise DirectorScriptError(f"{where}: visual_type {visual_type!r} not in {sorted(ALLOWED_VISUAL_TYPES)}")

    target = raw.get("target_sec")
    if not _is_number(target):
        raise DirectorScriptError(f"{where}: target_sec must be a number")
    target_sec = int(round(float(target)))
    if not (SCENE_MIN_SEC <= target_sec <= SCENE_MAX_SEC):
        raise DirectorScriptError(f"{where}: target_sec {target_sec} outside {SCENE_MIN_SEC}..{SCENE_MAX_SEC}")

    voice_text = _req_str(raw, "voice_text", 1, 900, where)
    if lang == "ru" and not CYRILLIC_RE.search(voice_text):
        raise DirectorScriptError(f"{where}: voice_text must be Russian (no Cyrillic letters found)")
    if lang == "en" and CYRILLIC_RE.search(voice_text):
        raise DirectorScriptError(f"{where}: voice_text must be English (Cyrillic letters found)")
    words = len(voice_text.split())
    lo_words = math.ceil(target_sec * MIN_WORDS_PER_SEC)
    hi_words = math.floor(target_sec * MAX_WORDS_PER_SEC)
    rate = words / target_sec
    advice = f"Write {lo_words}-{hi_words} words (about {round(target_sec * NARRATION_WORDS_PER_SEC_TARGET)})"
    if words < lo_words:
        raise DirectorScriptError(
            f"{where}: {words} words in {target_sec}s = {rate:.2f} words/sec, below {MIN_WORDS_PER_SEC} "
            f"(dead air). {advice}"
        )
    if words > hi_words:
        raise DirectorScriptError(
            f"{where}: {words} words in {target_sec}s = {rate:.2f} words/sec, above {MAX_WORDS_PER_SEC} "
            f"(too fast to speak). {advice}"
        )

    headline = _req_str(raw, "headline", 1, 24, where)
    caption = _opt_str(raw, "caption", 200, where)
    visual_prompt = _req_str(raw, "visual_prompt_en", 10, 400, where)
    if CYRILLIC_RE.search(visual_prompt):
        raise DirectorScriptError(f"{where}: visual_prompt_en must be English")

    stock_raw = raw.get("stock_queries_en")
    stock: list[str] = []
    if stock_raw is not None:
        if not isinstance(stock_raw, list) or len(stock_raw) > 3:
            raise DirectorScriptError(f"{where}: stock_queries_en must be a list of at most 3 phrases")
        for q in stock_raw:
            try:
                stock.append(validate_query(q if isinstance(q, str) else ""))
            except StockMediaError as exc:
                raise DirectorScriptError(f"{where}: invalid stock query: {exc}") from None
    if visual_type == "cinema_clip" and not stock:
        raise DirectorScriptError(f"{where}: cinema_clip scene needs at least one stock_queries_en phrase")

    kpis: list[dict[str, str]] = []
    if visual_type == "kpi":
        raw_kpis = raw.get("kpis")
        if not isinstance(raw_kpis, list) or not (1 <= len(raw_kpis) <= 4):
            raise DirectorScriptError(f"{where}: kpi scene needs 1..4 kpis")
        for k in raw_kpis:
            if not isinstance(k, dict):
                raise DirectorScriptError(f"{where}: each kpi must be an object")
            kpis.append(
                {
                    "value": _req_str(k, "value", 1, 12, f"{where} kpi"),
                    "label": _req_str(k, "label", 1, 80, f"{where} kpi"),
                }
            )
    return {
        "id": f"a{act_index}s{idx + 1:02d}",
        "act": act_index,
        "visual_type": visual_type,
        "target_sec": target_sec,
        "voice_text": voice_text,
        "headline": headline,
        "caption": caption,
        "visual_prompt_en": visual_prompt,
        "stock_queries_en": stock,
        "kpis": kpis,
    }


def _validate_act(raw_scenes: object, act_index: int, lang: str) -> list[dict[str, Any]]:
    if not isinstance(raw_scenes, list) or not (1 <= len(raw_scenes) <= SCENES_PER_ACT_MAX):
        raise DirectorScriptError(f"act {act_index}: scenes must be a list of 1..{SCENES_PER_ACT_MAX} items")
    return [_validate_scene(s, act_index, i, lang) for i, s in enumerate(raw_scenes)]


def _validate_global(script: dict[str, Any], total_sec: int) -> None:
    scenes = script["scenes"]
    if len(scenes) < MIN_TOTAL_SCENES:
        raise DirectorScriptError(f"script has {len(scenes)} scenes; at least {MIN_TOTAL_SCENES} are required")
    ids = [s["id"] for s in scenes]
    if len(ids) != len(set(ids)):
        raise DirectorScriptError("scene ids must be unique")
    actual = sum(s["target_sec"] for s in scenes)
    if abs(actual - total_sec) > total_sec * DURATION_TOLERANCE:
        raise DirectorScriptError(
            f"scene durations sum to {actual}s, requested {total_sec}s (tolerance +/-{int(DURATION_TOLERANCE*100)}%)"
        )


# --------------------------------------------------------------------------- generation


def _validate_act_payload(obj: object, act_index: int, lang: str) -> dict[str, Any]:
    """Validate one LLM act response. Raises DirectorScriptError with a message fit to show the model."""
    if not isinstance(obj, dict):
        raise DirectorScriptError(f"act {act_index}: LLM output must be a JSON object")
    out: dict[str, Any] = {}
    if act_index == 1:
        out["title"] = _req_str(obj, "title", 1, 120, "script")
        out["style_bible"] = _validate_style_bible(obj.get("style_bible"))
    out["scenes"] = _validate_act(obj.get("scenes"), act_index, lang)
    return out


def _call_act_with_repair(
    call: LLMCallable,
    messages: list[dict[str, str]],
    act_index: int,
    lang: str,
) -> dict[str, Any]:
    """Call the LLM for one act. Schema errors are sent back to the model for repair (bounded).

    Transport errors (HTTP, network, missing key, truncated output) are NOT retried here; they
    propagate immediately so that a broken key or outage cannot burn tokens silently.
    """
    convo = list(messages)
    last_err = ""
    for attempt in range(1, MAX_ACT_ATTEMPTS + 1):
        obj = call(convo)
        try:
            return _validate_act_payload(obj, act_index, lang)
        except DirectorScriptError as exc:
            last_err = str(exc)
            if attempt == MAX_ACT_ATTEMPTS:
                break
            convo = convo + [
                {"role": "assistant", "content": json.dumps(obj, ensure_ascii=False)[:4000]},
                {
                    "role": "user",
                    "content": (
                        f"Your JSON failed validation: {last_err}. "
                        "Return the COMPLETE corrected JSON object for this act, with the same schema. "
                        "Follow every length, count and language limit exactly."
                    ),
                },
            ]
    raise DirectorScriptError(
        f"act {act_index}: validation failed after {MAX_ACT_ATTEMPTS} attempts: {last_err}"
    )


def generate_script(
    topic: str,
    minutes: int,
    lang: str,
    style: str = "cinematic documentary",
    *,
    llm: LLMCallable | None = None,
) -> dict[str, Any]:
    """Generate and validate a multi-act director script. Raises DirectorScriptError on any failure."""
    clean_topic = " ".join(str(topic or "").split())
    if not clean_topic or len(clean_topic) > 300:
        raise DirectorScriptError("topic must be 1..300 characters")
    if not isinstance(minutes, int) or isinstance(minutes, bool) or not (MIN_MINUTES <= minutes <= MAX_MINUTES):
        raise DirectorScriptError(f"minutes must be an integer in {MIN_MINUTES}..{MAX_MINUTES}")
    if lang not in ALLOWED_LANGS:
        raise DirectorScriptError(f"lang must be one of {sorted(ALLOWED_LANGS)}")
    clean_style = " ".join(str(style or "").split())[:80] or "cinematic documentary"

    call = llm or chat_json
    total_sec = minutes * 60
    act_count = max(1, math.ceil(total_sec / ACT_MAX_SEC))
    if act_count > MAX_ACTS:
        raise DirectorScriptError(f"{minutes} min needs {act_count} acts; the maximum is {MAX_ACTS}")
    base, rem = divmod(total_sec, act_count)

    title = ""
    style_bible: dict[str, str] | None = None
    scenes: list[dict[str, Any]] = []
    for act_index in range(1, act_count + 1):
        act_target = base + (1 if act_index <= rem else 0)
        prompt = _act_user_prompt(
            clean_topic,
            minutes,
            act_index,
            act_count,
            act_target,
            clean_style,
            style_bible,
            [s["headline"] for s in scenes],
        )
        parsed = _call_act_with_repair(
            call,
            [{"role": "system", "content": _system_prompt(lang)}, {"role": "user", "content": prompt}],
            act_index,
            lang,
        )
        if act_index == 1:
            title = parsed["title"]
            style_bible = parsed["style_bible"]
        scenes.extend(parsed["scenes"])

    script: dict[str, Any] = {
        "slug": _make_slug(clean_topic, minutes),
        "title": title,
        "topic": clean_topic,
        "minutes": minutes,
        "lang": lang,
        "style": clean_style,
        "style_bible": style_bible,
        "fact_status": FACT_STATUS,
        "scenes": scenes,
    }
    _validate_global(script, total_sec)
    return script


def _make_slug(topic: str, minutes: int) -> str:
    base = slugify_topic(topic, fallback="director-script")[:50].rstrip("-") or "director-script"
    slug = f"{base}-{minutes}min"
    if not SLUG_RE.match(slug):
        raise DirectorScriptError(f"generated slug {slug!r} is invalid")
    return slug


def revalidate_script(script: dict[str, Any]) -> dict[str, Any]:
    """Re-run every validator on a stored script (used for offline `--script-file` input)."""
    if not isinstance(script, dict):
        raise DirectorScriptError("script file must contain a JSON object")
    lang = script.get("lang")
    if lang not in ALLOWED_LANGS:
        raise DirectorScriptError(f"lang must be one of {sorted(ALLOWED_LANGS)}")
    minutes = script.get("minutes")
    if not isinstance(minutes, int) or isinstance(minutes, bool) or not (MIN_MINUTES <= minutes <= MAX_MINUTES):
        raise DirectorScriptError("minutes must be an integer in range")
    _req_str(script, "title", 1, 120, "script")
    script["style_bible"] = _validate_style_bible(script.get("style_bible"))
    raw_scenes = script.get("scenes")
    if not isinstance(raw_scenes, list) or not raw_scenes:
        raise DirectorScriptError("scenes must be a non-empty list")
    grouped: dict[int, list[Any]] = {}
    for s in raw_scenes:
        if not isinstance(s, dict) or not isinstance(s.get("act"), int):
            raise DirectorScriptError("each stored scene needs an integer 'act'")
        grouped.setdefault(s["act"], []).append(s)
    rebuilt: list[dict[str, Any]] = []
    for act_index in sorted(grouped):
        rebuilt.extend(_validate_act(grouped[act_index], act_index, lang))
    script["scenes"] = rebuilt
    _validate_global(script, minutes * 60)
    return script


# --------------------------------------------------------------------------- deck conversion


def script_to_deck(script: dict[str, Any]) -> dict[str, Any]:
    """Map a validated director script onto a DUP Presenter deck (schema-valid, no assets required)."""
    lang = script["lang"]
    slides: list[dict[str, Any]] = []
    for sc in script["scenes"]:
        vt = sc["visual_type"]
        act_badge = f"ACT {sc['act']}"
        slide: dict[str, Any] = {
            "id": sc["id"],
            "tag": f"{sc['act']:02d}",
            "type": vt,
            "title": sc["headline"],
            "voice_text": sc["voice_text"],
            # The renderer would otherwise size the slide from narration alone (dead air or shortened film).
            "min_duration_sec": sc["target_sec"],
        }
        if vt == "cinema_clip":
            slide["background_query"] = sc["stock_queries_en"][0]
            slide["cinema"] = {"badge": act_badge, "crossfade_frames": 12, "grade": "cinema_warm"}
        elif vt == "broll_cinematic":
            slide["broll"] = {"badge": act_badge}
            if sc["caption"]:
                slide["broll"]["caption"] = sc["caption"]
        elif vt == "stat_burst":
            slide["stat_burst"] = {
                "headline": sc["headline"],
                "kicker": act_badge,
                "caption": sc["caption"] or sc["headline"],
            }
        elif vt == "kpi":
            slide["kpis"] = sc["kpis"]
        slides.append(slide)

    return {
        "slug": script["slug"],
        "lang": lang,
        "theme": DEFAULT_THEME,
        "aspect": "16:9",
        "brand": "DUP LABS",
        "burn_captions": True,
        "caption_style": "bold",
        "transition": {"style": "fade", "frames": 12},
        "background": {"enabled": False},
        "music": {"enabled": False},
        "voice": {
            "engine": ENGINE_BY_LANG[lang],
            "lang": lang,
            "speaker": DEFAULT_SPEAKER_BY_LANG[lang],
            "rate": "100%",
        },
        "slides": slides,
    }


def write_outputs(
    script: dict[str, Any],
    deck: dict[str, Any],
    *,
    deck_out: Path | None,
    script_out: Path | None,
    overwrite: bool,
) -> tuple[Path, Path]:
    """Validate the deck and write the script + deck files. Refuses to overwrite unless asked."""
    try:
        validate_deck(deck, check_assets=False)
    except DeckValidationError as exc:
        raise DirectorScriptError(f"generated deck failed validate_deck: {exc}") from None

    deck_path = deck_out or (DECKS_DIR / f"{script['slug']}.json")
    script_path = script_out or (SCRIPTS_OUT_DIR / f"{script['slug']}.json")
    for p in (deck_path, script_path):
        if p.exists() and not overwrite:
            raise DirectorScriptError(f"{p} already exists; pass overwrite to replace it")
    deck_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
    deck_path.write_text(json.dumps(deck, ensure_ascii=False, indent=2), encoding="utf-8")
    return deck_path, script_path


# --------------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DUP Presenter Director Script (DeepSeek, fail-closed)")
    parser.add_argument("--topic", default="", help="Topic / brief (1..300 chars). Required unless --script-file is set.")
    parser.add_argument("--minutes", type=int, default=1, help=f"Runtime in minutes ({MIN_MINUTES}..{MAX_MINUTES})")
    parser.add_argument("--lang", default="ru", choices=sorted(ALLOWED_LANGS))
    parser.add_argument("--style", default="cinematic documentary", help="Visual style note (<=80 chars)")
    parser.add_argument("--script-file", default="", help="Offline: load and re-validate a saved script JSON (no LLM call)")
    parser.add_argument("--out", default="", help="Deck output path (default decks/<slug>.json)")
    parser.add_argument("--script-out", default="", help="Script output path (default work/director_scripts/<slug>.json)")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing output files")
    args = parser.parse_args(argv)

    try:
        if args.script_file:
            raw = json.loads(Path(args.script_file).read_text(encoding="utf-8"))
            script = revalidate_script(raw)
        else:
            if not args.topic.strip():
                print("[ERROR] --topic is required (or pass --script-file)", file=sys.stderr)
                return 2
            script = generate_script(args.topic, args.minutes, args.lang, args.style)
        deck = script_to_deck(script)
        deck_path, script_path = write_outputs(
            script,
            deck,
            deck_out=Path(args.out) if args.out else None,
            script_out=Path(args.script_out) if args.script_out else None,
            overwrite=args.overwrite,
        )
    except DirectorScriptError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[FAIL] cannot read script file: {exc.__class__.__name__}", file=sys.stderr)
        return 1

    types: dict[str, int] = {}
    for s in script["scenes"]:
        types[s["visual_type"]] = types.get(s["visual_type"], 0) + 1
    total = sum(s["target_sec"] for s in script["scenes"])
    print(f"[OK] '{script['title']}' | {script['minutes']} min requested | {len(script['scenes'])} scenes | {total}s planned")
    print(f"[OK] visual types: {types}")
    print(f"[OK] deck:   {deck_path}")
    print(f"[OK] script: {script_path}")
    print(
        "[WARN] facts and numbers are LLM output and NOT verified (fact_status="
        f"{script.get('fact_status', FACT_STATUS)}). Check them before publishing."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
