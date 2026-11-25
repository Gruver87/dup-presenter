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
    """EN deck with music disabled: its track is gitignored (copyright), so CI has no copy."""
    deck = json.loads(EN_DECK.read_text(encoding="utf-8"))
    deck["music"] = {**(deck.get("music") or {}), "enabled": False}
    return deck


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

    def test_missing_music_file_is_error(self) -> None:
        deck = _base_en_deck()
        deck["music"] = {"enabled": True, "file": "__no_such_track__.mp3", "volume": 0.1}
        report = deck_doctor.diagnose_deck(deck)
        self.assertFalse(report["ok"])
        self.assertTrue(any("music file not found" in e for e in report["errors"]), report["errors"])

    def test_load_and_diagnose_accepts_str_and_reports_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            deck_file = Path(tmp) / "deck.json"
            deck_file.write_text(json.dumps(_base_en_deck(), ensure_ascii=False), encoding="utf-8")
            ok = deck_doctor.load_and_diagnose(str(deck_file))
        self.assertTrue(ok["ok"], ok["errors"])

        missing = deck_doctor.load_and_diagnose(str(ROOT / "decks" / "__missing__.json"))
        self.assertFalse(missing["ok"])
        self.assertTrue(any("cannot read deck" in e for e in missing["errors"]))


class DoctorWithoutAssetsTests(unittest.TestCase):
    """CI has no local assets. These run the doctor's non-asset checks on every committed deck."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._patch = mock.patch.object(deck_doctor, "OUT_DIR", Path(self._tmp.name))
        self._patch.start()

    def tearDown(self) -> None:
        self._patch.stop()
        self._tmp.cleanup()

    def test_every_committed_deck_passes_without_assets(self) -> None:
        decks = sorted((ROOT / "decks").glob("*.json"))
        self.assertGreater(len(decks), 0)
        failures: dict[str, list[str]] = {}
        for dp in decks:
            data = json.loads(dp.read_text(encoding="utf-8"))
            report = deck_doctor.diagnose_deck(data, overwrite=True, check_assets=False)
            if not report["ok"]:
                failures[dp.name] = report["errors"]
        self.assertEqual(failures, {}, "deck_doctor (no assets) must pass on every committed deck")

    def test_no_assets_mode_still_catches_cyrillic_in_english_deck(self) -> None:
        deck = _base_en_deck()
        deck["slides"][0]["title"] = "Радар крипторынка"
        report = deck_doctor.diagnose_deck(deck, overwrite=True, check_assets=False)
        self.assertFalse(report["ok"])
        self.assertTrue(any("Cyrillic" in e for e in report["errors"]))

    def test_no_assets_mode_still_catches_unknown_theme(self) -> None:
        deck = _base_en_deck()
        deck["theme"] = "not_a_theme"
        report = deck_doctor.diagnose_deck(deck, overwrite=True, check_assets=False)
        self.assertFalse(report["ok"])

    def test_no_assets_mode_says_assets_were_not_checked(self) -> None:
        report = deck_doctor.diagnose_deck(_base_en_deck(), overwrite=True, check_assets=False)
        self.assertTrue(any("assets not checked" in w for w in report["warnings"]))

    def test_assets_mode_still_refuses_missing_screenshot(self) -> None:
        deck = _base_en_deck()
        for s in deck["slides"]:
            for sc in s.get("screens") or []:
                sc["src"] = "screens/__missing__.png"
        report = deck_doctor.diagnose_deck(deck, overwrite=True, check_assets=True)
        self.assertFalse(report["ok"])


if __name__ == "__main__":
    unittest.main()
