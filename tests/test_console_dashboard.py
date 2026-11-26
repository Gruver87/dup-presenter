"""Console dashboard server tests: save-deck music preservation, Video Pack & TikTok gates, exports."""
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

import console_server  # noqa: E402


def _minimal_deck(slug: str) -> dict:
    return {
        "slug": slug,
        "brand": "DUP",
        "lang": "ru",
        "theme": "quantum_ledger",
        "aspect": "16:9",
        "width": 1920,
        "height": 1080,
        "voice": {"speaker": "dmitry", "lang": "ru", "mode": "single"},
        "music": {"enabled": True, "file": "custom-track.mp3", "volume": 0.13},
        "slides": [
            {
                "id": "s1",
                "type": "quote",
                "tag": "01",
                "title": "Test",
                "subtitle": "Author",
                "voice_text": "Короткая тестовая фраза для проверки консоли.",
            }
        ],
    }


class ConsoleDashboardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.slug = f"dash-test-{uuid.uuid4().hex[:8]}"
        self.merged_slug = f"merged-test-{uuid.uuid4().hex[:8]}"
        self.deck_path = console_server.DECKS_DIR / f"{self.slug}.json"
        self.deck_path.write_text(json.dumps(_minimal_deck(self.slug), ensure_ascii=False, indent=2), encoding="utf-8")
        self.created_out: list[Path] = []

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), console_server.ConsoleHandler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.deck_path.unlink(missing_ok=True)
        for p in self.created_out:
            p.unlink(missing_ok=True)
        shutil.rmtree(console_server.WORK_DIR / self.slug, ignore_errors=True)

    def _req(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict | bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            headers = {"Content-Type": "application/json"} if body is not None else {}
            payload = json.dumps(body).encode("utf-8") if body is not None else None
            conn.request(method, path, body=payload, headers=headers)
            resp = conn.getresponse()
            raw = resp.read()
            ct = resp.getheader("Content-Type", "")
            if "application/json" in ct:
                return resp.status, json.loads(raw.decode("utf-8"))
            return resp.status, raw
        finally:
            conn.close()

    def _touch_out(self, name: str, content: bytes | str) -> Path:
        p = console_server.OUT_DIR / name
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            p.write_bytes(content)
        else:
            p.write_text(content, encoding="utf-8")
        self.created_out.append(p)
        return p

    def _raw(self, method: str, path: str, headers: dict[str, str], body: bytes | None = None) -> int:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.putrequest(method, path, skip_host="Host" in headers)
            for k, v in headers.items():
                conn.putheader(k, v)
            conn.putheader("Content-Length", str(len(body or b"")))
            conn.endheaders(body or b"")
            resp = conn.getresponse()
            resp.read()
            return resp.status
        finally:
            conn.close()

    def test_cross_site_and_dns_rebinding_requests_refused(self) -> None:
        deck_before = self.deck_path.read_text(encoding="utf-8")
        body = json.dumps({"slug": self.slug, "deck": _minimal_deck(self.slug)}).encode("utf-8")

        self.assertEqual(
            self._raw("POST", "/api/save-deck", {"Origin": "https://evil.example", "Content-Type": "text/plain"}, body),
            403,
        )
        self.assertEqual(
            self._raw("POST", "/api/save-deck", {"Origin": "null", "Content-Type": "text/plain"}, body),
            403,
        )
        self.assertEqual(
            self._raw("POST", "/api/save-deck", {"Sec-Fetch-Site": "cross-site", "Content-Type": "text/plain"}, body),
            403,
        )
        self.assertEqual(self._raw("GET", "/api/state", {"Host": f"evil.example:{self.port}"}), 403)
        self.assertEqual(self.deck_path.read_text(encoding="utf-8"), deck_before)

        self.assertEqual(
            self._raw("GET", "/api/live", {"Origin": f"http://127.0.0.1:{self.port}", "Sec-Fetch-Site": "same-origin"}),
            200,
        )
        self.assertEqual(self._raw("GET", "/api/live", {"Host": f"localhost:{self.port}"}), 200)

    def test_save_deck_preserves_music_file_and_volume(self) -> None:
        status, data = self._req("POST", "/api/save-deck", {
            "slug": self.slug,
            "music_enabled": True,
            "render": False,
        })
        self.assertEqual(status, 200, data)
        saved = json.loads(self.deck_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["music"]["file"], "custom-track.mp3")
        self.assertEqual(saved["music"]["volume"], 0.13)
        self.assertTrue(saved["music"]["enabled"])

    def test_video_pack_build_refused_without_storyboard_approval(self) -> None:
        status, data = self._req("POST", "/api/video-pack/build", {"slug": self.slug})
        self.assertEqual(status, 409, data)
        self.assertFalse(data["ok"])
        self.assertIn("Video Pack", data["error"])

    def test_tiktok_upload_refused_for_unapproved_deck_master(self) -> None:
        self._touch_out(f"{self.slug}.mp4", b"fake-mp4-bytes")
        status, data = self._req("POST", "/api/tiktok/upload", {"slug": self.slug, "mode": "inbox", "dry_run": True})
        self.assertEqual(status, 409, data)
        self.assertFalse(data["ok"])
        self.assertIn("TikTok", data["error"])

    def test_tiktok_upload_allows_merged_mp4_without_deck(self) -> None:
        self._touch_out(f"{self.merged_slug}.mp4", b"fake-merged-mp4")
        orig_start = console_server.JOBS.start
        started: list[tuple[str, str, list[str]]] = []
        console_server.JOBS.start = lambda step, slug, cmd: (started.append((step, slug, cmd)) or True)
        try:
            status, data = self._req("POST", "/api/tiktok/upload", {"slug": self.merged_slug, "mode": "inbox", "dry_run": True})
        finally:
            console_server.JOBS.start = orig_start
        self.assertEqual(status, 202, data)
        self.assertTrue(data["ok"])
        self.assertEqual(len(started), 1)
        self.assertEqual(started[0][0], "tiktok")
        self.assertEqual(started[0][1], self.merged_slug)

    def test_publish_pack_exports_and_out_route(self) -> None:
        self._touch_out(f"{self.slug}_post_copy.md", "# Post\n\n## Источники визуалов\n- credit\n")
        self._touch_out(f"{self.slug}_chapters.txt", "00:00 Intro\n")
        self._touch_out(f"{self.slug}_visual_credits.txt", "Visual credits\n")
        self._touch_out(f"{self.slug}_cover.png", b"\x89PNG\r\n\x1a\n")
        # Real media_qa report shape: loudness lives under "audio".
        self._touch_out(
            f"{self.slug}_qa.json",
            json.dumps({"ok": True, "audio": {"integrated_lufs": -16.1, "true_peak_dbtp": -1.5}}),
        )

        status, detail = self._req("GET", f"/api/deck?slug={self.slug}")
        self.assertEqual(status, 200)
        self.assertTrue(detail["has_post_copy"])
        self.assertTrue(detail["has_chapters"])
        self.assertTrue(detail["has_credits"])
        self.assertTrue(detail["has_cover"])
        self.assertTrue(detail["has_qa"])
        self.assertEqual(detail["qa_summary"], {"ok": True, "lufs": -16.1, "true_peak_db": -1.5})

        for fname in (f"{self.slug}_visual_credits.txt", f"{self.slug}_cover.png", f"{self.slug}_post_copy.md"):
            st, _ = self._req("GET", f"/out/{fname}")
            self.assertEqual(st, 200, fname)

        st_bad, _ = self._req("GET", "/out/..%2F..%2Fsecrets.txt")
        self.assertEqual(st_bad, 400)


if __name__ == "__main__":
    unittest.main()
