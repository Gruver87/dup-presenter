"""Accepted-but-unconfirmed TikTok uploads are PENDING (exit 3), not failures, and can be re-checked from the audit log."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import tiktok_uploader as tu  # noqa: E402


def _log_rows(path: Path, *rows: dict) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


class PendingClassificationTests(unittest.TestCase):
    def test_real_non_terminal_status_is_pending(self) -> None:
        self.assertTrue(tu._is_pending({"verified": False, "status": "PROCESSING_UPLOAD"}))

    def test_terminal_and_unchecked_states_are_not_pending(self) -> None:
        self.assertFalse(tu._is_pending({"verified": True, "status": "SEND_TO_USER_INBOX"}))
        self.assertFalse(tu._is_pending({"verified": False, "status": "FAILED"}))
        self.assertFalse(tu._is_pending({"verified": False, "status": "NOT_CHECKED"}))

    def test_status_request_error_is_a_failure_not_pending(self) -> None:
        self.assertFalse(tu._is_pending({"verified": False, "ok": False, "error": "status HTTP 400"}))


class AuditBackedPendingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.log = Path(self._tmp.name) / "audit.jsonl"
        self._patch = mock.patch.object(tu, "AUDIT_LOG", self.log)
        self._patch.start()

    def tearDown(self) -> None:
        self._patch.stop()
        self._tmp.cleanup()

    def test_pending_ids_are_uploads_not_yet_settled(self) -> None:
        _log_rows(
            self.log,
            {"event": "upload", "publish_id": "A"},
            {"event": "upload", "publish_id": "B"},
            {"event": "upload", "publish_id": "C"},
            {"event": "verification", "publish_id": "A", "status": "SEND_TO_USER_INBOX", "verified": True},
            {"event": "verification", "publish_id": "C", "status": "FAILED", "verified": False},
        )
        self.assertEqual(tu.pending_publish_ids(), ["B"])

    def test_legacy_upload_rows_without_event_field_count_as_uploads(self) -> None:
        # Rows written before the event field existed: platform/mode/publish_id, no "event".
        _log_rows(self.log, {"platform": "tiktok", "mode": "inbox", "publish_id": "LEGACY", "mp4": "a.mp4"})
        self.assertEqual(tu.pending_publish_ids(), ["LEGACY"])

    def test_missing_log_means_nothing_pending(self) -> None:
        self.assertEqual(tu.pending_publish_ids(), [])

    def test_recheck_settles_confirmed_and_keeps_still_processing(self) -> None:
        _log_rows(
            self.log,
            {"event": "upload", "publish_id": "A"},
            {"event": "upload", "publish_id": "B"},
        )

        def fake_status(pid: str, wait_sec: float = 0.0) -> dict:
            if pid == "A":
                return {"publish_id": "A", "status": "SEND_TO_USER_INBOX", "verified": True, "polls": 1}
            return {"publish_id": "B", "status": "PROCESSING_UPLOAD", "verified": False, "polls": 1}

        with mock.patch.object(tu, "tiktok_publish_status", side_effect=fake_status):
            res = tu.recheck_pending(wait_sec=0)
        self.assertEqual(res["verified"], ["A"])
        self.assertEqual(res["still_pending"], ["B"])
        # The recheck itself is audited, and only A is now settled.
        self.assertEqual(tu.pending_publish_ids(), ["B"])


class ExitCodeTests(unittest.TestCase):
    def _run_main(self, result: dict, argv_extra: list[str]) -> int:
        with mock.patch.object(tu, "tiktok_publish", return_value=result), \
                mock.patch.object(sys, "argv", ["tiktok_uploader.py", *argv_extra]), \
                mock.patch("builtins.print"):
            return tu.main()

    def test_accepted_but_processing_exits_pending(self) -> None:
        code = self._run_main({"ok": True, "verified": False, "pending": True}, ["--mp4", "x.mp4"])
        self.assertEqual(code, tu.EXIT_PENDING)

    def test_verified_exits_zero(self) -> None:
        code = self._run_main({"ok": True, "verified": True, "pending": False}, ["--mp4", "x.mp4"])
        self.assertEqual(code, tu.EXIT_VERIFIED)

    def test_failed_upload_exits_one(self) -> None:
        code = self._run_main({"ok": False, "error": "boom"}, ["--mp4", "x.mp4"])
        self.assertEqual(code, tu.EXIT_FAILED)


if __name__ == "__main__":
    unittest.main()
