"""Fail-closed validation tests for the `cinema_clip` full-screen slide type."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_deck  # noqa: E402
from build_deck import DeckValidationError, validate_deck  # noqa: E402


def _deck(slide: dict) -> dict:
    return {
        "slug": "cinema-test",
        "lang": "en",
        "theme": "quantum_ledger",
        "aspect": "16:9",
        "brand": "DUP LABS",
        "background": {"enabled": False},
        "voice": {"engine": "kokoro_v1", "lang": "en", "speaker": "am_michael"},
        "slides": [slide],
    }


def _cinema_slide(**overrides) -> dict:
    slide = {
        "id": "c1",
        "tag": "01",
        "type": "cinema_clip",
        "title": "Big Bang",
        "voice_text": "The universe began in a single point of light.",
        "cinema": {"src": "cinema/test_clip.mp4", "badge": "13.8 BILLION YEARS AGO", "loop": True},
    }
    slide.update(overrides)
    return slide


class CinemaClipValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.public = Path(self._tmp.name)
        (self.public / "cinema").mkdir()
        (self.public / "cinema" / "test_clip.mp4").write_bytes(b"not-a-real-mp4-but-exists")
        self._patches = [
            mock.patch.object(build_deck, "PUBLIC_DIR", self.public),
            mock.patch.object(build_deck, "_media_duration_sec", return_value=12.04),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self) -> None:
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    def test_type_is_registered_as_allowed(self) -> None:
        self.assertIn("cinema_clip", build_deck.ALLOWED_TYPES)

    def test_valid_src_passes_and_records_probed_duration(self) -> None:
        deck = _deck(_cinema_slide())
        validate_deck(deck)
        self.assertEqual(deck["slides"][0]["cinema"]["clip_duration_sec"], 12.04)

    def test_background_query_without_src_is_accepted(self) -> None:
        slide = _cinema_slide(background_query="cosmos stars")
        slide["cinema"] = {"badge": "NO SRC"}
        validate_deck(_deck(slide))

    def test_missing_cinema_object_fails(self) -> None:
        slide = _cinema_slide()
        del slide["cinema"]
        with self.assertRaisesRegex(DeckValidationError, "requires a cinema object"):
            validate_deck(_deck(slide))

    def test_neither_src_nor_background_query_fails(self) -> None:
        slide = _cinema_slide()
        slide["cinema"] = {"badge": "EMPTY"}
        with self.assertRaisesRegex(DeckValidationError, "requires cinema.src or background_query"):
            validate_deck(_deck(slide))

    def test_path_traversal_is_rejected(self) -> None:
        slide = _cinema_slide()
        slide["cinema"]["src"] = "../secrets/key.mp4"
        with self.assertRaisesRegex(DeckValidationError, "safe relative path"):
            validate_deck(_deck(slide))

    def test_absolute_path_is_rejected(self) -> None:
        for bad in ("/etc/passwd.mp4", "\\Windows\\x.mp4"):
            with self.subTest(src=bad):
                slide = _cinema_slide()
                slide["cinema"]["src"] = bad
                with self.assertRaisesRegex(DeckValidationError, "safe relative path"):
                    validate_deck(_deck(slide))

    def test_missing_file_fails_closed(self) -> None:
        slide = _cinema_slide()
        slide["cinema"]["src"] = "cinema/does_not_exist.mp4"
        with self.assertRaisesRegex(DeckValidationError, "cinema.src file not found"):
            validate_deck(_deck(slide))


if __name__ == "__main__":
    unittest.main()
