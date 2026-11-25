"""End-to-end automated gate tests for DUP Presenter (Sprints A, B, C)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import audio_fx  # noqa: E402
import build_deck  # noqa: E402
import claim_audit  # noqa: E402
import make_cutdown  # noqa: E402
import mcp_server  # noqa: E402
import publish_pack  # noqa: E402
import ru_speech  # noqa: E402


class PresenterGatesTests(unittest.TestCase):
    def test_all_decks_validate_fail_closed(self) -> None:
        decks = sorted((ROOT / "decks").glob("*.json"))
        self.assertGreater(len(decks), 0)
        for dp in decks:
            data = json.loads(dp.read_text(encoding="utf-8"))
            # Schema only: some decks reference local-only screenshots (gitignored, not in CI).
            # Asset presence is enforced at render time by deck_doctor / validate_deck(check_assets=True).
            build_deck.validate_deck(data, check_assets=False)

    def test_validation_rejects_bad_transition_and_duck(self) -> None:
        base = json.loads((ROOT / "decks" / "radar-pro.json").read_text(encoding="utf-8"))
        bad_tr = dict(base, transition={"style": "unknown", "frames": 12})
        with self.assertRaises(build_deck.DeckValidationError):
            build_deck.validate_deck(bad_tr)
        bad_duck = dict(base, music={"enabled": True, "volume": 0.1, "duck_db": -40.0})
        with self.assertRaises(build_deck.DeckValidationError):
            build_deck.validate_deck(bad_duck)

    def test_audio_fx_sfx_and_speech_windows(self) -> None:
        sfx = audio_fx.ensure_sfx_files()
        self.assertTrue((ROOT / "public" / sfx["transition"]).is_file())
        self.assertTrue((ROOT / "public" / sfx["pop"]).is_file())
        # Synthetic audio: 1s silence + 2s speech + 1s silence
        sr = audio_fx.SR
        t = np.linspace(0, 2.0, 2 * sr, endpoint=False)
        speech = (0.25 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
        sig = np.concatenate([np.zeros(sr, dtype=np.float32), speech, np.zeros(sr, dtype=np.float32)])
        wins = audio_fx.detect_speech_windows(sig, sr=sr, offset_sec=0.5)
        self.assertEqual(len(wins), 1)
        self.assertAlmostEqual(wins[0][0], 1.5, delta=0.1)
        self.assertAlmostEqual(wins[0][1], 3.5, delta=0.1)

    def test_word_captions_with_real_boundaries(self) -> None:
        bounds = [
            {"start_sec": 0.1, "end_sec": 2.1, "text": "Привет мир."},
            {"start_sec": 2.4, "end_sec": 4.4, "text": "Второй тест."},
        ]
        cues = audio_fx.build_word_captions("Привет мир. Второй тест.", 5.0, boundaries=bounds, offset_sec=0.2)
        self.assertEqual(len(cues), 2)
        self.assertAlmostEqual(cues[0]["start_sec"], 0.3, delta=0.01)
        self.assertEqual(len(cues[0]["words"]), 2)
        self.assertEqual(cues[0]["words"][0]["w"], "Привет")
        self.assertGreater(cues[0]["words"][1]["end"], cues[0]["words"][0]["end"])

    def test_pronunciation_config_overrides_applied(self) -> None:
        table = ru_speech.get_latin_ru()
        self.assertIn("playwright", table)
        self.assertIn("lufs", table)
        out = ru_speech.normalize_ru_ssml("Рендер через Remotion в -16 LUFS.")
        self.assertIn("ремоушн", out)
        self.assertIn("луфс", out)

    def test_claim_audit_negation_and_contradiction(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            (repo / "config.py").write_text("enabled_default = False\nFUTURES_BLOCK = True\nPRICE_SCALE = 100_000_000\n", encoding="utf-8")
            good_deck = {
                "slug": "good",
                "slides": [
                    {
                        "id": "s1",
                        "title": "Безопасность",
                        "voice_text": "Автоторговля выключена по умолчанию и не торгует фьючерсами.",
                        "evidence": ["config.py:1-2"],
                    }
                ],
            }
            rep_good = claim_audit.audit_deck(good_deck, repo_root=repo)
            self.assertTrue(rep_good["hard_ok"], rep_good)
            self.assertEqual(rep_good["safety_warnings"], [])
            self.assertEqual(rep_good["evidence_errors"], [])

            bad_deck = {
                "slug": "bad",
                "slides": [
                    {
                        "id": "s1",
                        "title": "Ложное обещание",
                        "voice_text": "Бот торгует фьючерсами и автоторговля включена по умолчанию.",
                        "evidence": ["missing_file.py:99"],
                    }
                ],
            }
            rep_bad = claim_audit.audit_deck(bad_deck, repo_root=repo)
            self.assertFalse(rep_bad["hard_ok"])
            self.assertEqual(len(rep_bad["safety_warnings"]), 2)
            self.assertEqual(len(rep_bad["evidence_errors"]), 1)

    def test_short_cutdown_produces_valid_9_16(self) -> None:
        src = json.loads((ROOT / "decks" / "radar-pro.json").read_text(encoding="utf-8"))
        short = make_cutdown.build_short_cutdown(src, max_slides=4)
        self.assertEqual(short["aspect"], "9:16")
        self.assertEqual(len(short["slides"]), 4)
        self.assertTrue(short["slug"].endswith("-short"))
        build_deck.validate_deck(short)

    def test_offline_only_blocks_online_stock_background(self) -> None:
        src = json.loads((ROOT / "decks" / "radar-pro.json").read_text(encoding="utf-8"))
        src["background"] = {"enabled": True, "provider": "pixabay"}
        with self.assertRaises(build_deck.DeckValidationError):
            build_deck.synthesize_deck(src, offline_only=True)

    def test_publish_pack_chapters_start_at_00_00(self) -> None:
        fake_resolved = {
            "slug": "_unit_pack_test",
            "lang": "ru",
            "brand": "DUP LABS",
            "aspect": "16:9",
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "total_seconds": 30.0,
            "voice_used": "dmitry",
            "slides": [
                {"id": "s1", "title": "Вступление", "start_sec": 0.0, "duration_sec": 15},
                {"id": "s2", "title": "Финал", "start_sec": 14.6, "duration_sec": 15.4},
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            pack = publish_pack.build_publish_pack(fake_resolved, out_dir=Path(td))
            ch = pack["chapters"].read_text(encoding="utf-8")
            self.assertTrue(ch.startswith("00:00 Вступление"))
            self.assertIn("00:15 Финал", ch)

    def test_mcp_server_rpc_initialize_and_list(self) -> None:
        r1 = mcp_server.handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertEqual(r1["result"]["serverInfo"]["name"], "dup-presenter-mcp")
        r2 = mcp_server.handle_rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        names = {t["name"] for t in r2["result"]["tools"]}
        self.assertTrue({"list_decks", "audit_deck_claims", "make_short_cutdown", "run_media_qa", "pronunciation_dictionary"}.issubset(names))
        r3 = mcp_server.handle_rpc({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "list_decks", "arguments": {}}})
        self.assertFalse(r3["result"]["isError"])


if __name__ == "__main__":
    unittest.main()
