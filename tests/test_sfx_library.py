"""Offline tests for the Stage 5 named SFX library (deterministic synthesis, fail-closed cue validation)."""

from __future__ import annotations

import copy
import hashlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import sfx_library as sfx  # noqa: E402
import build_deck  # noqa: E402
from build_deck import DeckValidationError, validate_deck  # noqa: E402


def _deck(cues: list) -> dict:
    slide = {
        "id": "s1",
        "tag": "01",
        "type": "quote",
        "title": "Launch",
        "voice_text": "A short line for the test.",
        "sfx": cues,
    }
    return {
        "slug": "sfx-test",
        "lang": "en",
        "theme": "quantum_ledger",
        "aspect": "16:9",
        "brand": "DUP LABS",
        "background": {"enabled": False},
        "voice": {"engine": "kokoro_v1", "lang": "en", "speaker": "am_michael"},
        "slides": [slide],
    }


class SfxLibraryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="sfxlib_"))
        self.public = self.tmp / "public"
        self.lib_dir = self.public / "sfx" / "library"
        self.manifest = self.lib_dir / "manifest.json"
        patches = [
            mock.patch.object(sfx, "LIBRARY_DIR", self.lib_dir),
            mock.patch.object(sfx, "MANIFEST_PATH", self.manifest),
            # validate_deck resolves cue files under PUBLIC_DIR: keep it in the same temp tree.
            mock.patch.object(build_deck, "PUBLIC_DIR", self.public),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    # synthesis / manifest -------------------------------------------------

    def test_library_has_the_documented_six_effects(self) -> None:
        self.assertEqual(sfx.LIBRARY_NAMES, frozenset({"whoosh", "pop", "impact", "tick", "riser", "ding"}))

    def test_ensure_library_writes_files_and_manifest_hashes(self) -> None:
        manifest = sfx.ensure_library()
        self.assertEqual(manifest["schema"], sfx.MANIFEST_SCHEMA)
        self.assertEqual(len(manifest["items"]), 6)
        for item in manifest["items"]:
            path = self.lib_dir / f"{item['name']}.wav"
            self.assertTrue(path.is_file(), item["name"])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), item["sha256"])
            self.assertGreater(item["duration_sec"], 0.0)
            self.assertLessEqual(item["duration_sec"], 2.0)

    def test_synthesis_is_deterministic(self) -> None:
        sfx.ensure_library()
        first = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(self.lib_dir.glob("*.wav"))}
        second_dir = Path(tempfile.mkdtemp(prefix="sfxlib2_"))
        self.addCleanup(shutil.rmtree, second_dir, True)
        with mock.patch.object(sfx, "LIBRARY_DIR", second_dir), mock.patch.object(sfx, "MANIFEST_PATH", second_dir / "m.json"):
            sfx.ensure_library()
            second = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(second_dir.glob("*.wav"))}
        self.assertEqual(first, second)

    # name resolution ------------------------------------------------------

    def test_unknown_name_is_refused(self) -> None:
        with self.assertRaises(sfx.SfxLibraryError):
            sfx.library_src("explosion")
        with self.assertRaises(sfx.SfxLibraryError):
            sfx.library_src("../../etc/passwd")

    def test_resolve_maps_names_to_src_and_keeps_src_cues(self) -> None:
        deck = _deck([
            {"name": "impact", "at_sec": 0.2, "volume": 0.5},
            {"src": "sfx/ui_pop.wav", "at_sec": 1.0},
        ])
        sfx.resolve_deck_sfx(deck)
        cues = deck["slides"][0]["sfx"]
        self.assertEqual(cues[0]["src"], "sfx/library/impact.wav")
        self.assertNotIn("name", cues[0])
        self.assertEqual(cues[1]["src"], "sfx/ui_pop.wav")
        self.assertTrue((self.lib_dir / "impact.wav").is_file())

    # validation (fail-closed) ---------------------------------------------

    def test_valid_library_cue_passes_validation_without_prebuilt_file(self) -> None:
        deck = sfx.resolve_deck_sfx(_deck([{"name": "tick", "at_sec": 0.5}]))
        validate_deck(deck, check_assets=True)

    def test_cue_with_both_src_and_name_is_refused(self) -> None:
        deck = _deck([{"name": "tick", "src": "sfx/ui_pop.wav", "at_sec": 0.5}])
        with self.assertRaises(DeckValidationError):
            validate_deck(copy.deepcopy(deck), check_assets=False)

    def test_cue_with_neither_src_nor_name_is_refused(self) -> None:
        with self.assertRaises(DeckValidationError):
            validate_deck(_deck([{"at_sec": 0.5}]), check_assets=False)

    def test_unknown_library_name_is_refused_by_validation(self) -> None:
        with self.assertRaises(DeckValidationError) as ctx:
            validate_deck(_deck([{"name": "boom", "at_sec": 0.5}]), check_assets=False)
        self.assertIn("not in the SFX library", str(ctx.exception))

    def test_missing_src_file_still_refused_when_checking_assets(self) -> None:
        with self.assertRaises(DeckValidationError):
            validate_deck(_deck([{"src": "sfx/does_not_exist.wav", "at_sec": 0.5}]), check_assets=True)

    def test_every_library_name_validates(self) -> None:
        for name in sorted(sfx.LIBRARY_NAMES):
            validate_deck(_deck([{"name": name, "at_sec": 0.1}]), check_assets=False)


if __name__ == "__main__":
    unittest.main()
