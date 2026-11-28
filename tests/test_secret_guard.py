"""Unit tests for scripts/secret_guard.py (fail-closed secret egress guard)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import secret_guard  # noqa: E402

TEST_MAC_KEY = b"\x11" * 32
_KEY_PATCH = mock.patch.object(secret_guard, "_approval_mac_key", lambda create: TEST_MAC_KEY)


def setUpModule() -> None:
    _KEY_PATCH.start()


def tearDownModule() -> None:
    _KEY_PATCH.stop()


class TestSecretGuard(unittest.TestCase):
    def test_blocks_env_secret_in_prompt_text(self) -> None:
        with mock.patch.dict(os.environ, {"MY_PRIVATE_SECRET": "super_secret_value_12345"}, clear=False):
            with self.assertRaises(secret_guard.SecretLeakError):
                secret_guard.assert_no_secrets_in_text("please draw super_secret_value_12345")

    def test_blocks_known_secret_patterns(self) -> None:
        for sample in (
            "-----BEGIN RSA PRIVATE KEY-----\nabc",
            "use sk-proj-abcdefghijklmnopqrstuvwxyz12345",
            "token ghp_1234567890abcdefghij1234567890",
            "aws AKIAIOSFODNN7EXAMPLE",
            "runway key_0123456789abcdef0123456789abcdef",
        ):
            with self.assertRaises(secret_guard.SecretLeakError):
                secret_guard.assert_no_secrets_in_text(sample)

    def test_blocks_secret_in_outbound_url(self) -> None:
        with mock.patch.dict(os.environ, {"RUNWAYML_API_SECRET": "rw_secret_9876543210"}, clear=False):
            req = urllib.request.Request("https://evil.example.com/steal?k=rw_secret_9876543210")
            with self.assertRaises(secret_guard.SecretLeakError):
                secret_guard.inspect_outbound_request(req)

    def test_blocks_secret_in_outbound_body(self) -> None:
        with mock.patch.dict(os.environ, {"DUP_LLM_API_KEY": "llm_secret_abcdef123456"}, clear=False):
            req = urllib.request.Request(
                "https://api.dev.runwayml.com/v1/text_to_image",
                data=b'{"promptText": "hello llm_secret_abcdef123456"}',
                method="POST",
            )
            with self.assertRaises(secret_guard.SecretLeakError):
                secret_guard.inspect_outbound_request(req)

    def test_blocks_runway_key_sent_to_wrong_host(self) -> None:
        with mock.patch.dict(os.environ, {"RUNWAYML_API_SECRET": "rw_secret_9876543210"}, clear=False):
            req = urllib.request.Request(
                "https://evil.example.com/v1/text_to_image",
                headers={"Authorization": "Bearer rw_secret_9876543210"},
            )
            with self.assertRaises(secret_guard.SecretLeakError):
                secret_guard.inspect_outbound_request(req)

    def test_runway_key_to_official_host_requires_manual_approval(self) -> None:
        with tempfile.TemporaryDirectory() as td, mock.patch.object(
            secret_guard, "APPROVALS_FILE", Path(td) / "egress_approvals.json"
        ), mock.patch.dict(os.environ, {"RUNWAYML_API_SECRET": "rw_secret_9876543210"}, clear=False):
            req = urllib.request.Request(
                "https://api.dev.runwayml.com/v1/text_to_image",
                data=b'{"promptText": "cinematic dark observatory"}',
                headers={"Authorization": "Bearer rw_secret_9876543210"},
                method="POST",
            )
            with self.assertRaises(secret_guard.EgressApprovalRequired):
                secret_guard.inspect_outbound_request(req)

    def test_blocks_plain_http_to_remote_host(self) -> None:
        req = urllib.request.Request("http://api.dev.runwayml.com/v1/tasks")
        with self.assertRaises(secret_guard.OutboundThreatError):
            secret_guard.inspect_outbound_request(req)

    def test_blocks_unlisted_shady_and_phishing_domains(self) -> None:
        bad_urls = [
            "https://xn--runwaym1-9za.com/v1",
            "https://185.10.20.30/steal",
            "https://169.254.169.254/latest/meta-data/",
            "https://bit.ly/3xyz",
            "https://free-casino-slots.com/bonus",
            "https://api.dev.runwayml.com@evil.com/v1",
            "https://evil-site.tk/payload",
        ]
        for url in bad_urls:
            with self.subTest(url=url):
                with self.assertRaises(secret_guard.OutboundThreatError):
                    secret_guard.inspect_outbound_request(urllib.request.Request(url))

    def test_unlisted_site_blocked_for_write_but_readable_anonymously(self) -> None:
        with mock.patch.dict(os.environ, {"DUP_OPEN_READ": "1"}):
            secret_guard.inspect_outbound_request(urllib.request.Request("https://random-untrusted-site.com/page"))
            with self.assertRaises(secret_guard.OutboundThreatError):
                secret_guard.inspect_outbound_request(
                    urllib.request.Request("https://random-untrusted-site.com/page", data=b"{}", method="POST")
                )

    def test_system_path_var_is_not_treated_as_secret(self) -> None:
        with mock.patch.dict(os.environ, {"PATH": "C:\\Windows\\system32;C:\\Tools\\bin_long_value"}):
            self.assertNotIn("PATH", secret_guard.collect_secret_env())
            self.assertEqual(
                secret_guard.redact_secrets("open C:\\Windows\\system32 now"),
                "open C:\\Windows\\system32 now",
            )

    def test_real_secret_names_are_detected(self) -> None:
        self.assertTrue(secret_guard._is_secret_env_name("RUNWAYML_API_SECRET"))
        self.assertTrue(secret_guard._is_secret_env_name("DUP_LLM_API_KEY"))
        self.assertTrue(secret_guard._is_secret_env_name("GITHUB_TOKEN"))
        self.assertFalse(secret_guard._is_secret_env_name("PATH"))
        self.assertFalse(secret_guard._is_secret_env_name("DUP_WORKSPACE_ROOTS"))

    def test_allows_official_verified_domains(self) -> None:
        good_urls = [
            "https://api.dev.runwayml.com/v1/organization",
            "https://dnznrvs05pmza.cloudfront.net/output.mp4",
            "https://google.serper.dev/search",
            "https://api.github.com/repos/Gruver87/dup-protocol",
            "http://127.0.0.1:8787/api/status",
        ]
        for url in good_urls:
            with self.subTest(url=url):
                secret_guard.inspect_outbound_request(urllib.request.Request(url))

    def test_allows_localhost_http(self) -> None:
        req = urllib.request.Request("http://127.0.0.1:8787/api/status")
        secret_guard.inspect_outbound_request(req)

    def test_loopback_post_body_needs_no_approval(self) -> None:
        # Local Ollama chat is a POST with a body; it never leaves the machine, so no manual approval.
        body = json.dumps({"model": "qwen2.5:14b", "messages": [{"role": "user", "content": "2+2"}]}).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with mock.patch.dict(os.environ, {"RUNWAYML_API_SECRET": "rw_secret_9876543210"}, clear=False):
            secret_guard.inspect_outbound_request(req)

    def test_loopback_still_refuses_secret_in_body_or_auth(self) -> None:
        with mock.patch.dict(os.environ, {"RUNWAYML_API_SECRET": "rw_secret_9876543210"}, clear=False):
            body_req = urllib.request.Request(
                "http://127.0.0.1:11434/api/chat",
                data=b'{"prompt": "rw_secret_9876543210"}',
                method="POST",
            )
            with self.assertRaises(secret_guard.SecretLeakError):
                secret_guard.inspect_outbound_request(body_req)
            auth_req = urllib.request.Request(
                "http://127.0.0.1:8787/api/x",
                headers={"Authorization": "Bearer rw_secret_9876543210"},
            )
            with self.assertRaises(secret_guard.SecretLeakError):
                secret_guard.inspect_outbound_request(auth_req)

    def test_redact_secrets_scrubs_nested_payload(self) -> None:
        with mock.patch.dict(os.environ, {"RUNWAYML_API_SECRET": "rw_secret_9876543210"}, clear=False):
            scrubbed = secret_guard.redact_secrets(
                {"ok": False, "error": "failed with rw_secret_9876543210 and ghp_1234567890abcdefghij1234567890"}
            )
            self.assertNotIn("rw_secret_9876543210", scrubbed["error"])
            self.assertNotIn("ghp_1234567890abcdefghij1234567890", scrubbed["error"])
            self.assertIn("[REDACTED:RUNWAYML_API_SECRET]", scrubbed["error"])


class TestManualEgressApproval(unittest.TestCase):
    RUNWAY_HOST = "api.dev.runwayml.com"

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self._p = mock.patch.object(secret_guard, "APPROVALS_FILE", Path(self._td.name) / "egress_approvals.json")
        self._p.start()
        self._env = mock.patch.dict(os.environ, {"RUNWAYML_API_SECRET": "rw_secret_9876543210"}, clear=False)
        self._env.start()

    def tearDown(self) -> None:
        self._env.stop()
        self._p.stop()
        self._td.cleanup()

    def _auth_req(self, host: str = RUNWAY_HOST) -> urllib.request.Request:
        return urllib.request.Request(
            f"https://{host}/v1/organization",
            headers={"Authorization": "Bearer something_harmless_123"},
        )

    def _post_req(self, host: str = RUNWAY_HOST) -> urllib.request.Request:
        return urllib.request.Request(f"https://{host}/v1/x", data=b'{"a": 1}', method="POST")

    def test_auth_without_approval_is_refused(self) -> None:
        with self.assertRaises(secret_guard.EgressApprovalRequired):
            secret_guard.inspect_outbound_request(self._auth_req())

    def test_body_without_approval_is_refused(self) -> None:
        with self.assertRaises(secret_guard.EgressApprovalRequired):
            secret_guard.inspect_outbound_request(self._post_req())

    def test_anonymous_get_needs_no_approval(self) -> None:
        with mock.patch.dict(os.environ, {"DUP_OPEN_READ": "1"}):
            secret_guard.inspect_outbound_request(urllib.request.Request("https://docs.python.org/3/"))

    def test_get_without_credentials_or_data_needs_no_approval_when_open_read_off(self) -> None:
        with mock.patch.dict(os.environ, {"DUP_OPEN_READ": "0"}):
            secret_guard.inspect_outbound_request(urllib.request.Request(f"https://{self.RUNWAY_HOST}/v1/status"))

    def test_grant_allows_limited_uses_then_refuses(self) -> None:
        secret_guard.grant_egress_approval(
            self.RUNWAY_HOST, ttl_min=5, uses=2, confirm_text=f"APPROVE {self.RUNWAY_HOST}"
        )
        secret_guard.inspect_outbound_request(self._auth_req())
        secret_guard.inspect_outbound_request(self._post_req())
        with self.assertRaises(secret_guard.EgressApprovalRequired):
            secret_guard.inspect_outbound_request(self._auth_req())

    def test_grant_is_host_bound(self) -> None:
        secret_guard.grant_egress_approval(
            self.RUNWAY_HOST, ttl_min=5, uses=5, confirm_text=f"APPROVE {self.RUNWAY_HOST}"
        )
        with self.assertRaises(secret_guard.EgressApprovalRequired):
            secret_guard.inspect_outbound_request(self._post_req("api.openai.com"))

    def test_expired_grant_is_refused(self) -> None:
        rec = secret_guard.grant_egress_approval(
            self.RUNWAY_HOST, ttl_min=5, uses=5, confirm_text=f"APPROVE {self.RUNWAY_HOST}"
        )
        data = secret_guard._load_approvals_locked()
        for r in data:
            if r["id"] == rec["id"]:
                r["expires_ts"] = int(time.time()) - 1
        secret_guard._save_approvals_locked(data)
        with self.assertRaises(secret_guard.EgressApprovalRequired):
            secret_guard.inspect_outbound_request(self._auth_req())

    def test_wrong_confirmation_text_is_refused(self) -> None:
        with self.assertRaises(secret_guard.EgressApprovalRequired):
            secret_guard.grant_egress_approval(self.RUNWAY_HOST, ttl_min=5, uses=5, confirm_text="yes")
        self.assertEqual(secret_guard.list_egress_approvals(), [])

    def test_cannot_grant_unverified_host(self) -> None:
        with self.assertRaises(secret_guard.EgressApprovalRequired):
            secret_guard.grant_egress_approval(
                "random-untrusted-site.com", ttl_min=5, uses=5, confirm_text="APPROVE random-untrusted-site.com"
            )
        with self.assertRaises(secret_guard.EgressApprovalRequired):
            secret_guard.grant_egress_approval(
                "free-casino-slots.com", ttl_min=5, uses=5, confirm_text="APPROVE free-casino-slots.com"
            )

    def test_secret_in_body_is_blocked_even_with_approval(self) -> None:
        secret_guard.grant_egress_approval(
            self.RUNWAY_HOST, ttl_min=5, uses=5, confirm_text=f"APPROVE {self.RUNWAY_HOST}"
        )
        req = urllib.request.Request(
            f"https://{self.RUNWAY_HOST}/v1/x",
            data=b'{"leak": "rw_secret_9876543210"}',
            method="POST",
        )
        with self.assertRaises(secret_guard.SecretLeakError):
            secret_guard.inspect_outbound_request(req)

    def test_revoke_removes_grant(self) -> None:
        rec = secret_guard.grant_egress_approval(
            self.RUNWAY_HOST, ttl_min=5, uses=5, confirm_text=f"APPROVE {self.RUNWAY_HOST}"
        )
        self.assertTrue(secret_guard.revoke_egress_approval(rec["id"]))
        with self.assertRaises(secret_guard.EgressApprovalRequired):
            secret_guard.inspect_outbound_request(self._auth_req())

    def test_corrupt_approvals_file_fails_closed(self) -> None:
        secret_guard.APPROVALS_FILE.write_text("{not json", encoding="utf-8")
        with self.assertRaises(secret_guard.EgressApprovalRequired):
            secret_guard.inspect_outbound_request(self._auth_req())


class TestKeyBindingsRedirectsAndHttpx(unittest.TestCase):
    RUNWAY = "api.dev.runwayml.com"
    OPENAI = "api.openai.com"
    TIKTOK = "open.tiktokapis.com"

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self._p = mock.patch.object(secret_guard, "APPROVALS_FILE", Path(self._td.name) / "egress_approvals.json")
        self._p.start()
        self._env = mock.patch.dict(
            os.environ,
            {
                "RUNWAYML_API_SECRET": "rw_secret_9876543210",
                "SERPER_API_KEY": "serper_secret_123456",
                "TIKTOK_CLIENT_SECRET": "tt_client_secret_123",
                "MY_CUSTOM_TOKEN": "custom_secret_value_12345",
                "DUP_LLM_BASE_URL": "https://api.openai.com/v1",
            },
            clear=False,
        )
        self._env.start()
        secret_guard.install_egress_guard()

    def tearDown(self) -> None:
        self._env.stop()
        self._p.stop()
        self._td.cleanup()

    def _grant(self, host: str) -> None:
        secret_guard.grant_egress_approval(host, ttl_min=5, uses=50, confirm_text=f"APPROVE {host}")

    def test_key_bound_to_other_host_refused_even_with_approval(self) -> None:
        self._grant(self.OPENAI)
        req = urllib.request.Request(
            f"https://{self.OPENAI}/v1/x", headers={"Authorization": "Bearer serper_secret_123456"}
        )
        with self.assertRaises(secret_guard.SecretLeakError):
            secret_guard.inspect_outbound_request(req)

    def test_unbound_secret_name_is_never_transmitted(self) -> None:
        self._grant(self.RUNWAY)
        req = urllib.request.Request(
            f"https://{self.RUNWAY}/v1/x", headers={"Authorization": "Bearer custom_secret_value_12345"}
        )
        with self.assertRaises(secret_guard.SecretLeakError) as ctx:
            secret_guard.inspect_outbound_request(req)
        self.assertNotIsInstance(ctx.exception, secret_guard.EgressApprovalRequired)

    def test_tiktok_client_secret_allowed_in_body_only_to_tiktok(self) -> None:
        self._grant(self.TIKTOK)
        ok = urllib.request.Request(
            f"https://{self.TIKTOK}/v2/oauth/token/",
            data=b"client_secret=tt_client_secret_123&grant_type=refresh_token",
            method="POST",
        )
        secret_guard.inspect_outbound_request(ok)
        self._grant(self.OPENAI)
        leak = urllib.request.Request(
            f"https://{self.OPENAI}/v1/x", data=b"client_secret=tt_client_secret_123", method="POST"
        )
        with self.assertRaises(secret_guard.SecretLeakError):
            secret_guard.inspect_outbound_request(leak)

    def test_runway_key_in_body_refused_even_with_approval(self) -> None:
        self._grant(self.RUNWAY)
        req = urllib.request.Request(
            f"https://{self.RUNWAY}/v1/x", data=b'{"k": "rw_secret_9876543210"}', method="POST"
        )
        with self.assertRaises(secret_guard.SecretLeakError):
            secret_guard.inspect_outbound_request(req)

    def test_redirect_with_credentials_to_other_host_refused(self) -> None:
        handler = secret_guard._GuardedRedirectHandler()
        req = urllib.request.Request(f"https://{self.RUNWAY}/v1/x", headers={"Authorization": "Bearer abc123xyz"})
        with self.assertRaises(secret_guard.OutboundThreatError):
            handler.redirect_request(req, None, 302, "Found", {}, "https://evil-site.example.net/steal")

    def test_redirect_same_host_is_reinspected_for_approval(self) -> None:
        handler = secret_guard._GuardedRedirectHandler()
        req = urllib.request.Request(f"https://{self.RUNWAY}/v1/x", headers={"Authorization": "Bearer abc123xyz"})
        with self.assertRaises(secret_guard.EgressApprovalRequired):
            handler.redirect_request(req, None, 302, "Found", {}, f"https://{self.RUNWAY}/v1/y")

    def test_httpx_request_with_key_needs_approval_before_network(self) -> None:
        import httpx

        with httpx.Client(timeout=5.0) as client:
            with self.assertRaises(secret_guard.EgressApprovalRequired):
                client.send(httpx.Request("GET", f"https://{self.RUNWAY}/v1/x", headers={"Authorization": "Bearer abc123xyz"}))

    def test_httpx_body_with_foreign_key_blocked(self) -> None:
        import httpx

        with httpx.Client(timeout=5.0) as client:
            with self.assertRaises(secret_guard.SecretLeakError):
                client.send(httpx.Request("POST", "https://docs.python.org/x", content=b"serper_secret_123456"))

    def test_cloudfront_cannot_be_granted_for_credentials(self) -> None:
        with self.assertRaises(secret_guard.EgressApprovalRequired):
            secret_guard.grant_egress_approval(
                "d123abc.cloudfront.net", ttl_min=5, uses=5, confirm_text="APPROVE d123abc.cloudfront.net"
            )

    def test_guard_status_reports_both_clients(self) -> None:
        st = secret_guard.guard_status()
        self.assertTrue(st["urllib_guard"])
        self.assertTrue(st["httpx_guard"])
        self.assertTrue(st["redirect_hops_inspected"])


class TestGrantDedup(unittest.TestCase):
    HOST = "api.dev.runwayml.com"

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self._p = mock.patch.object(secret_guard, "APPROVALS_FILE", Path(self._td.name) / "egress_approvals.json")
        self._p.start()

    def tearDown(self) -> None:
        self._p.stop()
        self._td.cleanup()

    def test_regrant_does_not_duplicate_or_refill_uses(self) -> None:
        first = secret_guard.grant_egress_approval(self.HOST, ttl_min=60, uses=3, confirm_text=f"APPROVE {self.HOST}")
        for _ in range(2):
            secret_guard.consume_egress_approval(self.HOST)
        again = secret_guard.grant_egress_approval(self.HOST, ttl_min=60, uses=500, confirm_text=f"APPROVE {self.HOST}")
        self.assertEqual(again["id"], first["id"])
        active = secret_guard.list_egress_approvals()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["uses_left"], 1)

    def test_grant_after_expiry_creates_new_record(self) -> None:
        first = secret_guard.grant_egress_approval(self.HOST, ttl_min=5, uses=5, confirm_text=f"APPROVE {self.HOST}")
        data = secret_guard._load_approvals_locked()
        for r in data:
            if r["id"] == first["id"]:
                r["expires_ts"] = int(time.time()) - 1
        secret_guard._save_approvals_locked(data)
        second = secret_guard.grant_egress_approval(self.HOST, ttl_min=5, uses=5, confirm_text=f"APPROVE {self.HOST}")
        self.assertNotEqual(second["id"], first["id"])
        self.assertEqual(len(secret_guard.list_egress_approvals()), 1)


class TestOnDemandRenewal(unittest.TestCase):
    HOST = "api.dev.runwayml.com"

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self._p = mock.patch.object(secret_guard, "APPROVALS_FILE", Path(self._td.name) / "egress_approvals.json")
        self._p.start()

    def tearDown(self) -> None:
        secret_guard.set_approval_renewer(None)
        self._p.stop()
        self._td.cleanup()

    def _granting_renewer(self, calls: list[str]):
        def renew(host: str) -> bool:
            calls.append(host)
            secret_guard.grant_egress_approval(host, ttl_min=60, uses=5, confirm_text=f"APPROVE {host}")
            return True

        return renew

    def test_without_renewer_missing_grant_is_refused(self) -> None:
        with self.assertRaises(secret_guard.EgressApprovalRequired):
            secret_guard.consume_egress_approval(self.HOST)

    def test_renewer_grants_on_demand(self) -> None:
        calls: list[str] = []
        secret_guard.set_approval_renewer(self._granting_renewer(calls))
        spent = secret_guard.consume_egress_approval(self.HOST)
        self.assertEqual(spent["uses_left"], 4)
        self.assertEqual(calls, [self.HOST])

    def test_renewer_not_called_while_grant_is_valid(self) -> None:
        secret_guard.grant_egress_approval(self.HOST, ttl_min=60, uses=5, confirm_text=f"APPROVE {self.HOST}")
        calls: list[str] = []
        secret_guard.set_approval_renewer(self._granting_renewer(calls))
        secret_guard.consume_egress_approval(self.HOST)
        self.assertEqual(calls, [])

    def test_renewer_refusal_keeps_block(self) -> None:
        secret_guard.set_approval_renewer(lambda host: False)
        with self.assertRaises(secret_guard.EgressApprovalRequired):
            secret_guard.consume_egress_approval(self.HOST)
        self.assertIsNone(secret_guard.ensure_egress_approval(self.HOST))

    def test_renewer_error_fails_closed(self) -> None:
        def broken(host: str) -> bool:
            raise RuntimeError("boom")

        secret_guard.set_approval_renewer(broken)
        with self.assertRaises(secret_guard.EgressApprovalRequired):
            secret_guard.consume_egress_approval(self.HOST)

    def test_ensure_returns_grant_after_renewal(self) -> None:
        secret_guard.set_approval_renewer(self._granting_renewer([]))
        rec = secret_guard.ensure_egress_approval(self.HOST)
        self.assertIsNotNone(rec)
        self.assertEqual(rec["uses_left"], 5)


class TestHttpxUnreadBodies(unittest.TestCase):
    """Redirect hops arrive with an unread stream; bodiless hops must be inspected, not refused."""

    def _unread(self, method: str, **kw):
        import httpx

        return httpx.Request(method, "https://upload.wikimedia.org/a.png", content=iter([]), **kw)

    def test_bodiless_get_redirect_hop_is_inspected_and_allowed(self) -> None:
        req = self._unread("GET")
        secret_guard._inspect_httpx_request(req)  # must not raise: no secret, empty body
        self.assertEqual(req.read(), b"")

    def test_get_with_secret_in_unread_body_is_blocked(self) -> None:
        import httpx

        req = httpx.Request("GET", "https://upload.wikimedia.org/a.png", content=iter([b"sk-" + b"a" * 30]))
        with self.assertRaises(secret_guard.OutboundThreatError):
            secret_guard._inspect_httpx_request(req)

    def test_post_with_unread_stream_is_still_refused(self) -> None:
        req = self._unread("POST")
        with self.assertRaises(secret_guard.SecretLeakError):
            secret_guard._inspect_httpx_request(req)


class TestApprovalsSignature(unittest.TestCase):
    HOST = "api.dev.runwayml.com"

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self._p = mock.patch.object(secret_guard, "APPROVALS_FILE", Path(self._td.name) / "egress_approvals.json")
        self._p.start()
        secret_guard.set_approval_renewer(None)

    def tearDown(self) -> None:
        self._p.stop()
        self._td.cleanup()

    def _grant(self) -> dict:
        return secret_guard.grant_egress_approval(self.HOST, ttl_min=5, uses=5, confirm_text=f"APPROVE {self.HOST}")

    def _doc(self) -> dict:
        return json.loads(secret_guard.APPROVALS_FILE.read_text(encoding="utf-8"))

    def test_file_is_signed_and_round_trips(self) -> None:
        rec = self._grant()
        doc = self._doc()
        self.assertEqual(doc["format"], secret_guard.APPROVALS_FORMAT)
        self.assertEqual(doc["mac"], secret_guard._approvals_mac(TEST_MAC_KEY, doc["records"]))
        self.assertEqual(secret_guard.active_approval(self.HOST)["id"], rec["id"])

    def test_edited_uses_left_blocks_everything(self) -> None:
        self._grant()
        doc = self._doc()
        doc["records"][0]["uses_left"] = 500
        secret_guard.APPROVALS_FILE.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaises(secret_guard.EgressApprovalRequired):
            secret_guard.consume_egress_approval(self.HOST)
        with self.assertRaises(secret_guard.EgressApprovalRequired):
            secret_guard.list_egress_approvals()

    def test_forged_file_signed_with_other_key_is_refused(self) -> None:
        records = [{"id": "f" * 16, "host": self.HOST, "created_ts": 1, "expires_ts": int(time.time()) + 600,
                    "uses_left": 500, "granted_by": "manual-cli"}]
        forged = {"format": secret_guard.APPROVALS_FORMAT, "records": records,
                  "mac": secret_guard._approvals_mac(b"\x99" * 32, records)}
        secret_guard.APPROVALS_FILE.write_text(json.dumps(forged), encoding="utf-8")
        with self.assertRaises(secret_guard.EgressApprovalRequired):
            secret_guard.active_approval(self.HOST)

    def test_legacy_unsigned_list_grants_nothing(self) -> None:
        legacy = [{"id": "a" * 16, "host": self.HOST, "created_ts": 1, "expires_ts": int(time.time()) + 600,
                   "uses_left": 500, "granted_by": "manual-cli"}]
        secret_guard.APPROVALS_FILE.write_text(json.dumps(legacy), encoding="utf-8")
        self.assertIsNone(secret_guard.active_approval(self.HOST))
        with self.assertRaises(secret_guard.EgressApprovalRequired):
            secret_guard.consume_egress_approval(self.HOST)
        rec = self._grant()
        self.assertEqual(self._doc()["records"][0]["id"], rec["id"])
        self.assertEqual(len(self._doc()["records"]), 1)

    def test_reset_clears_tampered_file(self) -> None:
        self._grant()
        doc = self._doc()
        doc["mac"] = "0" * 64
        secret_guard.APPROVALS_FILE.write_text(json.dumps(doc), encoding="utf-8")
        status = secret_guard.guard_status()
        self.assertIsNone(status["active_approvals"])
        self.assertIn("Подпись", status["approvals_error"])
        secret_guard.reset_egress_approvals()
        self.assertEqual(secret_guard.list_egress_approvals(), [])
        self.assertEqual(secret_guard.guard_status()["active_approvals"], 0)

    def test_signed_file_without_key_fails_closed(self) -> None:
        self._grant()
        with mock.patch.object(secret_guard, "get_secret", return_value=None), \
                mock.patch.object(secret_guard, "_approval_mac_key", _REAL_MAC_KEY):
            with self.assertRaises(secret_guard.EgressApprovalRequired):
                secret_guard.active_approval(self.HOST)

    def test_store_error_and_bad_key_format_fail_closed(self) -> None:
        with mock.patch.object(secret_guard, "_approval_mac_key", _REAL_MAC_KEY):
            with mock.patch.object(secret_guard, "get_secret", side_effect=secret_guard.CredStoreError("boom")):
                with self.assertRaises(secret_guard.EgressApprovalRequired):
                    self._grant()
            with mock.patch.object(secret_guard, "get_secret", return_value="not-hex"):
                with self.assertRaises(secret_guard.EgressApprovalRequired):
                    self._grant()

    def test_key_is_created_once_in_store(self) -> None:
        store: dict[str, str] = {}
        with mock.patch.object(secret_guard, "_approval_mac_key", _REAL_MAC_KEY), \
                mock.patch.object(secret_guard, "get_secret", side_effect=store.get), \
                mock.patch.object(secret_guard, "set_secret", side_effect=store.__setitem__) as set_mock:
            self._grant()
            secret_guard.consume_egress_approval(self.HOST)
            self.assertEqual(set_mock.call_count, 1)
            self.assertRegex(store[secret_guard.APPROVALS_MAC_KEY_NAME], r"^[0-9a-f]{64}$")
            self.assertEqual(secret_guard.active_approval(self.HOST)["uses_left"], 4)


_REAL_MAC_KEY = secret_guard._approval_mac_key


if __name__ == "__main__":
    unittest.main()
