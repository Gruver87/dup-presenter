"""LinkedIn copy: length limits enforced, QA facts only for a passed report, written into the publish pack."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import linkedin_copy as lc  # noqa: E402
import publish_pack as pp  # noqa: E402


def _resolved(subtitle: str = "Short subtitle", url: str = "github.com/Gruver87/dup-presenter") -> dict:
    return {
        "slug": "demo-film",
        "brand": "DUP LABS",
        "lang": "en",
        "slides": [
            {"id": "u0", "title": "The Fail-Closed Law", "subtitle": subtitle, "duration_sec": 30.0, "start_sec": 0.0},
            {"id": "u1", "title": "Core", "duration_sec": 30.0, "start_sec": 30.0, "url": url},
        ],
    }


CHAPTERS = [
    {"time": "00:00", "title": "The Fail-Closed Law"},
    {"time": "00:30", "title": "Core"},
]

PASSED_QA = {
    "ok": True,
    "hard_fails": 0,
    "width": 1920,
    "height": 1080,
    "duration_sec": 339.7,
    "audio": {"integrated_lufs": -15.97, "true_peak_dbtp": -1.32},
}


class LinkedinCopyTests(unittest.TestCase):
    def test_short_copy_is_within_limits_and_names_the_repo(self) -> None:
        copy = lc.build_linkedin_copy(_resolved(), chapters=CHAPTERS)
        self.assertEqual(copy["errors"], [])
        self.assertLessEqual(copy["post_chars"], lc.POST_MAX_CHARS)
        self.assertLessEqual(copy["comment_chars"], lc.COMMENT_MAX_CHARS)
        self.assertIn("https://github.com/Gruver87/dup-presenter", copy["post"])
        self.assertIn(lc.DISCLAIMER, copy["post"])
        self.assertIn("Chapters: 00:00 The Fail-Closed Law | 00:30 Core", copy["comment"])

    def test_overlong_comment_is_flagged_not_silently_truncated(self) -> None:
        many = [{"time": f"{i:02d}:00", "title": "x" * 80} for i in range(30)]
        copy = lc.build_linkedin_copy(_resolved(), chapters=many)
        self.assertTrue(any("comment is" in e for e in copy["errors"]))
        self.assertGreater(copy["comment_chars"], lc.COMMENT_MAX_CHARS)  # the full text is kept, not cut

    def test_overlong_post_is_flagged(self) -> None:
        copy = lc.build_linkedin_copy(_resolved(subtitle="w " * 2000), chapters=CHAPTERS)
        self.assertTrue(any("post is" in e for e in copy["errors"]))

    def test_qa_line_only_for_a_passed_report(self) -> None:
        with_qa = lc.build_linkedin_copy(_resolved(), chapters=CHAPTERS, qa_report=PASSED_QA)
        self.assertIn("1920x1080, 339.7 s, -15.97 LUFS", with_qa["comment"])
        failed = dict(PASSED_QA, ok=False, hard_fails=1)
        without = lc.build_linkedin_copy(_resolved(), chapters=CHAPTERS, qa_report=failed)
        self.assertNotIn("How the MP4 was checked", without["comment"])

    def test_no_headline_is_an_error(self) -> None:
        resolved = {"slug": "x", "slides": [{"id": "u0", "title": ""}]}
        copy = lc.build_linkedin_copy(resolved, chapters=[])
        self.assertTrue(any("no headline" in e for e in copy["errors"]))

    def test_publish_pack_writes_the_linkedin_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = pp.build_publish_pack(_resolved(), mp4_path=None, qa_report=PASSED_QA, out_dir=Path(tmp))
            text = paths["linkedin"].read_text(encoding="utf-8")
        self.assertIn("## First comment", text)
        self.assertIn("OK", text)


if __name__ == "__main__":
    unittest.main()
