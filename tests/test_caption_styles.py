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


from audio_fx import build_word_captions  # noqa: E402

NARRATION = "First sentence here. Second one follows! Is there a third?"


class KaraokeWordTimingTests(unittest.TestCase):
    """Karaoke must never silently degrade to box for a voiced narration: every cue carries words."""

    def _assert_words_everywhere(self, cues: list[dict]) -> None:
        self.assertTrue(cues, "voiced narration must produce caption cues")
        for cue in cues:
            self.assertTrue(cue.get("words"), f"cue without words: {cue.get('text')!r}")
            self.assertEqual(
                [w["w"] for w in cue["words"]],
                cue["text"].split(),
                "word tokens must match the cue text",
            )
            for w in cue["words"]:
                self.assertLessEqual(w["start"], w["end"])

    def test_words_without_tts_boundaries(self) -> None:
        # Kokoro and Silero return no boundaries: proportional sentence spans.
        self._assert_words_everywhere(build_word_captions(NARRATION, 6.0, boundaries=None))

    def test_words_with_matching_tts_boundaries(self) -> None:
        # Edge: one real boundary per sentence.
        bounds = [{"start_sec": 0.0, "end_sec": 1.5}, {"start_sec": 1.6, "end_sec": 3.0}, {"start_sec": 3.1, "end_sec": 5.0}]
        self._assert_words_everywhere(build_word_captions(NARRATION, 6.0, boundaries=bounds))

    def test_words_with_mismatched_tts_boundaries(self) -> None:
        bounds = [{"start_sec": 0.0, "end_sec": 2.0}]
        self._assert_words_everywhere(build_word_captions(NARRATION, 6.0, boundaries=bounds))


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
