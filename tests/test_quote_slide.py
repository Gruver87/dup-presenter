"""Quote slide type: schema accept/reject (fail-closed)."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_deck  # noqa: E402
from build_deck import DeckValidationError  # noqa: E402

BASE = ROOT / "decks" / "caption-karaoke-demo.json"


def _deck_with_quote(**slide_fields) -> dict:
    data = copy.deepcopy(json.loads(BASE.read_text(encoding="utf-8")))
    quote = {
        "id": "q1",
        "tag": "QUOTE",
        "type": "quote",
        "title": "Heuristic scores are not guarantees.",
        "subtitle": "Project README",
        "voice_text": "Heuristic scores are not guarantees.",
    }
    quote.update(slide_fields)
    data["slides"].insert(1, quote)
    return data


class QuoteSchemaTests(unittest.TestCase):
    def test_valid_quote_passes(self) -> None:
        build_deck.validate_deck(_deck_with_quote(), check_assets=False)

    def test_attribution_is_optional(self) -> None:
        data = _deck_with_quote()
        del data["slides"][1]["subtitle"]
        build_deck.validate_deck(data, check_assets=False)

    def test_empty_quote_is_refused(self) -> None:
        with self.assertRaises(DeckValidationError):
            build_deck.validate_deck(_deck_with_quote(title="   "), check_assets=False)

    def test_overlong_quote_is_refused(self) -> None:
        with self.assertRaises(DeckValidationError):
            build_deck.validate_deck(_deck_with_quote(title="x" * 221), check_assets=False)

    def test_non_string_attribution_is_refused(self) -> None:
        with self.assertRaises(DeckValidationError):
            build_deck.validate_deck(_deck_with_quote(subtitle=["someone"]), check_assets=False)


if __name__ == "__main__":
    unittest.main()
