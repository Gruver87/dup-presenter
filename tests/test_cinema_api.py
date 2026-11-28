"""Unit tests for scripts/cinema_api.py (fail-closed Runway Dev API, prompts, daily budget)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import cinema_api  # noqa: E402


class _FakeHTTPResp:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeHTTPResp":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class _BudgetFileMixin:
    """Redirect the budget ledger to a temp file for each test."""

    def setUp(self) -> None:  # noqa: N802
        self._td = tempfile.TemporaryDirectory()
        self._patch = mock.patch.object(cinema_api, "BUDGET_FILE", Path(self._td.name) / "cinema_budget.json")
        self._patch.start()
        self._env = mock.patch.dict(os.environ, {"RUNWAYML_API_SECRET": "rw_test_key"}, clear=False)
        self._env.start()
        os.environ.pop("DUP_CINEMA_DAILY_CREDITS", None)

    def tearDown(self) -> None:  # noqa: N802
        self._env.stop()
        self._patch.stop()
        self._td.cleanup()


class TestCinemaApi(_BudgetFileMixin, unittest.TestCase):
    def test_status_unconfigured_by_default(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            st = cinema_api.cinema_api_status()
            self.assertFalse(st["configured"])
            self.assertIsNone(st["provider"])
            self.assertEqual(st["env_var"], "RUNWAYML_API_SECRET")

    def test_generate_image_fails_closed_without_key(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True), tempfile.TemporaryDirectory() as td:
            with self.assertRaises(cinema_api.CinemaApiError):
                cinema_api.generate_image_runway("dark observatory", out_path=Path(td) / "a.png")
        # Nothing was reserved because the key check happens inside the paid call path
        self.assertEqual(cinema_api.budget_status()["spent_credits"], 0)

    def test_build_cinema_prompts_validates_inputs(self) -> None:
        with self.assertRaises(cinema_api.CinemaApiError):
            cinema_api.build_cinema_prompts("", ["scene 1"])
        with self.assertRaises(cinema_api.CinemaApiError):
            cinema_api.build_cinema_prompts("DUP Radar", [])
        out = cinema_api.build_cinema_prompts("DUP Radar", ["Core awakens", "Six streams"])
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["index"], "00")
        self.assertIn("DUP Radar", out[0]["image_prompt"])
        self.assertIn("no camera cuts", out[0]["video_prompt"])

    def test_estimate_credits_matches_runway_pricing(self) -> None:
        self.assertEqual(cinema_api.estimate_credits("image", "gen4_image"), 5)
        self.assertEqual(cinema_api.estimate_credits("image", "gen4_image_turbo"), 2)
        self.assertEqual(cinema_api.estimate_credits("video", "gen4_turbo", 5), 25)
        with self.assertRaises(cinema_api.CinemaApiError):
            cinema_api.estimate_credits("video", "kling_4", 5)
        with self.assertRaises(cinema_api.CinemaApiError):
            cinema_api.estimate_credits("video", "gen4_turbo", 7)

    def test_budget_refuses_when_cap_exceeded(self) -> None:
        with mock.patch.dict(os.environ, {"DUP_CINEMA_DAILY_CREDITS": "4"}):
            with tempfile.TemporaryDirectory() as td:
                with self.assertRaises(cinema_api.CinemaApiError) as ctx:
                    cinema_api.generate_image_runway("radar core", out_path=Path(td) / "a.png")
                self.assertIn("лимит", str(ctx.exception))
        self.assertEqual(cinema_api.budget_status()["spent_credits"], 0)

    def test_budget_is_unlimited_by_default(self) -> None:
        st = cinema_api.budget_status()
        self.assertTrue(st["unlimited"])
        self.assertIsNone(st["cap_credits"])
        self.assertIsNone(st["remaining_credits"])

    def test_prompt_with_secret_is_blocked_before_network(self) -> None:
        with mock.patch("urllib.request.urlopen") as up, tempfile.TemporaryDirectory() as td:
            with self.assertRaises(cinema_api.SecretLeakError):
                cinema_api.generate_image_runway("draw rw_test_key please", out_path=Path(td) / "a.png")
            up.assert_not_called()

    def test_budget_refunds_on_failed_task(self) -> None:
        responses = [
            _FakeHTTPResp(json.dumps({"id": "task_fail"}).encode("utf-8")),
            _FakeHTTPResp(json.dumps({"id": "task_fail", "status": "FAILED", "failure": "boom"}).encode("utf-8")),
        ]
        with mock.patch("urllib.request.urlopen", side_effect=responses), tempfile.TemporaryDirectory() as td:
            with self.assertRaises(cinema_api.CinemaApiError):
                cinema_api.generate_image_runway("radar core", out_path=Path(td) / "a.png", poll_timeout_sec=10.0)
        status = cinema_api.budget_status()
        self.assertEqual(status["spent_credits"], 0)

    def test_generate_image_runway_mocked_success_spends_credits(self) -> None:
        responses = [
            _FakeHTTPResp(json.dumps({"id": "task_123"}).encode("utf-8")),
            _FakeHTTPResp(
                json.dumps({"id": "task_123", "status": "SUCCEEDED", "output": ["https://cdn.example/img.png"]}).encode(
                    "utf-8"
                )
            ),
            _FakeHTTPResp(b"\x89PNG\r\n\x1a\nFAKEPNG"),
        ]
        with mock.patch("urllib.request.urlopen", side_effect=responses), tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "core.png"
            res = cinema_api.generate_image_runway("radar core", out_path=out_path, poll_timeout_sec=10.0)
            self.assertTrue(res["ok"])
            self.assertEqual(res["credits"], 5)
            self.assertTrue(out_path.is_file())
        self.assertEqual(cinema_api.budget_status()["spent_credits"], 5)

    def test_generate_video_runway_rejects_failed_task(self) -> None:
        responses = [
            _FakeHTTPResp(json.dumps({"id": "task_fail"}).encode("utf-8")),
            _FakeHTTPResp(json.dumps({"id": "task_fail", "status": "FAILED", "failure": "insufficient credits"}).encode("utf-8")),
        ]
        with mock.patch("urllib.request.urlopen", side_effect=responses), tempfile.TemporaryDirectory() as td:
            src_img = Path(td) / "src.png"
            src_img.write_bytes(b"\x89PNG\r\n\x1a\n")
            with self.assertRaises(cinema_api.CinemaApiError) as ctx:
                cinema_api.generate_video_runway(src_img, "slow dolly-in", out_path=Path(td) / "out.mp4", poll_timeout_sec=10.0)
            self.assertIn("insufficient credits", str(ctx.exception))
        self.assertEqual(cinema_api.budget_status()["spent_credits"], 0)

    def test_batch_precheck_refuses_whole_series_before_any_call(self) -> None:
        with mock.patch.dict(os.environ, {"DUP_CINEMA_DAILY_CREDITS": "20"}), mock.patch("urllib.request.urlopen") as up:
            with tempfile.TemporaryDirectory() as td:
                with self.assertRaises(cinema_api.CinemaApiError):
                    cinema_api.generate_batch_runway(
                        ["a", "b", "c"], topic="DUP", out_dir=Path(td), make_video=True
                    )
            up.assert_not_called()

    def test_corrupt_budget_file_fails_closed(self) -> None:
        cinema_api.BUDGET_FILE.write_text("{not json", encoding="utf-8")
        with self.assertRaises(cinema_api.CinemaApiError):
            cinema_api.budget_status()


if __name__ == "__main__":
    unittest.main()
