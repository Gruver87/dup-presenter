"""Planner `quote` slides: a quotation must be copied verbatim from FACTS and carry no claims (fail-closed)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import plan_deck  # noqa: E402

README_TEXT = (
    "Heuristic scores are not guarantees of profit.\n"
    "Manual orders run only on KuCoin spot."
)


class QuoteFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.facts = {
            "root": self._tmp.name,
            "project": {"name": "demo"},
            "docs": [{"id": "D1", "path": "README.md", "lines": 2, "text": README_TEXT}],
            "code": [],
            "images": [],
            "urls": [],
        }

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _errors(self, slide: dict) -> list[str]:
        return plan_deck.validate_quote_slide(slide, self.facts, "s2")


class QuoteSlideTests(QuoteFixture):
    def test_verbatim_sentence_is_accepted(self) -> None:
        self.assertEqual(self._errors({"title": "Manual orders run only on KuCoin spot.", "subtitle": "README.md"}), [])

    def test_match_ignores_case_and_line_breaks(self) -> None:
        self.assertEqual(self._errors({"title": "manual orders run\nonly on KuCoin SPOT."}), [])

    def test_paraphrase_is_refused(self) -> None:
        errs = self._errors({"title": "Manual orders are only possible on KuCoin spot."})
        self.assertTrue(any("not verbatim" in e for e in errs))

    def test_heading_fragment_is_refused(self) -> None:
        # A heading phrase that occurs verbatim in FACTS is still not a sentence.
        self.facts["docs"][0]["text"] += "\nManual orders run only on KuCoin spot"
        errs = self._errors({"title": "Manual orders run only on KuCoin spot"})
        self.assertTrue(any("full sentence" in e for e in errs), errs)

    def test_too_short_sentence_is_refused(self) -> None:
        self.facts["docs"][0]["text"] += "\nSpot only."
        errs = self._errors({"title": "Spot only."})
        self.assertTrue(any("full sentence" in e for e in errs), errs)

    def test_claim_is_refused_even_if_quoted(self) -> None:
        self.assertFalse(self._errors({"title": "Mainnet is production ready."}) == [])

    def test_empty_quote_is_refused(self) -> None:
        self.assertFalse(self._errors({"title": "   "}) == [])

    def test_overlong_quote_is_refused(self) -> None:
        self.assertFalse(self._errors({"title": "x" * 221}) == [])

    def test_non_string_attribution_is_refused(self) -> None:
        self.assertFalse(self._errors({"title": "Manual orders run only on KuCoin spot.", "subtitle": ["README"]}) == [])

    def test_quote_type_is_in_planner_vocabulary(self) -> None:
        self.assertIn("quote", plan_deck.SLIDE_TYPES)

    def test_plan_with_valid_quote_has_no_quote_errors(self) -> None:
        plan = {
            "brand": "DUP LABS",
            "slides": [
                {"type": "hero_3d", "tag": "A", "title": "Demo", "subtitle": "x", "voice_text": "Demo.", "bullets": []},
                {
                    "type": "quote",
                    "tag": "Q",
                    "title": "Manual orders run only on KuCoin spot.",
                    "subtitle": "README.md",
                    "voice_text": "Manual orders run only on KuCoin spot.",
                    "bullets": [],
                },
                {"type": "outro_3d", "tag": "O", "title": "End", "subtitle": "x", "voice_text": "End.", "bullets": []},
            ],
        }
        errors = plan_deck.validate_plan(plan, self.facts, lang="en")
        self.assertFalse([e for e in errors if "quote" in e.lower()], errors)


if __name__ == "__main__":
    unittest.main()
