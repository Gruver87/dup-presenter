"""Item 5: automatic pacing. Pure math plus the bounded correction loop, with a fake synthesizer."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_deck  # noqa: E402
import pacing  # noqa: E402

BASE_WPM_AT_100 = 200.0  # fake engine: 200 wpm at rate 100%


class FakeSynth:
    """Duration scales with rate: wpm = BASE_WPM_AT_100 * rate / 100. Audio is silence of that length."""

    def __init__(self, rate: str) -> None:
        self.rate = rate
        self.calls = 0

    def synth_with_timings(self, speaker, plain, ssml=None):
        self.calls += 1
        rate = pacing.rate_pct(self.rate)
        words = len(plain.split())
        dur = words * 60.0 / (BASE_WPM_AT_100 * rate / 100.0)
        return np.zeros(int(dur * build_deck.SR), dtype=np.float32), []


PLAIN = " ".join(["word"] * 30)  # 30 words


class ParseTests(unittest.TestCase):
    def test_absent_means_off(self) -> None:
        self.assertIsNone(pacing.parse_pacing(None))

    def test_valid_spec_with_defaults(self) -> None:
        spec = pacing.parse_pacing({"target_wpm": 150})
        self.assertEqual((spec.target_wpm, spec.tolerance, spec.min_rate_pct, spec.max_rate_pct), (150, 0.04, 70, 110))

    def test_rejects_out_of_range_and_bad_types(self) -> None:
        for bad in ({}, {"target_wpm": "fast"}, {"target_wpm": 10}, {"target_wpm": 150, "tolerance": 0.9},
                    {"target_wpm": 150, "min_rate_pct": 120, "max_rate_pct": 110}, "150"):
            with self.subTest(bad=bad), self.assertRaises(pacing.PacingError):
                pacing.parse_pacing(bad)

    def test_rate_string_must_be_percent(self) -> None:
        self.assertEqual(pacing.rate_pct("86%"), 86.0)
        with self.assertRaises(pacing.PacingError):
            pacing.rate_pct("0.86")


class MathTests(unittest.TestCase):
    def test_wpm_and_zero_duration_guard(self) -> None:
        self.assertAlmostEqual(pacing.words_per_minute("a b c d", 2.0), 120.0)
        with self.assertRaises(pacing.PacingError):
            pacing.words_per_minute("a", 0.0)

    def test_next_rate_within_tolerance_is_none(self) -> None:
        spec = pacing.parse_pacing({"target_wpm": 150})
        self.assertIsNone(pacing.next_rate(86, 152.0, spec))

    def test_next_rate_scales_proportionally_and_clamps(self) -> None:
        spec = pacing.parse_pacing({"target_wpm": 150})
        self.assertEqual(pacing.next_rate(86, 172.0, spec), 75.0)  # 86 * 150/172 = 75.0
        self.assertEqual(pacing.next_rate(86, 60.0, spec), 110.0)  # clamped to max bound


class PacedSynthTests(unittest.TestCase):
    def test_converges_to_target_in_one_pass(self) -> None:
        spec = pacing.parse_pacing({"target_wpm": 150})
        synth = FakeSynth("86%")
        audio, _, rate_used, wpm = build_deck._paced_synth(synth, "x", PLAIN, {"id": "s"}, spec, "86%", "s")
        self.assertEqual(rate_used, "75%")
        self.assertAlmostEqual(wpm, 150.0, delta=1.0)
        self.assertEqual(synth.rate, "86%", "synther rate must be restored for the next slide")

    def test_out_of_reach_target_stops_at_bound(self) -> None:
        spec = pacing.parse_pacing({"target_wpm": 260})
        synth = FakeSynth("86%")
        _, _, rate_used, wpm = build_deck._paced_synth(synth, "x", PLAIN, {"id": "s"}, spec, "86%", "s")
        self.assertEqual(rate_used, "110%")
        self.assertAlmostEqual(wpm, 220.0, delta=1.0)
        self.assertLessEqual(synth.calls, 1 + build_deck.MAX_PASSES, "bounded passes only")

    def test_no_spec_keeps_base_rate_and_reports_nothing(self) -> None:
        synth = FakeSynth("86%")
        _, _, rate_used, wpm = build_deck._paced_synth(synth, "x", PLAIN, {"id": "s"}, None, "86%", "s")
        self.assertEqual((rate_used, wpm, synth.calls), ("86%", None, 1))

    def test_voice_ssml_is_never_overridden(self) -> None:
        spec = pacing.parse_pacing({"target_wpm": 150})
        synth = FakeSynth("86%")
        _, _, rate_used, wpm = build_deck._paced_synth(
            synth, "x", PLAIN, {"id": "s", "voice_ssml": "<speak>x</speak>"}, spec, "86%", "s"
        )
        self.assertEqual((rate_used, wpm, synth.calls), ("86%", None, 1))


if __name__ == "__main__":
    unittest.main()
