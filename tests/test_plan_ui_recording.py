"""Planner `ui_recording` slides: only existing recordings are referenced, and the assembled deck passes build_deck validation."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_deck  # noqa: E402
import plan_deck  # noqa: E402

DEMO_SRC = "ui_recordings/example-local-demo.mp4"


def _facts(root: str) -> dict:
    return {
        "root": root,
        "project": {"name": "demo"},
        "docs": [{"id": "D1", "path": "README.md", "lines": 1, "text": "Manual orders run only on KuCoin spot."}],
        "code": [],
        "images": [],
        "urls": ["https://github.com/example/demo"],
    }


def _recording_slide(src: object = DEMO_SRC, caption: object = "Live UI") -> dict:
    rec: dict = {"src": src}
    if caption is not None:
        rec["caption"] = caption
    return {
        "type": "ui_recording",
        "tag": "UI",
        "title": "Live UI",
        "subtitle": "Recorded scenario",
        "voice_text": "This clip shows a recorded scenario.",
        "bullets": [{"title": "Scenario", "desc": "Recorded from a JSON scenario"}],
        "recording": rec,
        "source_ids": ["D1"],
    }


class UiRecordingSlideValidationTests(unittest.TestCase):
    def test_existing_recording_is_accepted(self) -> None:
        errs = plan_deck.validate_ui_recording_slide(_recording_slide(), {DEMO_SRC}, "slide 2")
        self.assertEqual(errs, [])

    def test_unknown_recording_is_refused(self) -> None:
        errs = plan_deck.validate_ui_recording_slide(
            _recording_slide("ui_recordings/invented.mp4"), {DEMO_SRC}, "slide 2"
        )
        self.assertTrue(any("not an available recording" in e for e in errs), errs)

    def test_traversal_and_absolute_paths_are_refused(self) -> None:
        for bad in ("../secret.mp4", "/etc/passwd.mp4", "ui_recordings/../x.mp4", ["list"]):
            errs = plan_deck.validate_ui_recording_slide(_recording_slide(bad), {DEMO_SRC}, "slide 2")
            self.assertTrue(errs, f"expected refusal for {bad!r}")

    def test_missing_recording_object_is_refused(self) -> None:
        slide = _recording_slide()
        del slide["recording"]
        errs = plan_deck.validate_ui_recording_slide(slide, {DEMO_SRC}, "slide 2")
        self.assertTrue(any("needs recording" in e for e in errs), errs)

    def test_no_recordings_on_disk_refuses_the_slide(self) -> None:
        errs = plan_deck.validate_ui_recording_slide(_recording_slide(), set(), "slide 2")
        self.assertTrue(any("do not use ui_recording" in e for e in errs), errs)

    def test_non_string_caption_is_refused(self) -> None:
        errs = plan_deck.validate_ui_recording_slide(_recording_slide(caption=["x"]), {DEMO_SRC}, "slide 2")
        self.assertTrue(errs)

    def test_overlong_caption_is_refused(self) -> None:
        long = "c" * (plan_deck.UI_RECORDING_CAPTION_MAX + 1)
        errs = plan_deck.validate_ui_recording_slide(_recording_slide(caption=long), {DEMO_SRC}, "slide 2")
        self.assertTrue(errs)

    def test_type_is_in_planner_vocabulary(self) -> None:
        self.assertIn("ui_recording", plan_deck.SLIDE_TYPES)


class PlanIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.facts = _facts(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _plan(self, slide: dict) -> dict:
        return {
            "brand": "DEMO",
            "slides": [
                {"type": "hero_3d", "tag": "A", "title": "Demo", "subtitle": "x", "voice_text": "Demo.", "bullets": []},
                slide,
                {"type": "outro_3d", "tag": "O", "title": "End", "subtitle": "x", "voice_text": "End.", "bullets": []},
            ],
        }

    def test_valid_recording_plan_has_no_recording_errors(self) -> None:
        errors = plan_deck.validate_plan(self._plan(_recording_slide()), self.facts, lang="en", recordings={DEMO_SRC})
        self.assertFalse([e for e in errors if "recording" in e.lower()], errors)

    def test_invented_recording_plan_is_refused(self) -> None:
        errors = plan_deck.validate_plan(
            self._plan(_recording_slide("ui_recordings/invented.mp4")), self.facts, lang="en", recordings={DEMO_SRC}
        )
        self.assertTrue(any("not an available recording" in e for e in errors), errors)

    def test_assembled_deck_passes_build_deck_validation(self) -> None:
        deck = plan_deck.assemble_deck(self._plan(_recording_slide()), self.facts, "ui-plan-check", lang="en")
        rec_slide = deck["slides"][1]
        self.assertEqual(rec_slide["type"], "ui_recording")
        self.assertEqual(rec_slide["recording"], {"src": DEMO_SRC, "caption": "Live UI"})
        # check_assets=False: the file is checked against disk by list_ui_recordings above, not here.
        build_deck.validate_deck(deck, check_assets=False)


class RecordingListingTests(unittest.TestCase):
    def test_lists_only_valid_mp4_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "good-one.mp4").write_bytes(b"x")
            (d / "Bad Name.mp4").write_bytes(b"x")
            (d / "notes.txt").write_bytes(b"x")
            (d / "timeline.json").write_bytes(b"x")
            self.assertEqual(plan_deck.list_ui_recordings(d), ["ui_recordings/good-one.mp4"])

    def test_missing_directory_yields_empty_list(self) -> None:
        self.assertEqual(plan_deck.list_ui_recordings(Path("does-not-exist-xyz")), [])

    def test_planner_regex_matches_build_deck_regex(self) -> None:
        samples = [
            "ui_recordings/example-local-demo.mp4",
            "ui_recordings/a.mp4",
            "ui_recordings/-bad.mp4",
            "ui_recordings/UPPER.mp4",
            "ui_recordings/../x.mp4",
            "ui_recordings/" + "a" * 61 + ".mp4",
            "ui_recordings/" + "a" * 60 + ".mp4",
        ]
        for s in samples:
            self.assertEqual(
                bool(plan_deck.UI_RECORDING_SRC_RE.fullmatch(s)),
                bool(build_deck.UI_RECORDING_SRC_RE.fullmatch(s)),
                s,
            )


if __name__ == "__main__":
    unittest.main()
