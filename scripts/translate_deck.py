"""Deck translator (RU <-> EN) with code/metric/URL preservation and fail-closed validation.

Translates only human-facing fields (title, subtitle, tag, tagline, bullets, kpis.label,
screens.caption, arch.nodes.label, arch.edges.label, voice_text) while locking code lines,
file paths, URLs, numeric values, and brand tokens untouched.

Supports --offline-only (forces local Ollama only; refuses cloud OpenAI-compatible endpoints).

Usage:
    python scripts/translate_deck.py decks/radar-pro.json --to en --out decks/radar-pro-en-auto.json
    python scripts/translate_deck.py decks/radar-pro-en.json --to ru --offline-only
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from build_deck import validate_deck  # noqa: E402
from plan_deck import ollama_chat, openai_compatible_chat  # noqa: E402

CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")


class DeckTranslationError(RuntimeError):
    """Fail-closed error during deck translation."""


def _extract_translatable(slide: dict) -> dict:
    payload: dict = {"id": slide["id"]}
    for key in ("tag", "title", "subtitle", "tagline", "voice_text"):
        if slide.get(key):
            payload[key] = slide[key]
    if slide.get("bullets"):
        payload["bullets"] = [{"title": b.get("title", ""), "desc": b.get("desc", "")} for b in slide["bullets"]]
    if slide.get("kpis"):
        payload["kpis"] = [{"value": k.get("value", ""), "label": k.get("label", "")} for k in slide["kpis"]]
    if slide.get("screens"):
        payload["screens"] = [{"caption": sc.get("caption", "")} for sc in slide["screens"]]
    if slide.get("arch"):
        payload["arch"] = {
            "nodes": [{"id": n["id"], "label": n.get("label", "")} for n in (slide["arch"].get("nodes") or [])],
            "edges": [{"label": e.get("label", "")} for e in (slide["arch"].get("edges") or [])],
        }
    return payload


def _merge_translated(slide: dict, tr: dict) -> dict:
    out = copy.deepcopy(slide)
    out.pop("voice_ssml", None)
    for key in ("tag", "title", "subtitle", "tagline", "voice_text"):
        if key in tr and isinstance(tr[key], str) and tr[key].strip():
            out[key] = tr[key].strip()
    if isinstance(tr.get("bullets"), list) and isinstance(out.get("bullets"), list):
        for orig, new in zip(out["bullets"], tr["bullets"]):
            if isinstance(new, dict):
                if new.get("title"):
                    orig["title"] = str(new["title"]).strip()
                if new.get("desc"):
                    orig["desc"] = str(new["desc"]).strip()
    if isinstance(tr.get("kpis"), list) and isinstance(out.get("kpis"), list):
        for orig, new in zip(out["kpis"], tr["kpis"]):
            if isinstance(new, dict) and new.get("label"):
                orig["label"] = str(new["label"]).strip()
                # Preserve exact numeric value unless units needed translation within <=12 chars
                val = str(new.get("value") or orig["value"]).strip()
                if 1 <= len(val) <= 12:
                    orig["value"] = val
    if isinstance(tr.get("screens"), list) and isinstance(out.get("screens"), list):
        for orig, new in zip(out["screens"], tr["screens"]):
            if isinstance(new, dict) and new.get("caption"):
                orig["caption"] = str(new["caption"]).strip()
    if isinstance(tr.get("arch"), dict) and isinstance(out.get("arch"), dict):
        tr_nodes = {n["id"]: n.get("label") for n in (tr["arch"].get("nodes") or []) if isinstance(n, dict) and n.get("id")}
        for n in out["arch"].get("nodes") or []:
            if n.get("id") in tr_nodes and tr_nodes[n["id"]]:
                n["label"] = str(tr_nodes[n["id"]]).strip()
        tr_edges = tr["arch"].get("edges") or []
        for orig_e, new_e in zip(out["arch"].get("edges") or [], tr_edges):
            if isinstance(new_e, dict) and new_e.get("label"):
                orig_e["label"] = str(new_e["label"]).strip()
    return out


def _call_llm(messages: list[dict], offline_only: bool, ollama_model: str, ollama_host: str) -> str:
    if offline_only or not os.environ.get("LLM_API_KEY", "").strip():
        return ollama_chat(ollama_model, messages, ollama_host)
    return openai_compatible_chat(messages)


def translate_deck(
    deck: dict,
    target_lang: str,
    offline_only: bool = False,
    ollama_model: str = "qwen2.5:7b",
    ollama_host: str = "http://127.0.0.1:11434",
) -> dict:
    """Translate a deck into target_lang ('en' or 'ru') and validate fail-closed."""
    if target_lang not in {"en", "ru"}:
        raise DeckTranslationError(f"Unsupported target language {target_lang!r}; use 'en' or 'ru'")

    slides_in = [_extract_translatable(s) for s in (deck.get("slides") or [])]
    lang_name = "English" if target_lang == "en" else "Russian"
    extra_rules = (
        "- Output MUST contain ZERO Cyrillic characters.\n"
        "- Use concise, natural engineering English suitable for spoken narration.\n"
        if target_lang == "en"
        else "- Use natural Russian engineering phrasing; prefer 'список наблюдения' (not вотчлист), "
             "'загрузка данных' (not инжест), 'нативный модуль'.\n"
    )
    system = (
        f"You are a technical presentation translator. Translate the JSON array of slides into {lang_name}.\n"
        "STRICT RULES:\n"
        "- Return ONLY a valid JSON array matching the exact input schema and slide count.\n"
        "- Keep all numbers, metrics, percentages, brand names (DUP Labs, DUP Market Radar, DUP Protocol, Rust, Python, PyO3), and slide `id`s exact.\n"
        "- Do NOT invent facts, features, or claims that are not in the source.\n"
        "- Keep KPI `value` <= 12 characters.\n"
        + extra_rules
    )
    raw = _call_llm(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(slides_in, ensure_ascii=False)},
        ],
        offline_only=offline_only,
        ollama_model=ollama_model,
        ollama_host=ollama_host,
    )
    m = re.search(r"\[[\s\S]*\]", raw)
    if not m:
        raise DeckTranslationError(f"LLM did not return a JSON array: {raw[:300]}")
    translated_list = json.loads(m.group(0))
    if not isinstance(translated_list, list) or len(translated_list) != len(slides_in):
        raise DeckTranslationError(
            f"Translated slide count mismatch: got {len(translated_list) if isinstance(translated_list, list) else type(translated_list)}, expected {len(slides_in)}"
        )

    out = copy.deepcopy(deck)
    base_slug = re.sub(r"-(en|ru)$", "", str(deck["slug"]))
    out["slug"] = f"{base_slug}-{target_lang}"
    out["lang"] = target_lang
    out["slides"] = [_merge_translated(orig, tr) for orig, tr in zip(deck["slides"], translated_list)]

    if target_lang == "en":
        # Fail-closed check: zero Cyrillic left in translated English fields
        for s in out["slides"]:
            check_blob = json.dumps(_extract_translatable(s), ensure_ascii=False)
            if CYRILLIC_RE.search(check_blob):
                raise DeckTranslationError(f"Slide {s['id']} still contains Cyrillic after EN translation")
        out["voice"] = {
            "engine": "kokoro_v1",
            "lang": "en",
            "speaker": "am_michael",
            "rate": "100%",
            "ambient_volume": float((deck.get("voice") or {}).get("ambient_volume", 0.14)),
        }
    else:
        out["voice"] = {
            "engine": "edge_tts",
            "lang": "ru",
            "speaker": "dmitry",
            "fallback_speaker": "eugene",
            "rate": "95%",
            "ambient_volume": float((deck.get("voice") or {}).get("ambient_volume", 0.14)),
        }

    validate_deck(out)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="DUP Presenter deck translator (RU <-> EN)")
    parser.add_argument("deck", help="Source deck JSON")
    parser.add_argument("--to", required=True, choices=["en", "ru"], help="Target language")
    parser.add_argument("--out", default="", help="Output path (defaults to decks/<slug>-<lang>.json)")
    parser.add_argument("--offline-only", action="store_true", help="Force local Ollama only (no cloud LLM)")
    parser.add_argument("--ollama-model", default=os.environ.get("OLLAMA_MODEL", "qwen2.5:7b"))
    parser.add_argument("--ollama-host", default=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"))
    args = parser.parse_args()

    src_p = Path(args.deck)
    if not src_p.is_absolute():
        src_p = ROOT / src_p
    deck = json.loads(src_p.read_text(encoding="utf-8"))
    try:
        translated = translate_deck(
            deck,
            target_lang=args.to,
            offline_only=args.offline_only,
            ollama_model=args.ollama_model,
            ollama_host=args.ollama_host,
        )
    except Exception as exc:
        print(f"[ERROR] Translation failed: {exc}", file=sys.stderr)
        return 1

    out_p = Path(args.out) if args.out else (ROOT / "decks" / f"{translated['slug']}.json")
    if not out_p.is_absolute():
        out_p = ROOT / out_p
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(translated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[translate] wrote {out_p} (lang={args.to}, slides={len(translated['slides'])})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
