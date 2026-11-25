"""Unit & fail-closed tests for the built-in Idea Engine (Phase A)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from build_deck import validate_deck  # noqa: E402
from idea_engine import (  # noqa: E402
    GENRE_CATALOG,
    IdeaDeckExistsError,
    IdeaEngineError,
    assess_topic_complexity,
    auto_fix_deck,
    critique_deck,
    generate_ideas,
    idea_to_deck,
    slugify_topic,
    write_idea_deck,
)
from mcp_server import handle_tool_call  # noqa: E402


class IdeaEngineTests(unittest.TestCase):
    def test_template_ideas_cover_all_genres_and_convert_to_valid_decks(self) -> None:
        for lang in ("ru", "en"):
            res = generate_ideas("DUP Protocol", lang=lang, genre="all", count=7, mode="template")
            self.assertTrue(res["ok"])
            self.assertEqual(res["source"], "template")
            self.assertEqual(len(res["ideas"]), 7)
            seen_genres = {item["genre"] for item in res["ideas"]}
            self.assertEqual(seen_genres, {g["id"] for g in GENRE_CATALOG})

            for idea in res["ideas"]:
                deck = idea_to_deck(idea)
                validate_deck(deck)
                self.assertEqual(deck["lang"], lang)
                self.assertGreaterEqual(len(deck["slides"]), 3)

    def test_genre_filter_prioritizes_requested_genre(self) -> None:
        res = generate_ideas("Python vs Rust", lang="en", genre="versus_battle", count=3, mode="template")
        self.assertEqual(res["ideas"][0]["genre"], "versus_battle")

    def test_write_idea_deck_refuses_overwrite_by_default(self) -> None:
        res = generate_ideas("L1 Storage", lang="ru", genre="short_60s", count=1, mode="template")
        idea = res["ideas"][0]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            deck, path = write_idea_deck(idea, tmp_dir, slug="l1-storage-short")
            self.assertTrue(path.is_file())
            self.assertEqual(deck["aspect"], "9:16")
            self.assertEqual(deck["caption_style"], "bold")

            with self.assertRaises(IdeaDeckExistsError):
                write_idea_deck(idea, tmp_dir, slug="l1-storage-short", overwrite=False)

            # Overwrite=True succeeds
            _, path2 = write_idea_deck(idea, tmp_dir, slug="l1-storage-short", overwrite=True)
            self.assertEqual(path, path2)

    def test_fail_closed_on_bad_input_and_unreachable_ollama(self) -> None:
        with self.assertRaises(IdeaEngineError):
            generate_ideas("a", mode="template")
        with self.assertRaises(IdeaEngineError):
            generate_ideas("Valid Topic", genre="nonexistent_genre", mode="template")
        with self.assertRaises(IdeaEngineError):
            generate_ideas("Valid Topic", count=99, mode="template")
        # Unreachable Ollama MUST fail closed, never silently return templates
        with self.assertRaises(IdeaEngineError):
            generate_ideas("Valid Topic", mode="ollama", host="http://127.0.0.1:1")

    def test_slugify_transliterates_cyrillic(self) -> None:
        self.assertEqual(slugify_topic("Как работает блокчейн!"), "kak-rabotaet-blokcheyn")

    def test_mcp_generate_ideas_tool(self) -> None:
        res = handle_tool_call("generate_ideas", {"topic": "Zero-Float Ledger", "lang": "en", "count": 3, "mode": "template"})
        self.assertTrue(res["ok"])
        self.assertEqual(len(res["ideas"]), 3)
        self.assertIn("assessment", res)
        self.assertIn("recommended_preset", res["assessment"])

    def test_assess_topic_complexity_auto_selects_tools_and_presets(self) -> None:
        deep = assess_topic_complexity("Архитектура L1 блокчейна Rust consensus libp2p", lang="ru")
        self.assertEqual(deep["complexity"], "deep")
        self.assertEqual(deep["recommended_preset"], "cinema_cosmos")
        self.assertIn("protocol_cosmos", deep["recommended_tools"])

        vs = assess_topic_complexity("Python vs Rust", genre="versus_battle", lang="en")
        self.assertEqual(vs["recommended_voice_mode"], "podcast")
        self.assertIn("versus_split", vs["recommended_tools"])

        short = assess_topic_complexity("Crypto tip", genre="short_60s", lang="en")
        self.assertEqual(short["recommended_preset"], "fast_shorts")
        self.assertIn("stat_burst", short["recommended_tools"])

    def test_critique_deck_flags_missing_visuals_duplicates_and_bad_short_captions(self) -> None:
        weak_deck = {
            "slug": "weak",
            "lang": "ru",
            "aspect": "9:16",
            "caption_style": "box",
            "slides": [
                {"id": "s1", "type": "kpi", "title": "A", "voice_text": "Раз два"},
                {"id": "s2", "type": "kpi", "title": "B", "voice_text": " ".join(["слово"] * 100)},
                {"id": "s3", "type": "quote", "title": "C", "voice_text": "Нормальный текст на восемь разных слов здесь."},
                {"id": "s4", "type": "timeline", "title": "D", "voice_text": "Ещё один нормальный текст для четвёртого слайда."},
            ],
        }
        report = critique_deck(weak_deck)
        self.assertTrue(report["ok"])
        self.assertLess(report["score"], 70)
        self.assertGreaterEqual(len(report["add"]), 2)      # no hook, no visual, no outro
        self.assertGreaterEqual(len(report["remove"]), 2)   # duplicate kpi + >95 words
        self.assertGreaterEqual(len(report["upgrade"]), 2)  # short voice + 9:16 box captions

    def test_auto_fix_deck_repairs_short_captions_preset_and_outro(self) -> None:
        deck = {
            "slug": "autofix-test",
            "lang": "en",
            "theme": "neon_cyber",
            "aspect": "9:16",
            "caption_style": "box",
            "voice": {"engine": "kokoro_v1", "lang": "en", "speaker": "am_michael"},
            "slides": [
                {
                    "id": "s1",
                    "tag": "HOOK",
                    "type": "stat_burst",
                    "title": "Fast Hook",
                    "voice_text": "One clear insight delivered in sixty seconds without fluff.",
                    "stat_burst": {"headline": "60 SEC", "caption": "Fast vertical breakdown"},
                }
            ],
        }
        fixed, changes = auto_fix_deck(deck)
        self.assertEqual(fixed["caption_style"], "bold")
        self.assertEqual(fixed["director_preset"], "fast_shorts")
        self.assertEqual(fixed["slides"][-1]["type"], "outro_3d")
        self.assertEqual(len(changes), 3)


if __name__ == "__main__":
    unittest.main()
