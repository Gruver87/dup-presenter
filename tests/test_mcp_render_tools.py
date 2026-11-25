"""Fail-closed tests for MCP render tools (render_deck / render_status / preview_stills)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import deck_doctor  # noqa: E402
import mcp_server  # noqa: E402

EN_DECK = ROOT / "decks" / "radar-cosmic-v4-en.json"


def _music_free_deck(tmp: Path) -> Path:
    """Copy of the EN deck with music disabled: its track is gitignored, so CI has no copy."""
    deck = json.loads(EN_DECK.read_text(encoding="utf-8"))
    deck["music"] = {**(deck.get("music") or {}), "enabled": False}
    path = tmp / "deck.json"
    path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")
    return path


class McpRenderToolsTests(unittest.TestCase):
    def test_safe_slug_rejects_traversal_and_accepts_normal_slug(self) -> None:
        self.assertEqual(mcp_server._safe_slug("radar-cosmic-v4-en"), "radar-cosmic-v4-en")
        for bad in ("../evil", "a/b", "", "UPPER", "x" * 200, "with space"):
            with self.subTest(slug=bad), self.assertRaises(ValueError):
                mcp_server._safe_slug(bad)

    def test_start_render_refuses_existing_mp4_without_spawning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            deck_file = _music_free_deck(root)
            slug = json.loads(deck_file.read_text(encoding="utf-8"))["slug"]
            (root / "out").mkdir()
            (root / "out" / f"{slug}.mp4").write_bytes(b"x")
            with mock.patch.object(deck_doctor, "OUT_DIR", root / "out"), \
                    mock.patch.object(mcp_server, "ROOT", root), \
                    mock.patch.object(mcp_server.subprocess, "Popen") as popen:
                with self.assertRaises(ValueError) as ctx:
                    mcp_server._start_render(deck_file, skip_tts=True, overwrite=False)
                self.assertIn("refusing to overwrite", str(ctx.exception))
                popen.assert_not_called()

    def test_start_render_refuses_second_concurrent_render(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            deck_file = _music_free_deck(root)
            slug = json.loads(deck_file.read_text(encoding="utf-8"))["slug"]
            (root / "out").mkdir()
            # A log without BUILD_EXIT means a build is still running.
            (root / "out" / f"{slug}_build.log").write_text("building...\n", encoding="utf-8")
            with mock.patch.object(deck_doctor, "OUT_DIR", root / "out"), \
                    mock.patch.object(mcp_server, "ROOT", root), \
                    mock.patch.object(mcp_server.subprocess, "Popen") as popen:
                with self.assertRaises(ValueError) as ctx:
                    mcp_server._start_render(deck_file, skip_tts=True, overwrite=False)
                self.assertIn("already running", str(ctx.exception))
                popen.assert_not_called()

    def test_render_status_not_started_and_rejects_bad_slug(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(mcp_server, "ROOT", Path(tmp)):
                self.assertEqual(mcp_server._render_status("nope")["status"], "not_started")
                with self.assertRaises(ValueError):
                    mcp_server._render_status("../etc")

    def test_preview_stills_rejects_bad_only_slide_without_spawning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            deck_file = _music_free_deck(Path(tmp))
            with mock.patch.object(mcp_server.subprocess, "run") as run:
                with self.assertRaises(ValueError):
                    mcp_server._preview_stills(deck_file, only_slide="../s1", skip_tts=True)
                run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
