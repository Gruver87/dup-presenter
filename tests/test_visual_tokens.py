"""Item 8: one visual token source. Drift between src/themes.ts, the outro cards and the formats fails here."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import visual_tokens as vt  # noqa: E402
import build_deck  # noqa: E402

THEMES_TS = (ROOT / "src" / "themes.ts").read_text(encoding="utf-8")
# Literals the outro used to hard-code and must no longer contain. The gradient stops (#091026, #02040b) and
# the mono stack are deliberately still present as TOKEN VALUES, so they are not listed here.
LEGACY_OUTRO_LITERALS = ("#030612", "#e2e8f0", "#94a3b8", "rgba(7,14,32,0.86)", 'Segoe UI", sans-serif')


def _theme_block(theme_id: str) -> str:
    m = re.search(rf"\n  {theme_id}: \{{(.*?)\n  \}},", THEMES_TS, re.S)
    if not m:
        raise AssertionError(f"theme block {theme_id!r} not found in src/themes.ts")
    return m.group(1)


def _ts_value(block: str, key: str) -> str:
    m = re.search(rf'\b{key}: "([^"]+)"', block)
    if not m:
        raise AssertionError(f"key {key!r} not found in theme block")
    return m.group(1)


class PaletteParityTests(unittest.TestCase):
    def test_neon_cyber_mirror_matches_typescript(self) -> None:
        block = _theme_block("neon_cyber")
        for key in ("bg", "text", "muted", "cardBg"):
            with self.subTest(key=key):
                self.assertEqual(vt.NEON_CYBER_MIRROR[key], _ts_value(block, key),
                                 f"visual_tokens.NEON_CYBER_MIRROR[{key!r}] drifted from src/themes.ts")


class FormatTests(unittest.TestCase):
    def test_formats_match_deck_builder(self) -> None:
        self.assertEqual(vt.FORMATS["16:9"], build_deck.ASPECT_DIMS["16:9"])
        self.assertEqual(vt.FORMATS["9:16"], build_deck.ASPECT_DIMS["9:16"])


class OutroTemplateTests(unittest.TestCase):
    def setUp(self) -> None:
        import render_tiktok_outros as rto

        self.html = rto.make_html("01", "dup-protocol", "role", "data:image/jpeg;base64,AA==", "#38bdf8", "#0284c7")

    def test_outro_uses_tokens_not_legacy_literals(self) -> None:
        for legacy in LEGACY_OUTRO_LITERALS:
            with self.subTest(legacy=legacy):
                self.assertNotIn(legacy, self.html)

    def test_outro_carries_theme_background_and_fonts(self) -> None:
        self.assertIn(vt.BG, self.html)
        self.assertIn(vt.TEXT, self.html)
        self.assertIn(vt.FONT_UI_CANVAS, self.html)
        self.assertIn(vt.FONT_MONO_CANVAS, self.html)

    def test_no_unresolved_format_fields_leak_into_html(self) -> None:
        self.assertNotIn("{FONT_", self.html)
        self.assertNotIn("{BG", self.html)


if __name__ == "__main__":
    unittest.main()
