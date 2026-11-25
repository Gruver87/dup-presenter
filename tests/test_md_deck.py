"""Markdown -> deck importer: maps the supported subset exactly and refuses everything else (fail-closed)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_deck  # noqa: E402
import md_deck  # noqa: E402

EXAMPLE = ROOT / "examples" / "md-talk-demo.md"

HEADER = "---\nslug: t-talk\nlang: en\n---\n"


class MarkdownParseTests(unittest.TestCase):
    def test_example_maps_all_supported_types(self) -> None:
        deck = md_deck.parse_markdown_deck(EXAMPLE.read_text(encoding="utf-8"))
        self.assertEqual(deck["slug"], "md-talk-demo")
        self.assertEqual(deck["caption_style"], "karaoke")
        types = [s["type"] for s in deck["slides"]]
        self.assertEqual(types, ["hero_3d", "kpi", "timeline", "outro_3d"])
        self.assertEqual([s["id"] for s in deck["slides"]], ["s1", "s2", "s3", "s4"])

    def test_example_passes_schema(self) -> None:
        deck = md_deck.parse_markdown_deck(EXAMPLE.read_text(encoding="utf-8"))
        build_deck.validate_deck(deck, check_assets=False)

    def test_kpi_and_timeline_bullets_are_split_on_double_colon(self) -> None:
        deck = md_deck.parse_markdown_deck(EXAMPLE.read_text(encoding="utf-8"))
        kpi, timeline = deck["slides"][1], deck["slides"][2]
        self.assertEqual(kpi["kpis"][0], {"value": "4488", "label": "instruments in the catalogue"})
        self.assertEqual(timeline["bullets"][0], {"title": "Fetch", "desc": "pull market data from the venue"})

    def test_voice_continues_over_lines_until_key_or_bullet(self) -> None:
        deck = md_deck.parse_markdown_deck(EXAMPLE.read_text(encoding="utf-8"))
        self.assertIn("watch-only futures", deck["slides"][0]["voice_text"])

    def test_defaults_disable_network_media(self) -> None:
        deck = md_deck.parse_markdown_deck(EXAMPLE.read_text(encoding="utf-8"))
        self.assertFalse(deck["music"]["enabled"])
        self.assertFalse(deck["background"]["enabled"])
        self.assertEqual(deck["voice"]["engine"], "kokoro_v1")


class MarkdownRefusalTests(unittest.TestCase):
    def _refused(self, text: str) -> str:
        with self.assertRaises(md_deck.MarkdownDeckError) as ctx:
            md_deck.parse_markdown_deck(text)
        return str(ctx.exception)

    def test_missing_front_matter_is_refused(self) -> None:
        self._refused("## [hero_3d] A\nvoice: hi\n")

    def test_unknown_front_matter_key_is_refused(self) -> None:
        msg = self._refused("---\nslug: t-talk\nlang: en\nmusic_volume: 1\n---\n## [hero_3d] A\nvoice: hi\n")
        self.assertIn("unknown front matter key", msg)

    def test_bad_slug_is_refused(self) -> None:
        self._refused("---\nslug: ../evil\nlang: en\n---\n## [hero_3d] A\nvoice: hi\n")

    def test_unsupported_slide_type_is_refused(self) -> None:
        msg = self._refused(HEADER + "## [code_split] Code\nvoice: hi\n")
        self.assertIn("not supported in Markdown", msg)

    def test_slide_without_voice_is_refused(self) -> None:
        msg = self._refused(HEADER + "## [hero_3d] A\ntag: X\n")
        self.assertIn("no 'voice:' narration", msg)

    def test_bullets_on_hero_slide_are_refused(self) -> None:
        msg = self._refused(HEADER + "## [hero_3d] A\nvoice: hi\n- a :: b\n")
        self.assertIn("bullets are not used", msg)

    def test_unrecognised_line_reports_line_number(self) -> None:
        # Right after 'voice:' a line is narration continuation; outside the voice block it must be refused.
        msg = self._refused(HEADER + "## [hero_3d] A\ntag: X\n???\nvoice: hi\n")
        self.assertIn("line 7", msg)

    def test_malformed_heading_is_refused(self) -> None:
        msg = self._refused(HEADER + "## Just a title\nvoice: hi\n")
        self.assertIn("slide heading must look like", msg)

    def test_text_before_first_slide_is_refused(self) -> None:
        self._refused(HEADER + "stray text\n## [hero_3d] A\nvoice: hi\n")

    def test_empty_talk_is_refused(self) -> None:
        self._refused(HEADER)

    def test_duplicate_key_in_slide_is_refused(self) -> None:
        self._refused(HEADER + "## [hero_3d] A\ntag: X\ntag: Y\nvoice: hi\n")

    def test_convert_refuses_overwrite_without_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "t-talk.json"
            src = Path(tmp) / "t.md"
            src.write_text(HEADER + "## [hero_3d] A\nvoice: hi\n", encoding="utf-8")
            md_deck.convert_file(src, out)
            with self.assertRaises(md_deck.MarkdownDeckError):
                md_deck.convert_file(src, out)
            md_deck.convert_file(src, out, overwrite=True)


if __name__ == "__main__":
    unittest.main()
