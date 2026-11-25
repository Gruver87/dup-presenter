"""Console Markdown import: write_deck_from_markdown is fail-closed (slug, size, schema, no silent overwrite)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import md_deck  # noqa: E402
from build_deck import validate_deck  # noqa: E402

EXAMPLE = (ROOT / "examples" / "md-talk-demo.md").read_text(encoding="utf-8")


def _with_slug(slug: str) -> str:
    assert "slug: md-talk-demo" in EXAMPLE, "example front matter changed; update this test"
    return EXAMPLE.replace("slug: md-talk-demo", f"slug: {slug}", 1)


class WriteDeckFromMarkdownTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.decks = Path(self._tmp.name) / "decks"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_valid_markdown_writes_schema_valid_deck(self) -> None:
        deck = md_deck.write_deck_from_markdown(_with_slug("import-ok"), self.decks)
        out = self.decks / "import-ok.json"
        self.assertTrue(out.is_file())
        written = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(written["slug"], deck["slug"])
        validate_deck(written, check_assets=False)

    def test_existing_deck_is_refused_without_overwrite(self) -> None:
        md_deck.write_deck_from_markdown(_with_slug("dup-one"), self.decks)
        with self.assertRaises(md_deck.MarkdownDeckExists):
            md_deck.write_deck_from_markdown(_with_slug("dup-one"), self.decks)

    def test_existing_deck_is_replaced_only_with_overwrite(self) -> None:
        md_deck.write_deck_from_markdown(_with_slug("dup-two"), self.decks)
        md_deck.write_deck_from_markdown(_with_slug("dup-two"), self.decks, overwrite=True)
        self.assertTrue((self.decks / "dup-two.json").is_file())

    def test_unsafe_slug_is_refused(self) -> None:
        with self.assertRaises(md_deck.MarkdownDeckError):
            md_deck.write_deck_from_markdown(_with_slug("../evil"), self.decks)
        self.assertFalse((self.decks.parent / "evil.json").exists())

    def test_oversized_input_is_refused(self) -> None:
        big = _with_slug("too-big") + ("\n" + "x" * md_deck.MAX_MARKDOWN_BYTES)
        with self.assertRaises(md_deck.MarkdownImportError):
            md_deck.write_deck_from_markdown(big, self.decks)
        self.assertFalse(self.decks.exists())

    def test_schema_error_writes_nothing(self) -> None:
        bad = _with_slug("bad-type").replace("[hero_3d]", "[no_such_type]", 1)
        with self.assertRaises(md_deck.MarkdownDeckError):
            md_deck.write_deck_from_markdown(bad, self.decks)
        self.assertFalse((self.decks / "bad-type.json").exists())


if __name__ == "__main__":
    unittest.main()
