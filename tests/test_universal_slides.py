"""Unit & fail-closed validation tests for Phase B universal slide types."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from build_deck import DeckValidationError, validate_deck  # noqa: E402


def _base_deck(slides: list[dict]) -> dict:
    return {
        "slug": "universal-test",
        "lang": "en",
        "theme": "quantum_ledger",
        "aspect": "16:9",
        "brand": "DUP LABS",
        "voice": {"engine": "kokoro_v1", "lang": "en", "speaker": "am_michael"},
        "slides": slides,
    }


def _valid_slides() -> list[dict]:
    return [
        {
            "id": "s1",
            "tag": "HOOK",
            "type": "stat_burst",
            "title": "Zero Float Drift",
            "voice_text": "Zero floating point arithmetic in money.",
            "stat_burst": {
                "kicker": "CORE INVARIANT",
                "headline": "0 FLOAT",
                "caption": "Every balance is stored in exact 64-bit integer satoshis.",
                "chips": [{"label": "int64"}, {"label": "Fail-Closed"}],
            },
        },
        {
            "id": "s2",
            "tag": "VERSUS",
            "type": "versus_split",
            "title": "Legacy vs Modern",
            "voice_text": "Compare legacy silent fallbacks against fail-closed systems.",
            "versus": {
                "left": {"label": "Legacy", "badge": "RISK", "points": ["Silent fallbacks", "Float drift"]},
                "right": {"label": "Modern", "badge": "SAFE", "points": ["Fail-closed gates", "Integer satoshis"]},
                "verdict": "Fail loudly in tests, never silently in production.",
            },
        },
        {
            "id": "s3",
            "tag": "BENCHMARK",
            "type": "chart_story",
            "title": "Throughput Comparison",
            "voice_text": "Chart showing verified throughput.",
            "chart": {
                "kind": "bar",
                "unit": "ops/s",
                "series": [
                    {"label": "Baseline", "value": 120},
                    {"label": "Rust Core", "value": 980},
                ],
            },
        },
        {
            "id": "s4",
            "tag": "STORY",
            "type": "broll_cinematic",
            "title": "Built for Any Story",
            "voice_text": "Full-bleed cinematic slide for storytelling.",
            "broll": {
                "badge": "CINEMATIC",
                "caption": "Works with or without a background image.",
                "callouts": ["Ken Burns motion", "High-contrast typography"],
            },
        },
    ]


class UniversalSlidesTests(unittest.TestCase):
    def test_all_four_universal_slides_validate(self) -> None:
        validate_deck(_base_deck(_valid_slides()))

    def test_versus_split_refuses_too_few_points(self) -> None:
        s = copy.deepcopy(_valid_slides()[1])
        s["versus"]["left"]["points"] = ["Only one"]
        with self.assertRaises(DeckValidationError):
            validate_deck(_base_deck([s]))

    def test_chart_story_refuses_bad_kind_and_negative_value(self) -> None:
        s = copy.deepcopy(_valid_slides()[2])
        s["chart"]["kind"] = "pie3d"
        with self.assertRaises(DeckValidationError):
            validate_deck(_base_deck([s]))

        s2 = copy.deepcopy(_valid_slides()[2])
        s2["chart"]["series"][0]["value"] = -5
        with self.assertRaises(DeckValidationError):
            validate_deck(_base_deck([s2]))

    def test_stat_burst_refuses_overlong_headline(self) -> None:
        s = copy.deepcopy(_valid_slides()[0])
        s["stat_burst"]["headline"] = "X" * 30
        with self.assertRaises(DeckValidationError):
            validate_deck(_base_deck([s]))

    def test_broll_refuses_path_traversal(self) -> None:
        s = copy.deepcopy(_valid_slides()[3])
        s["broll"]["image"] = "../../etc/passwd"
        with self.assertRaises(DeckValidationError):
            validate_deck(_base_deck([s]))


if __name__ == "__main__":
    unittest.main()
