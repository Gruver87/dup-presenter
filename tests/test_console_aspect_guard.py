"""save-deck must not change a deck's aspect (and so its master) without explicit confirmation."""

from __future__ import annotations

import http.client
import json
import shutil
import sys
import threading
import unittest
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import console_server  # noqa: E402
from test_console_dashboard import _minimal_deck  # noqa: E402


class AspectGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.slug = f"aspect-test-{uuid.uuid4().hex[:8]}"
        self.deck_path = console_server.DECKS_DIR / f"{self.slug}.json"
        deck = _minimal_deck(self.slug)
        deck["aspect"] = "16:9"
        deck["width"], deck["height"] = 1920, 1080
        self.deck_path.write_text(json.dumps(deck, ensure_ascii=False, indent=2), encoding="utf-8")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), console_server.ConsoleHandler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.deck_path.unlink(missing_ok=True)
        shutil.rmtree(console_server.WORK_DIR / self.slug, ignore_errors=True)

    def _save(self, body: dict) -> tuple[int, dict]:
        # render=False: "Только сохранить". The default (render=true) starts a draft job, which these tests must not.
        body = {"render": False, **body}
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request("POST", "/api/save-deck", body=json.dumps(body).encode("utf-8"),
                         headers={"Content-Type": "application/json"})
            resp = conn.getresponse()
            return resp.status, json.loads(resp.read().decode("utf-8"))
        finally:
            conn.close()

    def _aspect_on_disk(self) -> str:
        return json.loads(self.deck_path.read_text(encoding="utf-8")).get("aspect")

    def test_aspect_change_without_confirmation_is_refused_and_nothing_is_written(self) -> None:
        before = self.deck_path.read_text(encoding="utf-8")
        status, data = self._save({"slug": self.slug, "aspect": "9:16"})
        self.assertEqual(status, 409)
        self.assertFalse(data["ok"])
        self.assertIn("не подтверждена", data["error"])
        self.assertEqual(self.deck_path.read_text(encoding="utf-8"), before)

    def test_same_aspect_saves_without_confirmation(self) -> None:
        status, data = self._save({"slug": self.slug, "aspect": "16:9"})
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(self._aspect_on_disk(), "16:9")

    def test_confirmed_aspect_change_is_saved(self) -> None:
        status, data = self._save({"slug": self.slug, "aspect": "9:16", "confirm_aspect_change": True})
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(self._aspect_on_disk(), "9:16")


if __name__ == "__main__":
    unittest.main()
