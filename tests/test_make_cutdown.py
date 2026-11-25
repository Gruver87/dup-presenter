"""make_cutdown must never emit two adjacent chart_story slides (fail-closed)."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import make_cutdown  # noqa: E402

_BASE = json.loads((ROOT / "decks" / "studio-universal-demo-v2.json").read_text(encoding="utf-8"))
_BY_ID = {s["id"]: s for s in _BASE["slides"]}
STAT = _BY_ID["s1"]  # stat_burst
VERSUS = _BY_ID["s2"]  # versus_split
BAR = _BY_ID["s3"]  # chart_story bar
BROLL = _BY_ID["s4"]  # broll_cinematic
LINE = _BY_ID["s5"]  # chart_story line
DONUT = _BY_ID["s6"]  # chart_story donut
OUTRO = _BY_ID["s7"]  # outro_3d


def _deck(slides: list[dict]) -> dict:
    deck = copy.deepcopy(_BASE)
    deck["slides"] = [copy.deepcopy(s) for s in slides]
    return deck


def _types(short: dict) -> list[str]:
    return [s["type"] for s in short["slides"]]


def _has_adjacent_charts(types: list[str]) -> bool:
    return any(a == "chart_story" and b == "chart_story" for a, b in zip(types, types[1:]))


class MakeCutdownAdjacentChartsTests(unittest.TestCase):
    def test_adjacent_charts_are_repaired_with_non_chart_slide(self) -> None:
        # Fill order would pick bar + line (adjacent). Line must be replaced by the versus slide.
        deck = _deck([STAT, BAR, LINE, VERSUS, OUTRO])
        short = make_cutdown.build_short_cutdown(deck, max_slides=4)
        self.assertEqual(_types(short), ["stat_burst", "chart_story", "versus_split", "outro_3d"])
        self.assertFalse(_has_adjacent_charts(_types(short)))

    def test_repaired_short_is_still_valid_and_renumbered(self) -> None:
        deck = _deck([STAT, BAR, LINE, VERSUS, OUTRO])
        short = make_cutdown.build_short_cutdown(deck, max_slides=4)
        self.assertEqual([s["id"] for s in short["slides"]], ["short_1", "short_2", "short_3", "short_4"])
        self.assertEqual(short["aspect"], "9:16")

    def test_chart_outro_with_no_middle_slot_fails_closed(self) -> None:
        # Hero stat -> bar (only middle) -> line (outro): no non-chart replacement exists.
        deck = _deck([STAT, BAR, LINE])
        with self.assertRaises(ValueError):
            make_cutdown.build_short_cutdown(deck, max_slides=3)

    def test_non_adjacent_selection_is_unchanged(self) -> None:
        deck = _deck([STAT, VERSUS, BROLL, BAR, LINE, DONUT, OUTRO])
        short = make_cutdown.build_short_cutdown(deck, max_slides=4)
        self.assertEqual(_types(short), ["stat_burst", "versus_split", "broll_cinematic", "outro_3d"])
        self.assertFalse(_has_adjacent_charts(_types(short)))

    def test_full_demo_deck_produces_no_adjacent_charts(self) -> None:
        for max_slides in (3, 4, 5):
            short = make_cutdown.build_short_cutdown(_BASE, max_slides=max_slides)
            self.assertFalse(_has_adjacent_charts(_types(short)), f"max_slides={max_slides}: {_types(short)}")


if __name__ == "__main__":
    unittest.main()
