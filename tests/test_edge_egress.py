"""Edge TTS sends the voice text over aiohttp/WebSocket (outside the urllib/httpx guard): explicit egress gate."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_deck  # noqa: E402
import edge_engine  # noqa: E402
import secret_guard  # noqa: E402

HOST = edge_engine.EDGE_HOST
_KEY_PATCH = mock.patch.object(secret_guard, "_approval_mac_key", lambda create: b"\x33" * 32)


def setUpModule() -> None:
    _KEY_PATCH.start()


def tearDownModule() -> None:
    _KEY_PATCH.stop()


class EdgeEgressGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self._p = mock.patch.object(secret_guard, "APPROVALS_FILE", Path(self._td.name) / "egress_approvals.json")
        self._p.start()
        secret_guard.set_approval_renewer(None)

    def tearDown(self) -> None:
        secret_guard.set_approval_renewer(None)
        self._p.stop()
        self._td.cleanup()

    def _grant(self, uses: int = 5) -> None:
        secret_guard.grant_egress_approval(HOST, ttl_min=10, uses=uses, confirm_text=f"APPROVE {HOST}")

    def test_edge_host_is_grantable(self) -> None:
        self._grant()
        self.assertTrue(edge_engine.edge_allowed())

    def test_without_grant_edge_is_refused(self) -> None:
        self.assertFalse(edge_engine.edge_allowed())
        with self.assertRaises(edge_engine.EdgeEngineError):
            edge_engine.require_edge_egress("Привет, это проверка.")

    def test_grant_is_spent_per_request(self) -> None:
        self._grant(uses=2)
        edge_engine.require_edge_egress("Первый слайд.")
        self.assertEqual(secret_guard.list_egress_approvals()[0]["uses_left"], 1)

    def test_secret_in_text_is_refused_even_with_grant(self) -> None:
        self._grant(uses=2)
        with self.assertRaises(edge_engine.EdgeEngineError):
            edge_engine.require_edge_egress("ключ sk-proj-abcdefghijklmnopqrstuvwxyz12345")
        self.assertEqual(secret_guard.list_egress_approvals()[0]["uses_left"], 2)

    def test_synth_refuses_before_any_network(self) -> None:
        with mock.patch.object(edge_engine.asyncio, "run", side_effect=AssertionError("network must not start")):
            with self.assertRaises(edge_engine.EdgeEngineError):
                edge_engine.synth_edge_with_timings("dmitry", "Текст слайда.", 48000)


class DeckFallbackTests(unittest.TestCase):
    def test_no_grant_means_whole_deck_offline_voice(self) -> None:
        deck = {"lang": "ru", "voice": {"speaker": "dmitry", "fallback_speaker": "eugene"}, "slides": []}
        calls: list[tuple[str, str, str]] = []

        def fake_synth(d, a, b, voice_used):
            calls.append((a, b, voice_used))
            return {"voice_used": voice_used}

        with (
            mock.patch.object(build_deck, "edge_allowed", return_value=False),
            mock.patch.object(build_deck, "edge_available", side_effect=AssertionError("no probe without grant")),
            mock.patch.object(build_deck, "_synthesize_deck_with", side_effect=fake_synth),
        ):
            res = build_deck.synthesize_deck(deck)
        self.assertEqual(res["voice_used"], "eugene")
        self.assertEqual(calls, [("eugene", "eugene", "eugene")])


if __name__ == "__main__":
    unittest.main()
