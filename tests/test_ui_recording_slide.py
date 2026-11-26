"""Tests for the ui_recording deck slide (schema, strict asset path, clip duration)."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_deck  # noqa: E402
from build_deck import DeckValidationError, validate_deck  # noqa: E402

DEMO_DECK = ROOT / "decks" / "ui-recording-demo.json"


def _deck_with(slide: dict) -> dict:
    """Minimal valid deck around one ui_recording slide (schema only, no asset check)."""
    return {
        "slug": "rec-test",
        "lang": "en",
        "theme": "cosmic_radar",
        "slides": [copy.deepcopy(slide)],
    }


def _slide(**overrides) -> dict:
    slide = {
        "id": "s1",
        "tag": "UI",
        "type": "ui_recording",
        "title": "Recorded UI",
        "voice_text": "Recorded clip.",
        "recording": {"src": "ui_recordings/example-local-demo.mp4", "caption": "Live UI"},
    }
    slide.update(overrides)
    return slide


class UiRecordingSchemaTests(unittest.TestCase):
    def test_valid_slide_passes_schema(self) -> None:
        validate_deck(_deck_with(_slide()), check_assets=False)

    def test_demo_deck_passes_schema(self) -> None:
        validate_deck(json.loads(DEMO_DECK.read_text(encoding="utf-8")), check_assets=False)

    def test_rejects_missing_recording_object(self) -> None:
        slide = _slide()
        del slide["recording"]
        with self.assertRaises(DeckValidationError):
            validate_deck(_deck_with(slide), check_assets=False)

    def test_rejects_paths_outside_ui_recordings(self) -> None:
        bad_srcs = [
            "../secrets.mp4",
            "ui_recordings/../../etc.mp4",
            "C:/Users/x/video.mp4",
            "/abs/video.mp4",
            "ui_recordings/clip.webm",
            "ui_recordings/Upper.mp4",
            "screens/radar.mp4",
            "",
        ]
        for src in bad_srcs:
            with self.subTest(src=src), self.assertRaises(DeckValidationError):
                validate_deck(_deck_with(_slide(recording={"src": src})), check_assets=False)

    def test_rejects_non_string_caption(self) -> None:
        with self.assertRaises(DeckValidationError):
            validate_deck(_deck_with(_slide(recording={"src": "ui_recordings/a.mp4", "caption": 5})), check_assets=False)

    def test_missing_clip_is_refused_when_assets_checked(self) -> None:
        deck = _deck_with(_slide(recording={"src": "ui_recordings/no-such-clip.mp4"}))
        with self.assertRaises(DeckValidationError) as ctx:
            validate_deck(deck, check_assets=True)
        self.assertIn("missing recording file", str(ctx.exception))


class ClipDurationTests(unittest.TestCase):
    # tests/fixtures/clip_2s.mp4 is a committed 2.000 s black clip (made once with full ffmpeg).
    # The Remotion-bundled ffmpeg cannot synthesise clips in tests, so the fixture is read as-is.
    FIXTURE = ROOT / "tests" / "fixtures" / "clip_2s.mp4"

    def test_media_duration_matches_clip(self) -> None:
        duration = build_deck._media_duration_sec(self.FIXTURE)
        self.assertAlmostEqual(duration, 2.0, delta=0.2)

    def test_media_duration_fails_closed_on_missing_file(self) -> None:
        with self.assertRaises(DeckValidationError):
            build_deck._media_duration_sec(Path(tempfile.gettempdir()) / "__no_such_clip__.mp4")


class DoctorRecordingEstimateTests(unittest.TestCase):
    """deck_doctor must size a ui_recording slide to its clip (same rule as build_deck), without needing ffprobe."""

    def _slide(self, *, voice_text: str = "коротко") -> dict:
        return {
            "id": "s2",
            "type": "ui_recording",
            "title": "t",
            "voice_text": voice_text,
            "recording": {"src": "ui_recordings/x.mp4"},
        }

    def test_clip_longer_than_speech_extends_estimate(self) -> None:
        import deck_doctor

        sec = deck_doctor._estimate_slide_sec(self._slide(), lambda _p: 12.48)
        self.assertEqual(sec, 14.0)  # ceil(12.48) + 1

    def test_speech_longer_than_clip_keeps_speech_estimate(self) -> None:
        import deck_doctor

        long_text = " ".join(["слово"] * 60)
        sec = deck_doctor._estimate_slide_sec(self._slide(voice_text=long_text), lambda _p: 2.0)
        self.assertGreater(sec, 3.0)

    def test_probe_failure_is_reported_as_doctor_error(self) -> None:
        import deck_doctor

        def _boom(_p: Path) -> float:
            raise DeckValidationError("ffprobe failed on clip")

        with self.assertRaises(DeckValidationError):
            deck_doctor._estimate_slide_sec(self._slide(), _boom)


if __name__ == "__main__":
    unittest.main()
