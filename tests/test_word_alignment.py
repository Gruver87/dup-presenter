"""Word-level caption timing from TTS word events (Edge WordBoundary): alignment rules and fail-closed fallback."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from audio_fx import WORD_ALIGN_MIN_RATIO, align_word_events, build_word_captions  # noqa: E402


def _ev(text: str, start: float, end: float) -> dict:
    return {"start_sec": start, "end_sec": end, "text": text}


class AlignWordEventsTests(unittest.TestCase):
    def test_exact_tokens_take_event_times(self) -> None:
        tokens = ["Each", "word", "lights"]
        events = [_ev("Each", 0.1, 0.4), _ev("word", 0.5, 0.7), _ev("lights", 0.8, 1.2)]
        spans, ratio = align_word_events(tokens, events)
        self.assertEqual(ratio, 1.0)
        self.assertEqual(spans, [(0.1, 0.4), (0.5, 0.7), (0.8, 1.2)])

    def test_punctuation_attached_to_token_still_matches(self) -> None:
        # Edge drops punctuation: 'spoken.' is voiced as 'spoken'.
        spans, ratio = align_word_events(["spoken.", "now"], [_ev("spoken", 0.0, 0.5), _ev("now", 0.6, 0.9)])
        self.assertEqual(ratio, 1.0)
        self.assertEqual(spans[0], (0.0, 0.5))

    def test_case_is_ignored(self) -> None:
        spans, ratio = align_word_events(["KuCoin"], [_ev("kucoin", 1.0, 1.5)])
        self.assertEqual(ratio, 1.0)
        self.assertEqual(spans, [(1.0, 1.5)])

    def test_split_token_is_interpolated_and_lowers_ratio(self) -> None:
        # 'BTC/ETH' is voiced as three events; it cannot be matched, so it is interpolated between neighbours.
        tokens = ["price", "BTC/ETH", "rises"]
        events = [_ev("price", 0.0, 0.4), _ev("BTC", 0.5, 0.7), _ev("ETH", 0.8, 1.0), _ev("rises", 1.2, 1.6)]
        spans, ratio = align_word_events(tokens, events)
        self.assertAlmostEqual(ratio, 2 / 3, places=3)
        self.assertEqual(spans[0], (0.0, 0.4))
        self.assertEqual(spans[2], (1.2, 1.6))
        self.assertGreaterEqual(spans[1][0], 0.4)
        self.assertLessEqual(spans[1][1], 1.2)
        self.assertLessEqual(spans[1][0], spans[1][1])

    def test_pure_punctuation_token_does_not_count_against_ratio(self) -> None:
        tokens = ["one", "-", "two"]
        events = [_ev("one", 0.0, 0.3), _ev("two", 0.5, 0.8)]
        spans, ratio = align_word_events(tokens, events)
        self.assertEqual(ratio, 1.0)
        self.assertEqual(len(spans), 3)
        self.assertLessEqual(spans[1][1], spans[2][0] + 1e-9)

    def test_no_events_gives_zero_ratio(self) -> None:
        spans, ratio = align_word_events(["a", "b"], [])
        self.assertEqual(ratio, 0.0)
        self.assertEqual(len(spans), 2)

    def test_spans_are_monotonic(self) -> None:
        tokens = "one two three four five".split()
        events = [_ev(t, 0.3 * i, 0.3 * i + 0.25) for i, t in enumerate(tokens)]
        spans, _ = align_word_events(tokens, events)
        starts = [s for s, _ in spans]
        self.assertEqual(starts, sorted(starts))


class BuildWordCaptionsTests(unittest.TestCase):
    def test_aligned_words_carry_real_event_times_with_offset(self) -> None:
        plain = "Alpha beta. Gamma delta."
        events = [_ev("Alpha", 0.2, 0.5), _ev("beta", 0.6, 0.9), _ev("Gamma", 1.4, 1.8), _ev("delta", 1.9, 2.3)]
        cues = build_word_captions(plain, 3.0, boundaries=events, offset_sec=10.0)
        self.assertEqual(len(cues), 2)
        first, second = cues
        self.assertEqual(first["words"][0], {"w": "Alpha", "start": 10.2, "end": 10.5})
        self.assertEqual(second["words"][0]["start"], 11.4)
        self.assertEqual(first["start_sec"], 10.2)
        self.assertEqual(second["end_sec"], 12.3)

    def test_low_alignment_falls_back_but_keeps_words(self) -> None:
        plain = "Alpha beta gamma delta epsilon zeta eta theta."
        events = [_ev("qqq", 0.0, 0.2), _ev("www", 0.3, 0.5)]
        cues = build_word_captions(plain, 4.0, boundaries=events)
        self.assertTrue(cues[0]["words"])
        self.assertEqual([w["w"] for w in cues[0]["words"]], plain.split())
        self.assertLess(align_word_events(plain.split(), events)[1], WORD_ALIGN_MIN_RATIO)

    def test_spoken_text_aligns_respelled_brand_names(self) -> None:
        # Display keeps 'DUP Labs'; the RU voice said 'дап лабс'. Aligning to spoken text keeps timings real.
        plain = "DUP Labs shows words."
        spoken = "дап лабс shows words."
        events = [_ev("дап", 0.0, 0.4), _ev("лабс", 0.5, 0.9), _ev("shows", 1.0, 1.3), _ev("words", 1.4, 1.8)]
        cues = build_word_captions(plain, 2.5, boundaries=events, spoken=spoken)
        self.assertEqual(cues[0]["words"][1], {"w": "Labs", "start": 0.5, "end": 0.9})

    def test_spoken_with_different_token_count_is_ignored(self) -> None:
        plain = "one two three"
        events = [_ev("one", 0.0, 0.2), _ev("two", 0.3, 0.5), _ev("three", 0.6, 0.8)]
        cues = build_word_captions(plain, 1.0, boundaries=events, spoken="one two")
        self.assertEqual(cues[0]["words"][2]["start"], 0.6)


if __name__ == "__main__":
    unittest.main()
