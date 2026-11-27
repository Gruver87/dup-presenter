"""Item 4: validation must not write back into source decks.

Invariant: `validate_deck` never mutates its argument (writers validate then persist). The build pipeline
gets its annotated copy from `prepare_deck`, and the input dict is left untouched there as well.
"""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_deck  # noqa: E402


def _deck() -> dict:
    return {
        "slug": "pure-check",
        "lang": "en",
        "aspect": "16:9",
        "theme": "neon_cyber",
        "caption_style": "box",
        "background": {"enabled": False},
        "music": {"enabled": False},
        "voice": {"engine": "kokoro_v1", "lang": "en", "speaker": "am_michael", "rate": "86%"},
        "slides": [
            {
                "id": "s1",
                "type": "cinema_clip",
                "tag": "01",
                "title": "T",
                "voice_text": "Hello there.",
                "cinema": {
                    "loop": False,
                    "shots": [
                        {"src": "cinema/a.mp4", "duration_sec": 4.0},
                        {"src": "cinema/b.mp4", "duration_sec": 4.0},
                    ],
                },
            }
        ],
    }


class PureValidationTests(unittest.TestCase):
    def test_validate_deck_does_not_mutate_input(self) -> None:
        deck = _deck()
        before = copy.deepcopy(deck)
        build_deck.validate_deck(deck, check_assets=False)
        self.assertEqual(deck, before, "validate_deck must not add kind/clip_duration_sec to the source")
        self.assertNotIn("kind", deck["slides"][0]["cinema"]["shots"][0])

    def test_prepare_deck_annotates_a_copy_only(self) -> None:
        deck = _deck()
        before = copy.deepcopy(deck)
        annotated = build_deck.prepare_deck(deck, check_assets=False)
        self.assertEqual(deck, before, "prepare_deck must leave its input untouched")
        self.assertEqual(annotated["slides"][0]["cinema"]["shots"][0]["kind"], "video")
        self.assertIsNot(annotated, deck)

    def test_validate_still_fails_closed(self) -> None:
        deck = _deck()
        deck["aspect"] = "4:3"
        with self.assertRaises(build_deck.DeckValidationError):
            build_deck.validate_deck(deck, check_assets=False)


if __name__ == "__main__":
    unittest.main()
