"""Regression tests: loop=false cinema slides must not leave a black tail after their shots."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import deck_doctor  # noqa: E402


def _probe(lengths: dict[str, float]):
    def _inner(path: Path) -> float:
        return lengths.get(path.name, 0.0)

    return _inner


class CinemaCoverageTests(unittest.TestCase):
    def test_loop_false_short_shots_is_error(self) -> None:
        # The shipped defect: a 12 s card with loop=false inside a 20 s slide.
        slides = [
            {
                "id": "u10",
                "type": "cinema_clip",
                "cinema": {
                    "loop": False,
                    "shots": [{"src": "cinema/u10.mp4", "duration_sec": 12.0, "playback_rate": 1.0}],
                },
            }
        ]
        errs = deck_doctor.cinema_coverage_errors(slides, [20.0], _probe({"u10.mp4": 12.04}))
        self.assertEqual(len(errs), 1)
        self.assertIn("black tail", errs[0])
        self.assertIn("u10", errs[0])

    def test_loop_default_true_is_not_checked(self) -> None:
        slides = [
            {
                "id": "u0",
                "type": "cinema_clip",
                "cinema": {"shots": [{"src": "cinema/a.mp4", "duration_sec": 12.0}]},
            }
        ]
        self.assertEqual(deck_doctor.cinema_coverage_errors(slides, [30.0], _probe({"a.mp4": 12.0})), [])

    def test_loop_false_with_full_coverage_passes(self) -> None:
        slides = [
            {
                "id": "u1",
                "type": "cinema_clip",
                "cinema": {
                    "loop": False,
                    "shots": [
                        {"src": "cinema/a.mp4", "duration_sec": 12.0},
                        {"src": "cinema/b.mp4", "duration_sec": 12.0},
                    ],
                },
            }
        ]
        self.assertEqual(
            deck_doctor.cinema_coverage_errors(slides, [24.0], _probe({"a.mp4": 12.0, "b.mp4": 12.0})), []
        )

    def test_clip_shorter_than_declared_duration_is_capped(self) -> None:
        # Declared 12 s but the file is only 8 s at rate 1.0: coverage is 8 s, not 12 s.
        slides = [
            {
                "id": "u2",
                "type": "cinema_clip",
                "cinema": {"loop": False, "shots": [{"src": "cinema/c.mp4", "duration_sec": 12.0}]},
            }
        ]
        errs = deck_doctor.cinema_coverage_errors(slides, [12.0], _probe({"c.mp4": 8.0}))
        self.assertEqual(len(errs), 1)

    def test_playback_rate_stretches_coverage(self) -> None:
        # 12 s clip at rate 0.5 plays for 24 s, which covers a 24 s slide.
        slides = [
            {
                "id": "u3",
                "type": "cinema_clip",
                "cinema": {"loop": False, "shots": [{"src": "cinema/d.mp4", "playback_rate": 0.5}]},
            }
        ]
        self.assertEqual(deck_doctor.cinema_coverage_errors(slides, [24.0], _probe({"d.mp4": 12.0})), [])

    def test_single_src_clip_respects_playback_rate(self) -> None:
        # Real approved solar slide: 12.04 s clip at rate 0.9 plays for ~13.4 s.
        slides = [{"id": "c0", "type": "cinema_clip", "cinema": {"loop": False, "src": "cinema/s.mp4", "playback_rate": 0.9}}]
        self.assertEqual(deck_doctor.cinema_coverage_errors(slides, [13.0], _probe({"s.mp4": 12.04})), [])
        errs = deck_doctor.cinema_coverage_errors(slides, [14.5], _probe({"s.mp4": 12.04}))
        self.assertEqual(len(errs), 1)

    def test_doctor_reports_coverage_as_warning_not_error(self) -> None:
        # Doctor uses word-count estimates (2-5 s above real narration): it must warn, never reject a deck.
        deck = {
            "slug": "t", "lang": "en", "aspect": "16:9", "width": 1920, "height": 1080, "fps": 30,
            "slides": [{"id": "x", "type": "cinema_clip", "voice_text": "hi there",
                        "cinema": {"loop": False, "src": "cinema/none.mp4"}}],
        }
        report = deck_doctor.diagnose_deck(deck, check_assets=True)
        self.assertFalse(any("black tail" in e for e in report["errors"]), report["errors"])

    def test_non_cinema_slides_ignored(self) -> None:
        slides = [{"id": "s", "type": "title", "cinema": {"loop": False}}]
        self.assertEqual(deck_doctor.cinema_coverage_errors(slides, [30.0], _probe({})), [])

    def test_mismatched_lengths_are_not_guessed(self) -> None:
        slides = [{"id": "x", "type": "cinema_clip", "cinema": {"loop": False, "src": "cinema/z.mp4"}}]
        self.assertEqual(deck_doctor.cinema_coverage_errors(slides, [], _probe({"z.mp4": 1.0})), [])


class FractionalRateWarningTests(unittest.TestCase):
    def test_fractional_rates_warn_once_per_slide(self) -> None:
        slides = [
            {"id": "a", "type": "cinema_clip", "cinema": {"playback_rate": 0.94}},
            {"id": "b", "type": "cinema_clip", "cinema": {"shots": [{"src": "x", "playback_rate": 0.95}, {"playback_rate": 0.9}]}},
            {"id": "c", "type": "cinema_clip", "cinema": {"playback_rate": 1.0, "shots": [{"playback_rate": 1.0}]}},
            {"id": "d", "type": "title", "cinema": {"playback_rate": 0.5}},
        ]
        warns = deck_doctor.fractional_rate_warnings(slides)
        self.assertEqual(len(warns), 2)
        self.assertIn("slide a", warns[0])
        self.assertIn("slide b", warns[1])

    def test_unit_rate_is_silent(self) -> None:
        self.assertEqual(deck_doctor.fractional_rate_warnings([{"id": "c", "type": "cinema_clip", "cinema": {"playback_rate": 1}}]), [])


if __name__ == "__main__":
    unittest.main()
