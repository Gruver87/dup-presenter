"""QA must vouch for the exact MP4 that reaches TikTok (SHA-256 + size), and verification must be audited."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import media_qa as mq  # noqa: E402
import tiktok_uploader as tu  # noqa: E402


def _write_report(mp4: Path, **overrides) -> None:
    report = {
        "ok": True,
        "hard_fails": 0,
        "mp4": mp4.name,
        "bytes": mp4.stat().st_size,
        "sha256": mq.file_sha256(mp4),
    }
    report.update(overrides)
    mq.qa_report_path(mp4).write_text(json.dumps(report), encoding="utf-8")


class QaBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.mp4 = self.dir / "film.mp4"
        self.mp4.write_bytes(b"\x00" * 4096 + b"film")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_matching_passed_report_is_accepted(self) -> None:
        _write_report(self.mp4)
        self.assertIsNone(mq.qa_binding_error(self.mp4))

    def test_missing_report_is_refused(self) -> None:
        self.assertIn("no media QA report", mq.qa_binding_error(self.mp4))

    def test_unreadable_report_is_refused(self) -> None:
        mq.qa_report_path(self.mp4).write_text("{not json", encoding="utf-8")
        self.assertIn("unreadable", mq.qa_binding_error(self.mp4))

    def test_report_without_sha256_is_refused(self) -> None:
        report = {"ok": True, "hard_fails": 0, "bytes": self.mp4.stat().st_size}
        mq.qa_report_path(self.mp4).write_text(json.dumps(report), encoding="utf-8")
        self.assertIn("has no sha256", mq.qa_binding_error(self.mp4))

    def test_size_mismatch_is_refused(self) -> None:
        _write_report(self.mp4, bytes=1)
        self.assertIn("describes 1 bytes", mq.qa_binding_error(self.mp4))

    def test_same_size_different_content_is_refused(self) -> None:
        _write_report(self.mp4)
        self.mp4.write_bytes(b"\x01" * 4096 + b"film")  # same length, different bytes
        self.assertIn("sha256 mismatch", mq.qa_binding_error(self.mp4))

    def test_failed_qa_is_refused_even_when_bound(self) -> None:
        _write_report(self.mp4, ok=False, hard_fails=1)
        self.assertIn("media QA failed", mq.qa_binding_error(self.mp4))


class TikTokGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.mp4 = self.dir / "film.mp4"
        self.mp4.write_bytes(b"\x00" * 4096)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_unqa_file_is_refused_before_any_network_or_token_call(self) -> None:
        with mock.patch.object(tu, "ensure_access_token", side_effect=AssertionError("token call")), \
                mock.patch.object(tu, "tiktok_status", side_effect=AssertionError("status call")):
            res = tu.tiktok_publish(self.mp4, dry_run=True)
        self.assertFalse(res["ok"])
        self.assertEqual(res["gate"], "media_qa")
        self.assertIn("no media QA report", res["error"])

    def test_bound_file_passes_the_gate_in_dry_run(self) -> None:
        _write_report(self.mp4)
        with mock.patch.object(tu, "tiktok_status", return_value={"ok": True}):
            res = tu.tiktok_publish(self.mp4, dry_run=True)
        self.assertTrue(res["ok"])
        self.assertTrue(res["dry_run"])


class VerificationAuditTests(unittest.TestCase):
    def test_verification_is_appended_as_its_own_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "audit.jsonl"
            with mock.patch.object(tu, "AUDIT_LOG", log):
                tu._record_verification(
                    "verification",
                    {"publish_id": "v_inbox_file~v2.1", "status": "SEND_TO_USER_INBOX", "verified": True, "polls": 3},
                )
                tu._record_verification(
                    "status_check",
                    {"publish_id": "v_inbox_file~v2.2", "status": "FAILED", "verified": False, "fail_reason": "bad"},
                )
            rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([r["event"] for r in rows], ["verification", "status_check"])
        self.assertTrue(rows[0]["verified"])
        self.assertEqual(rows[0]["polls"], 3)
        self.assertEqual(rows[1]["fail_reason"], "bad")
        self.assertFalse(rows[1]["verified"])


if __name__ == "__main__":
    unittest.main()
