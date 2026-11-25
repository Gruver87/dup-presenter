"""Fail-closed tests for deck_doctor (pre-render diagnostics, no rendering)."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import deck_doctor  # noqa: E402

EN_DECK = ROOT / "decks" / "radar-cosmic-v4-en.json"


def _base_en_deck() -> dict:
    return json.loads(EN_DECK.read_text(encoding="utf-8"))


class DeckDoctorTests(unittest.TestCase):
    def setUp(self) -> None:
        # Redirect out/ to an empty temp dir so overwrite checks never depend on real renders.
        self._tmp = tempfile.TemporaryDirectory()
        self.out_dir = Path(self._tmp.name)
        patcher = mock.patch.object(deck_doctor, "OUT_DIR", self.out_dir)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)

    def test_valid_en_deck_is_ok(self) -> None:
        report = deck_doctor.diagnose_deck(_base_en_deck())
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(report["errors"], [])
        self.assertGreater(report["estimates"]["estimated_length_sec"], 0)
        self.assertGreater(report["estimates"]["frames"], 0)

    def test_cyrillic_in_en_deck_is_error(self) -> None:
        deck = _base_en_deck()
        deck["slides"][1]["title"] = "Привет мир"
        report = deck_doctor.diagnose_deck(deck)
        self.assertFalse(report["ok"])
        self.assertTrue(any("Cyrillic" in e for e in report["errors"]), report["errors"])

    def test_missing_screenshot_is_error(self) -> None:
        deck = _base_en_deck()
        slide = next(s for s in deck["slides"] if s.get("screens"))
        slide["screens"][0]["src"] = "screens/__does_not_exist__.png"
        report = deck_doctor.diagnose_deck(deck)
        self.assertFalse(report["ok"])
        # validate_deck() catches missing screen files first (schema stage); either message blocks the render.
        self.assertTrue(
            any("missing screen file" in e or "screenshot not found" in e for e in report["errors"]),
            report["errors"],
        )

    def test_existing_mp4_refused_without_overwrite(self) -> None:
        slug = _base_en_deck()["slug"]
        (self.out_dir / f"{slug}.mp4").write_bytes(b"x")

        refused = deck_doctor.diagnose_deck(_base_en_deck(), overwrite=False)
        self.assertFalse(refused["ok"])
        self.assertTrue(any("refusing to overwrite" in e for e in refused["errors"]), refused["errors"])

        allowed = deck_doctor.diagnose_deck(_base_en_deck(), overwrite=True)
        self.assertTrue(allowed["ok"], allowed["errors"])
        self.assertTrue(any("overwritten" in w for w in allowed["warnings"]), allowed["warnings"])

    def test_schema_violation_is_reported_not_raised(self) -> None:
        deck = _base_en_deck()
        deck["theme"] = "no_such_theme"
        report = deck_doctor.diagnose_deck(copy.deepcopy(deck))
        self.assertFalse(report["ok"])
        self.assertTrue(report["errors"])

    def test_non_dict_deck_raises(self) -> None:
        with self.assertRaises(deck_doctor.DeckDoctorError):
            deck_doctor.diagnose_deck([])  # type: ignore[arg-type]

    def test_load_and_diagnose_accepts_str_and_reports_missing_file(self) -> None:
        ok = deck_doctor.load_and_diagnose(str(EN_DECK))
        self.assertTrue(ok["ok"], ok["errors"])

        missing = deck_doctor.load_and_diagnose(str(ROOT / "decks" / "__missing__.json"))
        self.assertFalse(missing["ok"])
        self.assertTrue(any("cannot read deck" in e for e in missing["errors"]))


if __name__ == "__main__":
    unittest.main()
