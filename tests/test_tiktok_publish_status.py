"""Item 6: an upload is verified only when TikTok reports a terminal OK state for its publish_id."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import tiktok_uploader as tu  # noqa: E402


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def clock(self) -> float:
        return self.now

    def sleep(self, sec: float) -> None:
        self.now += sec


def _scripted(states: list[str], fail_reason: str = ""):
    seq = list(states)
    calls: list[str] = []

    def fetch(pid: str) -> dict:
        calls.append(pid)
        st = seq.pop(0) if len(seq) > 1 else seq[0]
        return {"status": st, "fail_reason": fail_reason if st == "FAILED" else ""}

    return fetch, calls


class PollTests(unittest.TestCase):
    def test_processing_then_inbox_is_verified(self) -> None:
        clk = FakeClock()
        fetch, calls = _scripted(["PROCESSING_UPLOAD", "PROCESSING_UPLOAD", "SEND_TO_USER_INBOX"])
        res = tu.poll_publish_status("pid-1", fetch, wait_sec=60, poll_sec=5, sleep=clk.sleep, clock=clk.clock)
        self.assertTrue(res["verified"])
        self.assertTrue(res["ok"])
        self.assertEqual(res["status"], "SEND_TO_USER_INBOX")
        self.assertEqual(res["polls"], 3)
        self.assertEqual(calls, ["pid-1"] * 3)

    def test_failed_is_reported_with_reason_and_not_verified(self) -> None:
        clk = FakeClock()
        fetch, _ = _scripted(["PROCESSING_DOWNLOAD", "FAILED"], fail_reason="file_format_check_failed")
        res = tu.poll_publish_status("pid-2", fetch, wait_sec=60, poll_sec=5, sleep=clk.sleep, clock=clk.clock)
        self.assertFalse(res["verified"])
        self.assertEqual(res["status"], "FAILED")
        self.assertEqual(res["fail_reason"], "file_format_check_failed")

    def test_deadline_without_terminal_state_is_not_verified(self) -> None:
        clk = FakeClock()
        fetch, _ = _scripted(["PROCESSING_UPLOAD"])
        res = tu.poll_publish_status("pid-3", fetch, wait_sec=12, poll_sec=5, sleep=clk.sleep, clock=clk.clock)
        self.assertFalse(res["verified"], "a timeout must never be reported as success")
        self.assertIn("timeout", res["fail_reason"])

    def test_unknown_state_keeps_polling_until_deadline(self) -> None:
        clk = FakeClock()
        fetch, _ = _scripted(["SOMETHING_NEW"])
        res = tu.poll_publish_status("pid-4", fetch, wait_sec=10, poll_sec=5, sleep=clk.sleep, clock=clk.clock)
        self.assertFalse(res["verified"])
        self.assertEqual(res["status"], "SOMETHING_NEW")

    def test_empty_publish_id_is_refused(self) -> None:
        with self.assertRaises(tu.TikTokStatusError):
            tu.poll_publish_status("", lambda pid: {"status": "x"}, wait_sec=0)


class ParseTests(unittest.TestCase):
    def test_ok_response_parses(self) -> None:
        body = {"data": {"status": "SEND_TO_USER_INBOX"}, "error": {"code": "ok"}}
        self.assertEqual(tu._parse_publish_status(200, body)["status"], "SEND_TO_USER_INBOX")

    def test_http_error_raises(self) -> None:
        with self.assertRaises(tu.TikTokStatusError):
            tu._parse_publish_status(401, {}, "unauthorized")

    def test_api_error_code_raises(self) -> None:
        with self.assertRaises(tu.TikTokStatusError):
            tu._parse_publish_status(200, {"error": {"code": "publish_id_not_found"}})


if __name__ == "__main__":
    unittest.main()
