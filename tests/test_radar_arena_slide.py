"""Fail-closed validation tests for the radar_arena slide type."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_deck as bd  # noqa: E402


def _base_deck(slide: dict) -> dict:
    return {
        "slug": "radar-arena-test",
        "lang": "ru",
        "theme": "cosmic_radar",
        "voice": {"lang": "ru", "speaker": "eugene", "rate": "90%"},
        "slides": [slide],
    }


class RadarArenaValidationTests(unittest.TestCase):
    def test_all_four_modes_validate(self) -> None:
        for mode in ("core_army", "live_candles", "trap_gauntlet", "integer_vault"):
            with self.subTest(mode=mode):
                deck = _base_deck(
                    {
                        "id": f"s_{mode}",
                        "type": "radar_arena",
                        "title": "Test Arena",
                        "voice_text": "Тестовый текст слайда арены.",
                        "arena": {"mode": mode, "badge": "ARENA", "headline": "Заголовок"},
                    }
                )
                bd.validate_deck(deck, check_assets=False)

    def test_missing_arena_object_refused(self) -> None:
        deck = _base_deck(
            {
                "id": "s1",
                "type": "radar_arena",
                "title": "No Arena",
                "voice_text": "Текст",
            }
        )
        with self.assertRaises(bd.DeckValidationError):
            bd.validate_deck(deck, check_assets=False)

    def test_unknown_mode_refused(self) -> None:
        deck = _base_deck(
            {
                "id": "s1",
                "type": "radar_arena",
                "title": "Bad Mode",
                "voice_text": "Текст",
                "arena": {"mode": "invented_mode"},
            }
        )
        with self.assertRaises(bd.DeckValidationError):
            bd.validate_deck(deck, check_assets=False)

    def test_blank_optional_string_refused(self) -> None:
        deck = _base_deck(
            {
                "id": "s1",
                "type": "radar_arena",
                "title": "Blank Badge",
                "voice_text": "Текст",
                "arena": {"mode": "core_army", "badge": "   "},
            }
        )
        with self.assertRaises(bd.DeckValidationError):
            bd.validate_deck(deck, check_assets=False)


if __name__ == "__main__":
    unittest.main()
