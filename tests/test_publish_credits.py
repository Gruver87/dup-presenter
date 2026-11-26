"""CC BY / CC BY-SA attribution in the publish pack (post_copy.md)."""
from __future__ import annotations

import json
import shutil
import sys
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import publish_pack  # noqa: E402


def _asset(title: str, licence: str) -> dict:
    return {
        "title": title,
        "creator": f"Author of {title}",
        "license": licence,
        "license_url": f"https://creativecommons.org/licenses/{licence}/4.0/",
        "page_url": f"https://commons.wikimedia.org/wiki/File:{title}.jpg",
        "kind": "image",
        "file": f"visual/{title}.jpg",
    }


class VisualCreditLinesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = ROOT / "work" / f"_test_credits_{uuid.uuid4().hex[:8]}"
        self.tmp.mkdir(parents=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _plan(self, scenes: list[dict]) -> Path:
        path = self.tmp / "plan.json"
        path.write_text(json.dumps({"slug": "t", "title": "T", "scenes": scenes}), encoding="utf-8")
        return path

    def test_by_and_by_sa_get_lines_cc0_and_pdm_do_not(self) -> None:
        plan = self._plan([
            {"id": "s1", "asset": _asset("nebula-by", "by")},
            {"id": "s2", "asset": _asset("stars-bysa", "by-sa")},
            {"id": "s3", "asset": _asset("sun-cc0", "cc0")},
            {"id": "s4", "asset": _asset("moon-pdm", "pdm")},
            {"id": "s5", "asset": None},
        ])
        lines = publish_pack.visual_credit_lines("t", plan_path=plan)
        self.assertEqual(len(lines), 2)
        self.assertIn("nebula-by", lines[0])
        self.assertIn("Author of nebula-by", lines[0])
        self.assertIn("https://commons.wikimedia.org/wiki/File:nebula-by.jpg", lines[0])
        self.assertIn("stars-bysa", lines[1])
        self.assertFalse(any("sun-cc0" in line or "moon-pdm" in line for line in lines))

    def test_missing_plan_gives_no_lines(self) -> None:
        self.assertEqual(publish_pack.visual_credit_lines("t", plan_path=self.tmp / "absent.json"), [])

    def test_post_copy_contains_credits_section_only_when_needed(self) -> None:
        resolved = {
            "slug": "credits-test",
            "lang": "en",
            "slides": [{"id": "s1", "title": "Hero", "start_sec": 0, "duration_sec": 5}],
        }
        out_dir = self.tmp / "out"

        # No plan for this slug -> no credits section.
        build_plain = publish_pack.build_publish_pack(resolved, out_dir=out_dir)
        self.assertNotIn("Visual credits", build_plain["post_copy"].read_text(encoding="utf-8"))

        # Plan with a CC BY asset -> section + attribution line in post copy.
        plan_file = self.tmp / "plan.json"
        plan_file.write_text(json.dumps({
            "slug": "credits-test", "title": "T",
            "scenes": [{"id": "s1", "asset": _asset("nebula-by", "by")}],
        }), encoding="utf-8")
        original = publish_pack.visual_credit_lines
        publish_pack.visual_credit_lines = lambda slug: original(slug, plan_path=plan_file)
        try:
            build = publish_pack.build_publish_pack(resolved, out_dir=out_dir)
        finally:
            publish_pack.visual_credit_lines = original
        text = build["post_copy"].read_text(encoding="utf-8")
        self.assertIn("## Visual credits", text)
        self.assertIn("nebula-by", text)


if __name__ == "__main__":
    unittest.main()
