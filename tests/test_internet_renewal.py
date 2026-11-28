"""Internet toggle <-> egress approvals: on-demand renewal only while ON, OFF revokes every live grant."""

from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import console_server  # noqa: E402
import secret_guard  # noqa: E402

MANAGED = "api.dev.runwayml.com"
_KEY_PATCH = mock.patch.object(secret_guard, "_approval_mac_key", lambda create: b"\x22" * 32)


def setUpModule() -> None:
    _KEY_PATCH.start()


def tearDownModule() -> None:
    _KEY_PATCH.stop()


class InternetRenewalTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self._patches = [
            mock.patch.object(secret_guard, "APPROVALS_FILE", Path(self._td.name) / "egress_approvals.json"),
            mock.patch.object(console_server, "_internet_managed_hosts", return_value=[MANAGED]),
        ]
        for p in self._patches:
            p.start()
        self._orig_enabled = console_server.INTERNET_ENABLED

    def tearDown(self) -> None:
        console_server.INTERNET_ENABLED = self._orig_enabled
        for p in reversed(self._patches):
            p.stop()
        self._td.cleanup()

    def test_renewal_refused_when_toggle_off(self) -> None:
        console_server.INTERNET_ENABLED = False
        self.assertFalse(console_server._renew_internet_approval(MANAGED))
        self.assertEqual(secret_guard.list_egress_approvals(), [])

    def test_renewal_refused_for_unmanaged_host(self) -> None:
        console_server.INTERNET_ENABLED = True
        self.assertFalse(console_server._renew_internet_approval("api.openai.com"))
        self.assertEqual(secret_guard.list_egress_approvals(), [])

    def test_renewal_grants_managed_host_when_on(self) -> None:
        console_server.INTERNET_ENABLED = True
        self.assertTrue(console_server._renew_internet_approval(MANAGED))
        hosts = [r["host"] for r in secret_guard.list_egress_approvals()]
        self.assertEqual(hosts, [MANAGED])

    def _expire_in(self, seconds: int) -> None:
        data = secret_guard._load_approvals_locked()
        for r in data:
            r["expires_ts"] = int(time.time()) + seconds
        secret_guard._save_approvals_locked(data)

    def test_job_sync_replaces_grant_close_to_expiry(self) -> None:
        console_server.INTERNET_ENABLED = True
        console_server._sync_internet_approvals(True)
        first_id = secret_guard.list_egress_approvals()[0]["id"]
        self._expire_in(60)
        self.assertEqual(console_server._sync_internet_approvals(True, min_remaining_sec=900), [])
        active = secret_guard.list_egress_approvals()
        self.assertEqual(len(active), 1)
        self.assertNotEqual(active[0]["id"], first_id)

    def test_plain_sync_keeps_live_grant(self) -> None:
        console_server.INTERNET_ENABLED = True
        console_server._sync_internet_approvals(True)
        first_id = secret_guard.list_egress_approvals()[0]["id"]
        self._expire_in(60)
        console_server._sync_internet_approvals(True)
        self.assertEqual(secret_guard.list_egress_approvals()[0]["id"], first_id)

    def test_toggle_off_revokes_every_live_grant(self) -> None:
        console_server.INTERNET_ENABLED = True
        self.assertEqual(console_server._sync_internet_approvals(True), [])
        self.assertEqual(len(secret_guard.list_egress_approvals()), 1)
        console_server.INTERNET_ENABLED = False
        self.assertEqual(console_server._sync_internet_approvals(False), [])
        self.assertEqual(secret_guard.list_egress_approvals(), [])


if __name__ == "__main__":
    unittest.main()
