"""Auto-Cutdown generator: turns any 16:9 presentation deck into a punchy 9:16 vertical Short (~45-60s).

Deterministic, zero-hallucination: never invents new claims. Selects the highest-impact slides
(hero -> KPI/architecture -> live UI/code -> outro), compacts each slide's voice_text to the
leading 1-2 crisp sentences, switches aspect to 9:16, enables karaoke captions + fast slide
transitions, and runs fail-closed deck validation.

Usage:
    python scripts/make_cutdown.py decks/radar-pro.json
    python scripts/make_cutdown.py decks/radar-pro.json --out decks/radar-pro-short.json --max-slides 4
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from build_deck import validate_deck  # noqa: E402

PREFERRED_MIDDLE_TYPES = ["kpi", "screen_split", "arch_flow", "code_split", "terminal", "timeline"]


def _compact_voice(text: str, max_chars: int = 165) -> str:
    """Keep the first 1-2 complete sentences up to max_chars without cutting mid-sentence."""
    clean = " ".join((text or "").split())
    if len(clean) <= max_chars:
        return clean
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", clean) if s.strip()]
    if not sents:
        return clean[:max_chars]
    picked: list[str] = [sents[0]]
    for s in sents[1:]:
        cand = " ".join(picked + [s])
        if len(cand) <= max_chars:
            picked.append(s)
        else:
            break
    return " ".join(picked)


CHART_TYPES = frozenset({"chart_story"})


def _repair_adjacent_charts(
    mid: list[dict],
    hero: dict,
    outro: dict,
    pool: list[dict],
    used_ids: set[str],
    order_map: dict[str, int],
) -> list[dict]:
    """Ensure no two chart slides are adjacent in the final short (fail-closed).

    A conflicting middle slide is replaced by the first unused non-chart slide from the deck.
    If no middle slot or no replacement exists, raise instead of silently producing a bad short.
    """
    current = list(mid)
    for _ in range(len(current) + 2):
        picked = [hero, *current, outro]
        conflict = next(
            (
                i
                for i in range(len(picked) - 1)
                if picked[i].get("type") in CHART_TYPES and picked[i + 1].get("type") in CHART_TYPES
            ),
            None,
        )
        if conflict is None:
            return current
        # Prefer replacing the later slide of the pair when it is a middle slide, else the earlier one.
        target_pos = conflict + 1 if 1 <= conflict + 1 <= len(current) else conflict
        if not (1 <= target_pos <= len(current)):
            raise ValueError(
                "make_cutdown: adjacent chart_story slides at the hero/outro boundary cannot be separated "
                "(no middle slot); reorder the deck or add a non-chart slide"
            )
        victim = current[target_pos - 1]
        replacement = next(
            (s for s in pool if s.get("type") not in CHART_TYPES and s["id"] not in used_ids),
            None,
        )
        if replacement is None:
            raise ValueError(
                f"make_cutdown: adjacent chart_story slides around {victim['id']!r} and no unused "
                "non-chart slide exists to replace it; add a non-chart slide to the deck"
            )
        used_ids.discard(victim["id"])
        used_ids.add(replacement["id"])
        current = [s for s in current if s is not victim] + [replacement]
        current.sort(key=lambda s: order_map[s["id"]])
    raise ValueError("make_cutdown: could not resolve adjacent chart_story slides")


def build_short_cutdown(deck: dict, max_slides: int = 4, max_chars_per_slide: int = 165) -> dict:
    """Create a validated 9:16 vertical Short deck from an existing 16:9 deck."""
    slides = deck.get("slides") or []
    if len(slides) < 2:
        raise ValueError("Deck must have at least 2 slides to create a cutdown")

    max_slides = max(2, min(max_slides, len(slides)))
    hero = slides[0]
    outro = slides[-1]
    middle_pool = slides[1:-1]

    selected_mid: list[dict] = []
    used_ids: set[str] = {hero["id"], outro["id"]}
    want_mid = max(0, max_slides - 2)

    # First pass: pick one slide of each preferred visual type in priority order
    for pref in PREFERRED_MIDDLE_TYPES:
        if len(selected_mid) >= want_mid:
            break
        for s in middle_pool:
            if s.get("type") == pref and s["id"] not in used_ids:
                selected_mid.append(s)
                used_ids.add(s["id"])
                break

    # Fill any remaining slots preserving original deck order
    if len(selected_mid) < want_mid:
        for s in middle_pool:
            if len(selected_mid) >= want_mid:
                break
            if s["id"] not in used_ids:
                selected_mid.append(s)
                used_ids.add(s["id"])

    # Restore narrative order from original deck
    order_map = {s["id"]: i for i, s in enumerate(slides)}
    selected_mid.sort(key=lambda s: order_map[s["id"]])
    selected_mid = _repair_adjacent_charts(selected_mid, hero, outro, middle_pool, used_ids, order_map)
    picked = [copy.deepcopy(hero), *[copy.deepcopy(s) for s in selected_mid], copy.deepcopy(outro)]

    for i, s in enumerate(picked, start=1):
        s["id"] = f"short_{i}"
        if s.get("voice_text"):
            s["voice_text"] = _compact_voice(s["voice_text"], max_chars=max_chars_per_slide)
        s.pop("voice_ssml", None)
        # Keep portrait slides airy: cap bullets to 3 on vertical layout
        if isinstance(s.get("bullets"), list) and s.get("type") != "timeline":
            s["bullets"] = s["bullets"][:3]

    short = copy.deepcopy(deck)
    base_slug = str(deck["slug"]).removesuffix("-short")
    short["slug"] = f"{base_slug}-short"
    short["aspect"] = "9:16"
    short["burn_captions"] = True
    short["transition"] = {"style": "slide", "frames": 10}
    short.setdefault("sfx", {"enabled": True, "volume": 0.22})
    short["slides"] = picked

    validate_deck(short)
    return short


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a 9:16 ~60s Short cutdown deck from any 16:9 deck")
    parser.add_argument("deck", help="Input deck JSON (e.g. decks/radar-pro.json)")
    parser.add_argument("--out", default="", help="Output deck path (defaults to decks/<slug>-short.json)")
    parser.add_argument("--max-slides", type=int, default=4, help="Slide count for the short (2..6, default 4)")
    parser.add_argument("--max-chars", type=int, default=165, help="Max voice_text chars per slide")
    args = parser.parse_args()

    src_p = Path(args.deck)
    if not src_p.is_absolute():
        src_p = ROOT / src_p
    deck = json.loads(src_p.read_text(encoding="utf-8"))
    short = build_short_cutdown(deck, max_slides=args.max_slides, max_chars_per_slide=args.max_chars)

    out_p = Path(args.out) if args.out else (ROOT / "decks" / f"{short['slug']}.json")
    if not out_p.is_absolute():
        out_p = ROOT / out_p
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(short, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    est_chars = sum(len(s.get("voice_text") or "") for s in short["slides"])
    est_sec = round(est_chars / 13.5 + len(short["slides"]) * 1.2)
    print(f"[cutdown] wrote {out_p} ({len(short['slides'])} slides, 9:16, ~{est_sec}s est)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
