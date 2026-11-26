"""Offline fail-closed tests for the Stage 4 storyboard approval gate (no ffmpeg, no network).

Every test builds an isolated fake repo root in a temp dir; the frame extractor is injected.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import storyboard_gate as sg  # noqa: E402

SLUG = "sb-test"


def _deck(title: str = "Intro", order: str = "a") -> dict:
    return {
        "slug": SLUG,
        "brand": "T",
        "slides": [
            {"id": "a1s01", "type": "cinema_clip", "title": title, "voice_text": "Hello world"},
            {"id": "a1s02", "type": "title", "title": "Second"},
        ],
    }


def _fake_extractor(calls: list):
    def extract(mp4: Path, t_sec: float, out_jpg: Path) -> None:
        calls.append((t_sec, out_jpg.name))
        out_jpg.write_bytes(b"\xff\xd8" + b"x" * 4096)

    return extract


class StoryboardGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="sbgate_"))
        (self.root / "decks").mkdir()
        (self.root / "out").mkdir()
        self.deck_path = self.root / "decks" / f"{SLUG}.json"
        self.deck_path.write_text(json.dumps(_deck(), ensure_ascii=False), encoding="utf-8")
        self.mp4 = self.root / "out" / f"{SLUG}_draft.mp4"
        self.mp4.write_bytes(b"draft-bytes-v1")
        self.slides = [
            {"id": "a1s01", "type": "cinema_clip", "title": "Intro", "start_sec": 0.0, "duration_sec": 10.0},
            {"id": "a1s02", "type": "title", "title": "Second", "start_sec": 10.0, "duration_sec": 4.0},
        ]

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    # helpers -------------------------------------------------------------

    def _record_draft(self) -> None:
        sg.record_draft_build(SLUG, sg.deck_fingerprint(_deck()), self.slides, root=self.root)

    def _full_chain(self) -> list:
        calls: list = []
        self._record_draft()
        sg.build_storyboard(SLUG, root=self.root, extract_frame=_fake_extractor(calls))
        sg.approve(SLUG, root=self.root)
        return calls

    def _rewrite_deck(self, deck: dict) -> None:
        self.deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")

    # fingerprint ---------------------------------------------------------

    def test_fingerprint_ignores_key_order_but_tracks_content(self) -> None:
        a = {"slug": "x", "slides": [{"id": "s1", "title": "T"}]}
        b = {"slides": [{"title": "T", "id": "s1"}], "slug": "x"}
        self.assertEqual(sg.deck_fingerprint(a), sg.deck_fingerprint(b))
        c = {"slug": "x", "slides": [{"id": "s1", "title": "T2"}]}
        self.assertNotEqual(sg.deck_fingerprint(a), sg.deck_fingerprint(c))

    # gate refusals ------------------------------------------------------

    def test_no_draft_blocks_master(self) -> None:
        self.mp4.unlink()
        st = sg.gate_status(SLUG, root=self.root)
        self.assertFalse(st["can_master"])
        self.assertFalse(st["draft_exists"])
        with self.assertRaises(sg.StoryboardGateError):
            sg.assert_master_allowed(SLUG, root=self.root)

    def test_draft_without_build_record_blocks_master(self) -> None:
        st = sg.gate_status(SLUG, root=self.root)
        self.assertTrue(st["draft_exists"])
        self.assertFalse(st["draft_fresh"])
        self.assertFalse(st["can_master"])

    def test_fresh_draft_without_storyboard_or_approval_blocks_master(self) -> None:
        self._record_draft()
        st = sg.gate_status(SLUG, root=self.root)
        self.assertTrue(st["draft_fresh"])
        self.assertFalse(st["storyboard_ready"])
        self.assertFalse(st["can_master"])

    def test_storyboard_refused_without_fresh_draft(self) -> None:
        with self.assertRaises(sg.StoryboardGateError):
            sg.build_storyboard(SLUG, root=self.root, extract_frame=_fake_extractor([]))

    def test_approve_refused_without_storyboard(self) -> None:
        self._record_draft()
        with self.assertRaises(sg.StoryboardGateError):
            sg.approve(SLUG, root=self.root)
        self.assertFalse(sg.gate_status(SLUG, root=self.root)["can_master"])

    # happy path ---------------------------------------------------------

    def test_full_chain_allows_master(self) -> None:
        self._full_chain()
        st = sg.assert_master_allowed(SLUG, root=self.root)
        self.assertTrue(st["can_master"])
        self.assertTrue(st["approved_at"])

    def test_storyboard_uses_draft_timings_not_shared_cache(self) -> None:
        calls = self._full_chain()
        # a1s01: start 0 + min(2.5, 10*0.4)=2.5 ; a1s02: start 10 + min(2.5, 4*0.4)=1.6
        self.assertEqual(calls[0], (2.5, "a1s01.jpg"))
        self.assertAlmostEqual(calls[1][0], 11.6, places=3)
        index = json.loads((self.root / "work" / SLUG / "storyboard" / "index.json").read_text(encoding="utf-8"))
        self.assertEqual([s["id"] for s in index["slides"]], ["a1s01", "a1s02"])
        self.assertEqual(index["slides"][0]["voice_text"], "Hello world")

    def test_visual_credit_is_attached_from_plan(self) -> None:
        plan_dir = self.root / "work" / "visual_sources" / SLUG
        plan_dir.mkdir(parents=True)
        plan = {"scenes": [{"id": "a1s01", "asset": {
            "kind": "image", "source": "wikimedia", "source_id": "1", "title": "Nebula",
            "creator": "Someone", "license": "by-sa", "license_url": "https://x", "page_url": "https://commons/x",
        }}]}
        (plan_dir / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        self._full_chain()
        index = json.loads((self.root / "work" / SLUG / "storyboard" / "index.json").read_text(encoding="utf-8"))
        visual = index["slides"][0]["visual"]
        self.assertEqual(visual["source"], "wikimedia")
        self.assertEqual(visual["license"], "by-sa")
        self.assertIsNone(index["slides"][1]["visual"])

    # invalidation -------------------------------------------------------

    def test_deck_edit_invalidates_approval(self) -> None:
        self._full_chain()
        self._rewrite_deck(_deck(title="Changed"))
        st = sg.gate_status(SLUG, root=self.root)
        self.assertFalse(st["can_master"])
        self.assertIn("колода изменилась", st["reason"])
        with self.assertRaises(sg.StoryboardGateError):
            sg.assert_master_allowed(SLUG, root=self.root)

    def test_new_draft_bytes_invalidate_approval(self) -> None:
        self._full_chain()
        self.mp4.write_bytes(b"draft-bytes-v2-different")
        st = sg.gate_status(SLUG, root=self.root)
        self.assertFalse(st["can_master"])
        self.assertFalse(st["draft_fresh"])

    def test_revoke_blocks_master(self) -> None:
        self._full_chain()
        st = sg.revoke(SLUG, root=self.root)
        self.assertFalse(st["can_master"])
        self.assertTrue(st["storyboard_ready"])
        self.assertIn("не одобрена", st["reason"])

    def test_storyboard_view_hides_stale_index(self) -> None:
        self._full_chain()
        self.assertIsNotNone(sg.storyboard_view(SLUG, root=self.root)["index"])
        self._rewrite_deck(_deck(title="Changed"))
        self.assertIsNone(sg.storyboard_view(SLUG, root=self.root)["index"])

    # input validation / fail-closed I/O --------------------------------

    def test_record_refuses_unsafe_slide_id(self) -> None:
        bad = [{"id": "../evil", "type": "x", "title": "t", "start_sec": 0, "duration_sec": 1}]
        with self.assertRaises(sg.StoryboardGateError):
            sg.record_draft_build(SLUG, sg.deck_fingerprint(_deck()), bad, root=self.root)

    def test_frame_not_written_is_refused(self) -> None:
        self._record_draft()

        def lazy(mp4: Path, t: float, out: Path) -> None:  # writes nothing
            return None

        with self.assertRaises(sg.StoryboardGateError):
            sg.build_storyboard(SLUG, root=self.root, extract_frame=lazy)

    def test_slug_traversal_is_refused(self) -> None:
        for bad in ("../escape", "a/b", "", "x" * 80):
            with self.assertRaises(sg.StoryboardGateError):
                sg.gate_status(bad, root=self.root)

    def test_corrupt_approval_is_refused_not_ignored(self) -> None:
        self._full_chain()
        (self.root / "work" / SLUG / "storyboard" / "approval.json").write_text("{not json", encoding="utf-8")
        with self.assertRaises(sg.StoryboardGateError):
            sg.gate_status(SLUG, root=self.root)


if __name__ == "__main__":
    unittest.main()
