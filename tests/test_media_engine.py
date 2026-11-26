"""Offline tests for the opt-in cinema video engine field (`media_engine`). Default must stay `offthread`."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from build_deck import ALLOWED_MEDIA_ENGINES, DeckValidationError, validate_deck  # noqa: E402


def _deck(**extra) -> dict:
    return {
        "slug": "engine-test",
        "lang": "en",
        "theme": "quantum_ledger",
        "aspect": "16:9",
        "brand": "DUP LABS",
        "background": {"enabled": False},
        "voice": {"engine": "kokoro_v1", "lang": "en", "speaker": "am_michael"},
        "slides": [{"id": "q1", "tag": "01", "type": "quote", "title": "Hello", "voice_text": "Hello there."}],
        **extra,
    }


class MediaEngineFieldTests(unittest.TestCase):
    def test_allowed_values_are_exactly_offthread_and_media(self) -> None:
        self.assertEqual(ALLOWED_MEDIA_ENGINES, frozenset({"offthread", "media"}))

    def test_field_is_optional(self) -> None:
        validate_deck(_deck(), check_assets=False)

    def test_both_allowed_values_validate(self) -> None:
        for engine in ("offthread", "media"):
            validate_deck(_deck(media_engine=engine), check_assets=False)

    def test_unknown_engine_is_refused(self) -> None:
        for bad in ("ffmpeg", "Media", "", "html5"):
            with self.assertRaises(DeckValidationError, msg=bad):
                validate_deck(_deck(media_engine=bad), check_assets=False)


if __name__ == "__main__":
    unittest.main()
