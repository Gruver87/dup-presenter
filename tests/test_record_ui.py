"""Tests for the scenario-driven UI recorder (validation is pure; the live test drives real Chromium)."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import record_ui  # noqa: E402
from record_ui import RecordUIError, validate_scenario  # noqa: E402

EXAMPLE = ROOT / "scenarios" / "example_local_demo.json"


def _valid() -> dict:
    return {
        "name": "demo-1",
        "url": "http://127.0.0.1:8787/",
        "viewport": {"width": 1920, "height": 1080},
        "steps": [
            {"action": "click", "selector": "#go"},
            {"action": "type", "selector": "#q", "text": "abc"},
            {"action": "scroll", "dy": 300},
            {"action": "wait", "ms": 500},
        ],
    }


class ValidateScenarioTests(unittest.TestCase):
    def test_valid_scenario_is_normalised(self) -> None:
        sc = validate_scenario(_valid())
        self.assertEqual(sc["viewport"], {"width": 1920, "height": 1080})
        self.assertEqual(len(sc["steps"]), 4)
        self.assertEqual(sc["steps"][0]["cursor_ms"], record_ui.CURSOR_MS_DEFAULT)

    def test_rejects_bad_name(self) -> None:
        for bad in ("../evil", "Upper", "", "with space", "x" * 80):
            with self.subTest(name=bad), self.assertRaises(RecordUIError):
                validate_scenario({**_valid(), "name": bad})

    def test_rejects_non_http_schemes(self) -> None:
        for bad in ("javascript:alert(1)", "ftp://x/y", "data:text/html,hi", "/relative/path"):
            with self.subTest(url=bad), self.assertRaises(RecordUIError):
                validate_scenario({**_valid(), "url": bad})

    def test_rejects_unknown_action(self) -> None:
        sc = _valid()
        sc["steps"] = [{"action": "eval", "code": "alert(1)"}]
        with self.assertRaises(RecordUIError):
            validate_scenario(sc)

    def test_rejects_bool_as_int_and_out_of_range(self) -> None:
        sc = _valid()
        sc["steps"] = [{"action": "wait", "ms": True}]
        with self.assertRaises(RecordUIError):
            validate_scenario(sc)
        sc["steps"] = [{"action": "wait", "ms": record_ui.MAX_WAIT_MS + 1}]
        with self.assertRaises(RecordUIError):
            validate_scenario(sc)
        sc["steps"] = [{"action": "scroll", "dy": 99999}]
        with self.assertRaises(RecordUIError):
            validate_scenario(sc)

    def test_rejects_missing_selector_and_text(self) -> None:
        with self.assertRaises(RecordUIError):
            validate_scenario({**_valid(), "steps": [{"action": "click"}]})
        with self.assertRaises(RecordUIError):
            validate_scenario({**_valid(), "steps": [{"action": "type", "selector": "#q"}]})

    def test_rejects_too_many_steps_and_empty_steps(self) -> None:
        with self.assertRaises(RecordUIError):
            validate_scenario({**_valid(), "steps": []})
        with self.assertRaises(RecordUIError):
            validate_scenario({**_valid(), "steps": [{"action": "wait", "ms": 1}] * (record_ui.MAX_STEPS + 1)})

    def test_rejects_scenario_over_length_budget(self) -> None:
        sc = copy.deepcopy(_valid())
        sc["steps"] = [{"action": "wait", "ms": record_ui.MAX_WAIT_MS}] * 40  # 800 s > 600 s budget
        with self.assertRaises(RecordUIError) as ctx:
            validate_scenario(sc)
        self.assertIn("exceeds", str(ctx.exception))

    def test_zoom_defaults_and_reset(self) -> None:
        sc = validate_scenario({**_valid(), "steps": [{"action": "zoom", "selector": "#r"}]})
        self.assertEqual(sc["steps"][0]["scale"], record_ui.ZOOM_SCALE_DEFAULT)
        self.assertEqual(sc["steps"][0]["ms"], record_ui.ZOOM_MS_DEFAULT)
        reset = validate_scenario({**_valid(), "steps": [{"action": "zoom"}]})
        self.assertNotIn("scale", reset["steps"][0])
        self.assertNotIn("selector", reset["steps"][0])

    def test_zoom_rejects_bad_scale_and_duration(self) -> None:
        for bad_scale in (0.5, 3.0, True, "1.5", None):
            with self.subTest(scale=bad_scale), self.assertRaises(RecordUIError):
                validate_scenario({**_valid(), "steps": [{"action": "zoom", "selector": "#r", "scale": bad_scale}]})
        with self.assertRaises(RecordUIError):
            validate_scenario({**_valid(), "steps": [{"action": "zoom", "ms": 50}]})

    def test_rejects_bad_viewport(self) -> None:
        with self.assertRaises(RecordUIError):
            validate_scenario({**_valid(), "viewport": {"width": 100, "height": 1080}})
        with self.assertRaises(RecordUIError):
            validate_scenario({**_valid(), "viewport": "1920x1080"})

    def test_example_scenario_file_validates_after_placeholder_substitution(self) -> None:
        text = EXAMPLE.read_text(encoding="utf-8").replace("{SCENARIO_DIR}", EXAMPLE.parent.as_posix())
        sc = validate_scenario(json.loads(text))
        self.assertTrue(sc["url"].startswith("file:///"))
        self.assertTrue(Path(sc["url"][len("file:///"):]).is_file())


class LiveRecordTests(unittest.TestCase):
    """Drives real Chromium through Playwright and encodes MP4 with ffmpeg. Fails loudly if unavailable."""

    def test_example_scenario_records_mp4_and_timeline(self) -> None:
        text = EXAMPLE.read_text(encoding="utf-8").replace("{SCENARIO_DIR}", EXAMPLE.parent.as_posix())
        scenario = json.loads(text)
        with tempfile.TemporaryDirectory() as tmp:
            result = record_ui.record_scenario(scenario, out_dir=Path(tmp), overwrite=True)
            self.assertTrue(result["ok"])
            mp4 = Path(result["mp4"])
            self.assertTrue(mp4.is_file() and mp4.stat().st_size > 10_000, "MP4 missing or too small")
            timeline = json.loads(Path(result["timeline"]).read_text(encoding="utf-8"))
            # goto (injected) + the 6 scenario steps
            self.assertEqual(len(timeline["steps"]), 1 + len(scenario["steps"]))
            self.assertGreater(timeline["duration_sec"], 5.0)
            starts = [s["start_sec"] for s in timeline["steps"]]
            self.assertEqual(starts, sorted(starts), "step timeline must be monotonic")

    def test_refuses_to_overwrite_without_flag(self) -> None:
        text = EXAMPLE.read_text(encoding="utf-8").replace("{SCENARIO_DIR}", EXAMPLE.parent.as_posix())
        scenario = json.loads(text)
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / f"{scenario['name']}.mp4").write_bytes(b"x")
            with self.assertRaises(RecordUIError) as ctx:
                record_ui.record_scenario(scenario, out_dir=Path(tmp), overwrite=False)
            self.assertIn("already exists", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
