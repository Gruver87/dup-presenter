"""Fail-closed validation tests for the radar_heart_3d Three.js slide type."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_deck as bd  # noqa: E402


def _deck(slide: dict) -> dict:
    return {
        "slug": "radar-heart-3d-test",
        "lang": "ru",
        "theme": "cosmic_radar",
        "voice": {"lang": "ru", "speaker": "eugene", "rate": "90%"},
        "slides": [slide],
    }


class RadarHeart3DValidationTests(unittest.TestCase):
    def test_all_ten_scenes_validate(self) -> None:
        scenes = (
            "core_birth",
            "emblem_ingest",
            "emblem_mtf_score",
            "emblem_runners",
            "emblem_stop_cut",
            "emblem_traps",
            "emblem_integer",
            "emblem_recovery",
            "constellation_radar",
            "presenter_core",
        )
        for scene in scenes:
            with self.subTest(scene=scene):
                bd.validate_deck(
                    _deck(
                        {
                            "id": f"s_{scene}",
                            "type": "radar_heart_3d",
                            "title": "Heart 3D",
                            "voice_text": "Тестовая озвучка 3D сцены.",
                            "heart3d": {"scene": scene, "chips": ["A", "B"]},
                        }
                    ),
                    check_assets=False,
                )

    def test_missing_heart3d_refused(self) -> None:
        with self.assertRaises(bd.DeckValidationError):
            bd.validate_deck(
                _deck({"id": "s1", "type": "radar_heart_3d", "title": "X", "voice_text": "Текст"}),
                check_assets=False,
            )

    def test_unknown_scene_refused(self) -> None:
        with self.assertRaises(bd.DeckValidationError):
            bd.validate_deck(
                _deck(
                    {
                        "id": "s1",
                        "type": "radar_heart_3d",
                        "title": "X",
                        "voice_text": "Текст",
                        "heart3d": {"scene": "dinosaurs"},
                    }
                ),
                check_assets=False,
            )

    def test_too_many_chips_refused(self) -> None:
        with self.assertRaises(bd.DeckValidationError):
            bd.validate_deck(
                _deck(
                    {
                        "id": "s1",
                        "type": "radar_heart_3d",
                        "title": "X",
                        "voice_text": "Текст",
                        "heart3d": {"scene": "core_birth", "chips": ["1", "2", "3", "4", "5"]},
                    }
                ),
                check_assets=False,
            )

    def test_bg_video_traversal_refused(self) -> None:
        for bad in ("../secret.mp4", "/etc/passwd", "\\windows\\x.mp4", ""):
            with self.assertRaises(bd.DeckValidationError):
                bd.validate_deck(
                    _deck(
                        {
                            "id": "s1",
                            "type": "radar_heart_3d",
                            "title": "X",
                            "voice_text": "Текст",
                            "heart3d": {"scene": "core_birth", "bg_video": bad},
                        }
                    ),
                    check_assets=False,
                )

    def test_bg_video_missing_asset_refused(self) -> None:
        with self.assertRaises(bd.DeckValidationError):
            bd.validate_deck(
                _deck(
                    {
                        "id": "s1",
                        "type": "radar_heart_3d",
                        "title": "X",
                        "voice_text": "Текст",
                        "heart3d": {"scene": "core_birth", "bg_video": "cinema/world3026/does_not_exist.mp4"},
                    }
                ),
                check_assets=True,
            )

    def test_bg_opacity_bounds_and_bool_refused(self) -> None:
        for bad in (0.05, 1.5, True, "0.5"):
            with self.assertRaises(bd.DeckValidationError):
                bd.validate_deck(
                    _deck(
                        {
                            "id": "s1",
                            "type": "radar_heart_3d",
                            "title": "X",
                            "voice_text": "Текст",
                            "heart3d": {"scene": "core_birth", "bg_opacity": bad},
                        }
                    ),
                    check_assets=False,
                )

    # public/cinema/ is git-ignored (large AI-generated clips, regenerated per machine). Without them this
    # check cannot run, so it is skipped with an explicit reason instead of failing on a clean checkout.
    @unittest.skipUnless(
        (Path(__file__).resolve().parents[1] / "public" / "cinema" / "world3026").is_dir(),
        "public/cinema/world3026 clips are not in the repo (git-ignored); run on a machine with the generated clips",
    )
    def test_year_3026_deck_passes_with_assets(self) -> None:
        deck_path = Path(__file__).resolve().parents[1] / "decks" / "dup-market-radar-3026.json"
        raw = json.loads(deck_path.read_text(encoding="utf-8"))
        bd.validate_deck(raw, check_assets=True)
        self.assertEqual(len(raw["slides"]), 10)
        for sl in raw["slides"]:
            self.assertEqual(sl["type"], "radar_heart_3d")
            self.assertTrue(sl["heart3d"]["bg_video"].startswith("cinema/world3026/"))


if __name__ == "__main__":
    unittest.main()
