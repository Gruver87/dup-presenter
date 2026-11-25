"""Unit & fail-closed tests for Phase C (Director Presets + Thumbnail Studio) and Phase D (Video Pack)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from build_deck import validate_deck  # noqa: E402
from director_presets import DIRECTOR_PRESETS, DirectorPresetError, apply_director_preset  # noqa: E402
from idea_engine import generate_ideas, idea_to_deck  # noqa: E402
from thumbnail_studio import ThumbnailError, build_thumbnail_props, render_thumbnail  # noqa: E402
from video_pack import VideoPackError, plan_video_pack  # noqa: E402


class DirectorThumbPackTests(unittest.TestCase):
    def _sample_deck(self) -> dict:
        idea = generate_ideas("DUP Studio", lang="en", genre="tech_explainer", count=1, mode="template")["ideas"][0]
        return idea_to_deck(idea, slug="dup-studio-test")

    def test_all_director_presets_produce_valid_decks(self) -> None:
        base = self._sample_deck()
        for preset_id in DIRECTOR_PRESETS:
            applied = apply_director_preset(base, preset_id)
            validate_deck(applied)
            self.assertEqual(applied["director_preset"], preset_id)
            if preset_id == "fast_shorts":
                self.assertEqual(applied["aspect"], "9:16")
                self.assertEqual(applied["caption_style"], "bold")

    def test_unknown_director_preset_fails_closed(self) -> None:
        with self.assertRaises(DirectorPresetError):
            apply_director_preset(self._sample_deck(), "nonexistent_preset")

    def test_thumbnail_props_and_dry_run_command(self) -> None:
        deck = self._sample_deck()
        props = build_thumbnail_props(deck=deck, accent_badge="0 FLOAT")
        self.assertEqual(props["theme"], deck["theme"])
        self.assertEqual(props["accentBadge"], "0 FLOAT")
        with tempfile.TemporaryDirectory() as tmp:
            out_png = Path(tmp) / "thumb.png"
            res = render_thumbnail(out_png, props, dry_run=True)
            self.assertTrue(res["ok"])
            self.assertIn("DupThumbnail", res["cmd"])

    def test_thumbnail_refuses_empty_title_or_path_traversal(self) -> None:
        with self.assertRaises(ThumbnailError):
            build_thumbnail_props(title="")
        with self.assertRaises(ThumbnailError):
            build_thumbnail_props(title="Ok", preview_image="../../secret.png")
        with self.assertRaises(ThumbnailError):
            build_thumbnail_props(title="Ok", theme="bad_theme")

    def test_video_pack_plan_builds_multi_format_targets_and_fails_on_same_lang(self) -> None:
        deck = self._sample_deck()
        with tempfile.TemporaryDirectory() as tmp:
            dp = Path(tmp) / "sample.json"
            dp.write_text(json.dumps(deck), encoding="utf-8")
            plan = plan_video_pack(dp, include_short=True, include_thumbnail=True, translate_to="ru", preset="cinema_cosmos")
            self.assertTrue(plan["ok"])
            roles = [t["role"] for t in plan["targets"]]
            self.assertEqual(roles, ["primary", "short_9x16", "translated_ru"])
            self.assertIsNotNone(plan["thumbnail"])
            self.assertIn("preflight", plan)
            self.assertGreaterEqual(plan["preflight"]["director_score"], 0)
            self.assertEqual(plan["targets"][1]["preset"], "fast_shorts")

            with self.assertRaises(VideoPackError):
                plan_video_pack(dp, translate_to="en")


if __name__ == "__main__":
    unittest.main()
