"""Burned-in caption presets (deck field caption_style): schema accept/reject, fail-closed."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_deck  # noqa: E402
from build_deck import DeckValidationError  # noqa: E402

BASE = ROOT / "decks" / "radar-cosmic-v4-en.json"


def _deck(**extra) -> dict:
    data = json.loads(BASE.read_text(encoding="utf-8"))
    data.update(extra)
    return data


class CaptionStyleSchemaTests(unittest.TestCase):
    def test_default_is_box_and_valid(self) -> None:
        build_deck.validate_deck(_deck(), check_assets=False)

    def test_each_allowed_style_is_accepted(self) -> None:
        for style in ("box", "karaoke", "bold"):
            with self.subTest(style=style):
                build_deck.validate_deck(_deck(caption_style=style), check_assets=False)

    def test_unknown_style_is_refused(self) -> None:
        with self.assertRaises(DeckValidationError):
            build_deck.validate_deck(_deck(caption_style="neon_glow"), check_assets=False)

    def test_non_string_style_is_refused(self) -> None:
        with self.assertRaises(DeckValidationError):
            build_deck.validate_deck(_deck(caption_style=["karaoke"]), check_assets=False)


if __name__ == "__main__":
    unittest.main()
