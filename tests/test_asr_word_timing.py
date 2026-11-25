"""Word timing source selection: engine events > local ASR (English only) > labelled estimate. No model load here."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import audio_fx  # noqa: E402
import build_deck  # noqa: E402
from audio_fx import WordTimingUnavailable  # noqa: E402

CLIP = np.zeros(4800, dtype=np.float32)
ENGINE = [{"start_sec": 0.0, "end_sec": 0.2, "text": "Edge"}]
ASR = [{"start_sec": 0.1, "end_sec": 0.3, "text": "asr"}]


class WordEventSourceTests(unittest.TestCase):
    def test_engine_events_win_and_skip_asr(self) -> None:
        with mock.patch.object(build_deck, "transcribe_word_events", side_effect=AssertionError("ASR must not run")):
            self.assertEqual(build_deck._word_events_for_clip(CLIP, "en", "s1", ENGINE), ENGINE)

    def test_russian_without_engine_events_uses_estimate_without_asr(self) -> None:
        with mock.patch.object(build_deck, "transcribe_word_events", side_effect=AssertionError("ASR is en-only")):
            self.assertEqual(build_deck._word_events_for_clip(CLIP, "ru", "s1", []), [])

    def test_english_uses_asr_when_no_engine_events(self) -> None:
        with mock.patch.object(build_deck, "transcribe_word_events", return_value=ASR) as asr:
            self.assertEqual(build_deck._word_events_for_clip(CLIP, "en", "s1", []), ASR)
            asr.assert_called_once()

    def test_english_asr_unavailable_is_reported_and_estimated(self) -> None:
        with mock.patch.object(build_deck, "transcribe_word_events", side_effect=WordTimingUnavailable("no pkg")):
            self.assertEqual(build_deck._word_events_for_clip(CLIP, "en", "s1", []), [])


class AsrPackageTests(unittest.TestCase):
    def test_missing_package_raises_typed_error(self) -> None:
        # A None entry in sys.modules makes `import faster_whisper` raise ImportError.
        with mock.patch.dict(sys.modules, {"faster_whisper": None}):
            with self.assertRaises(WordTimingUnavailable):
                audio_fx.transcribe_word_events(CLIP, 48000)


if __name__ == "__main__":
    unittest.main()
