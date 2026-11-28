"""AI edit of an existing deck without facts.json: fallback facts use the regular schema."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from unittest import mock  # noqa: E402

import plan_deck  # noqa: E402

DECK = {
    "brand": "DUP COSMOS",
    "subtitle": "От вспышки до Земли",
    "slides": [
        {"id": "s1", "type": "hero_3d", "title": "Большой взрыв", "voice_text": "Вспыхнул свет.",
         "bullets": [{"title": "Свет", "desc": "из точки"}]},
        {"id": "s2", "type": "outro_3d", "headline": "Каждый атом"},
    ],
}


class FactsFromDeckTests(unittest.TestCase):
    def test_schema_matches_scanned_facts(self) -> None:
        facts = plan_deck.facts_from_deck(DECK, "zz-test")
        self.assertEqual(facts["project"], {"name": "DUP COSMOS", "description": "От вспышки до Земли"})
        self.assertEqual(facts["code"], [])
        self.assertEqual(facts["images"], [])
        self.assertEqual([d["id"] for d in facts["docs"]], ["D1"])
        self.assertEqual(plan_deck.symbol_index(facts), {})

    def test_render_facts_contains_slide_text(self) -> None:
        text = plan_deck.render_facts(plan_deck.facts_from_deck(DECK, "zz-test"))
        self.assertIn("PROJECT: DUP COSMOS", text)
        self.assertIn("[D1] decks/zz-test.json", text)
        self.assertIn("Большой взрыв | Вспыхнул свет. | Свет: из точки", text)
        self.assertIn("Каждый атом", text)

    def test_cinema_slides_are_reported_as_unsupported(self) -> None:
        cinema = {"slides": [{"type": "cinema_clip"}, {"type": "hero_3d"}, {"type": None}]}
        self.assertEqual(plan_deck.unsupported_slide_types(cinema), ["None", "cinema_clip"])
        self.assertEqual(plan_deck.unsupported_slide_types(DECK), [])

    def test_short_deck_may_keep_two_slides(self) -> None:
        facts = plan_deck.facts_from_deck(DECK, "zz-test")
        two = {"slides": [{"type": "hero_3d"}, {"type": "outro_3d"}]}
        count_err = lambda errs: [e for e in errs if "slides must be" in e]  # noqa: E731
        self.assertEqual(count_err(plan_deck.validate_plan(two, facts, min_slides=2)), [])
        self.assertNotEqual(count_err(plan_deck.validate_plan(two, facts, min_slides=3)), [])

    def test_revision_keeps_voice_block_of_existing_deck(self) -> None:
        voice = {"engine": "kokoro_v1", "lang": "en", "speaker": "am_michael", "rate": 1.0}
        plan = {"slides": [{"type": "hero_3d", "title": "T", "subtitle": "s", "tag": "x",
                            "voice_text": "Hello.", "bullets": [], "source_ids": ["D1"]}]}
        with mock.patch.object(plan_deck, "list_ui_recordings", return_value=[]):
            deck = plan_deck.assemble_deck(plan, plan_deck.facts_from_deck(DECK, "zz-test"), "zz-test",
                                           lang="en", voice_base=voice)
        self.assertEqual(deck["voice"]["engine"], "kokoro_v1")
        self.assertEqual(deck["voice"]["speaker"], "am_michael")

    def test_empty_deck_uses_slug(self) -> None:
        facts = plan_deck.facts_from_deck({}, "zz-empty")
        self.assertEqual(facts["project"]["name"], "zz-empty")
        self.assertEqual(facts["docs"][0]["lines"], "1-1")


if __name__ == "__main__":
    unittest.main()
