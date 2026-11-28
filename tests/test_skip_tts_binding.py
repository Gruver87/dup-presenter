"""--skip-tts must only reuse a shared deck_resolved.json synthesized from this exact deck.

Regression: the RU and EN masters were rendered with --skip-tts from a timeline of the other deck
(Russian narration under the English slug). The guard below must refuse that case.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_deck as bd  # noqa: E402


class SkipTtsSourceTests(unittest.TestCase):
    def test_refused_when_timeline_has_no_source_record(self) -> None:
        err = bd.skip_tts_source_error({"slug": "x", "slides": []}, "a" * 64)
        self.assertIsNotNone(err)
        self.assertIn("source_deck_sha256", err)

    def test_refused_when_timeline_came_from_other_deck(self) -> None:
        err = bd.skip_tts_source_error({"source_deck_sha256": "b" * 64}, "a" * 64)
        self.assertIsNotNone(err)
        self.assertIn("different deck", err)

    def test_allowed_when_fingerprint_matches(self) -> None:
        self.assertIsNone(bd.skip_tts_source_error({"source_deck_sha256": "a" * 64}, "a" * 64))

    def test_empty_recorded_fingerprint_is_refused(self) -> None:
        self.assertIsNotNone(bd.skip_tts_source_error({"source_deck_sha256": ""}, "a" * 64))


class BindResolvedTests(unittest.TestCase):
    def test_full_deck_timeline_records_fingerprint(self) -> None:
        resolved: dict = {"slides": []}
        bd.bind_resolved_to_deck(resolved, "a" * 64, only_slide="")
        self.assertEqual(resolved["source_deck_sha256"], "a" * 64)
        self.assertIsNone(bd.skip_tts_source_error(resolved, "a" * 64))

    def test_only_slide_timeline_clears_fingerprint(self) -> None:
        resolved = {"slides": [], "source_deck_sha256": "a" * 64}
        bd.bind_resolved_to_deck(resolved, "a" * 64, only_slide="s5")
        self.assertNotIn("source_deck_sha256", resolved)
        self.assertIsNotNone(bd.skip_tts_source_error(resolved, "a" * 64))

    def test_whitespace_only_slide_counts_as_full_deck(self) -> None:
        resolved: dict = {}
        bd.bind_resolved_to_deck(resolved, "a" * 64, only_slide="   ")
        self.assertEqual(resolved["source_deck_sha256"], "a" * 64)


if __name__ == "__main__":
    unittest.main()
