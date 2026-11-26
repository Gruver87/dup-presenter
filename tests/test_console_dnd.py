"""Tests for console HTML5 Drag-and-Drop asset upload, Inspector metadata, smart binding, and CC BY flow."""
from __future__ import annotations

import http.client
import io
import json
import shutil
import sys
import threading
import unittest
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import asset_store  # noqa: E402
import console_server  # noqa: E402
import publish_pack  # noqa: E402


def _make_png(w: int = 320, h: int = 180) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (18, 42, 88)).save(buf, format="PNG")
    return buf.getvalue()


def _deck_with_media_slides(slug: str) -> dict:
    return {
        "slug": slug,
        "brand": "DUP",
        "lang": "ru",
        "theme": "quantum_ledger",
        "aspect": "16:9",
        "width": 1920,
        "height": 1080,
        "voice": {"speaker": "dmitry", "lang": "ru", "mode": "single"},
        "slides": [
            {
                "id": "s_broll",
                "type": "broll_cinematic",
                "tag": "01",
                "title": "B-roll slide",
                "broll": {"callouts": ["Test"]},
                "voice_text": "Тестовый слайд для картинки.",
            },
            {
                "id": "s_cinema",
                "type": "cinema_clip",
                "tag": "02",
                "title": "Cinema slide",
                "background_query": "nebula space",
                "cinema": {"badge": "TEST"},
                "voice_text": "Тестовый слайд для кино.",
            },
            {
                "id": "s_quote",
                "type": "quote",
                "tag": "03",
                "title": "Quote slide",
                "subtitle": "Author",
                "voice_text": "Текстовый слайд без медиа.",
            },
        ],
    }


class ConsoleDndAssetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.slug = f"dnd-test-{uuid.uuid4().hex[:8]}"
        self.deck_path = console_server.DECKS_DIR / f"{self.slug}.json"
        self.deck_path.write_text(
            json.dumps(_deck_with_media_slides(self.slug), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), console_server.ConsoleHandler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.deck_path.unlink(missing_ok=True)
        shutil.rmtree(asset_store.UPLOADS_DIR / self.slug, ignore_errors=True)
        shutil.rmtree(console_server.WORK_DIR / self.slug, ignore_errors=True)

    def _req(self, method: str, path: str, body: bytes | dict | None = None, content_type: str = "application/json") -> tuple[int, dict | bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            headers = {}
            payload = None
            if isinstance(body, dict):
                headers["Content-Type"] = "application/json"
                payload = json.dumps(body).encode("utf-8")
            elif isinstance(body, bytes):
                headers["Content-Type"] = content_type
                payload = body
            conn.request(method, path, body=payload, headers=headers)
            resp = conn.getresponse()
            raw = resp.read()
            if "application/json" in (resp.getheader("Content-Type") or ""):
                return resp.status, json.loads(raw.decode("utf-8"))
            return resp.status, raw
        finally:
            conn.close()

    def test_binary_png_upload_binds_to_broll_and_cinema_and_inspect_and_credits(self) -> None:
        png = _make_png(640, 360)
        st, d = self._req(
            "POST",
            f"/api/assets/upload?slug={self.slug}&slide_id=s_broll&filename=nebula.png",
            body=png,
            content_type="image/png",
        )
        self.assertEqual(st, 200, d)
        self.assertTrue(d["ok"])
        rel = d["asset"]["file"]
        self.assertTrue(rel.startswith(f"uploads/{self.slug}/"))
        self.assertEqual(d["asset"]["width"], 640)
        self.assertEqual(d["asset"]["height"], 360)

        # Deck updated with broll.image
        deck = json.loads(self.deck_path.read_text(encoding="utf-8"))
        self.assertEqual(deck["slides"][0]["broll"]["image"], rel)

        # Smart binding: PNG dropped onto cinema_clip becomes cinema.shots[0] (kind=image)
        st2, d2 = self._req(
            "POST",
            f"/api/assets/upload?slug={self.slug}&slide_id=s_cinema&filename=nebula.png",
            body=png,
            content_type="image/png",
        )
        self.assertEqual(st2, 200, d2)
        deck2 = json.loads(self.deck_path.read_text(encoding="utf-8"))
        self.assertEqual(deck2["slides"][1]["cinema"]["shots"][0]["src"], rel)
        self.assertEqual(deck2["slides"][1]["cinema"]["shots"][0]["kind"], "image")

        # Serve via /public/
        st_pub, raw_pub = self._req("GET", f"/public/{rel}")
        self.assertEqual(st_pub, 200)
        self.assertTrue(raw_pub.startswith(b"\x89PNG"))

        # Inspect returns real specs
        st_i, di = self._req("GET", f"/api/assets/inspect?slug={self.slug}&file={rel}")
        self.assertEqual(st_i, 200, di)
        self.assertEqual(di["asset"]["width"], 640)

        # Update metadata to CC BY -> publish_pack.visual_credit_lines picks it up automatically!
        st_m, dm = self._req("POST", "/api/assets/meta", {
            "slug": self.slug,
            "file": rel,
            "meta": {
                "title": "Deep Space Nebula",
                "creator": "ESA/Hubble",
                "license": "by",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "page_url": "https://commons.wikimedia.org/wiki/File:Nebula.png",
            },
        })
        self.assertEqual(st_m, 200, dm)
        self.assertTrue(dm["asset"]["needs_credit"])
        credits = publish_pack.visual_credit_lines(self.slug)
        self.assertEqual(len(credits), 1)
        self.assertIn("Deep Space Nebula", credits[0])
        self.assertIn("ESA/Hubble", credits[0])

    def test_fail_closed_refusals(self) -> None:
        # Bad magic bytes (plain text disguised as png)
        st, d = self._req(
            "POST",
            f"/api/assets/upload?slug={self.slug}&slide_id=s_broll&filename=fake.png",
            body=b"not an image at all, just plain text",
            content_type="image/png",
        )
        self.assertEqual(st, 400, d)

        # Drop onto quote slide refused
        st2, d2 = self._req(
            "POST",
            f"/api/assets/upload?slug={self.slug}&slide_id=s_quote&filename=ok.png",
            body=_make_png(),
            content_type="image/png",
        )
        self.assertEqual(st2, 400, d2)

        # Non-https URL refused
        st3, d3 = self._req("POST", "/api/assets/upload", {
            "slug": self.slug,
            "slide_id": "s_broll",
            "url": "http://insecure.example.com/a.jpg",
        })
        self.assertEqual(st3, 400, d3)

        # Path traversal on /public/ refused
        st4, _ = self._req("GET", "/public/uploads/../../secrets.txt")
        self.assertEqual(st4, 400)

    def test_tiktok_blocked_until_uploaded_asset_has_licence(self) -> None:
        st, d = self._req(
            "POST",
            f"/api/assets/upload?slug={self.slug}&slide_id=s_broll&filename=mystery.png",
            body=_make_png(),
            content_type="image/png",
        )
        self.assertEqual(st, 200, d)
        rel = d["asset"]["file"]

        mp4 = console_server.OUT_DIR / f"{self.slug}.mp4"
        mp4.parent.mkdir(parents=True, exist_ok=True)
        mp4.write_bytes(b"not-a-real-mp4-but-gate-runs-before-upload")
        try:
            st_t, dt = self._req("POST", "/api/tiktok/upload", {"slug": self.slug, "dry_run": True})
            self.assertEqual(st_t, 409, dt)
            self.assertEqual(dt["unlicensed"], [rel])
            self.assertIn("лиценз", dt["error"])

            st_m, dm = self._req("POST", "/api/assets/meta", {
                "slug": self.slug,
                "file": rel,
                "meta": {"license": "cc0", "title": "Own test image"},
            })
            self.assertEqual(st_m, 200, dm)

            # Licence gate now passes; the request proceeds to the storyboard gate (no draft yet).
            st_t2, dt2 = self._req("POST", "/api/tiktok/upload", {"slug": self.slug, "dry_run": True})
            self.assertEqual(st_t2, 409, dt2)
            self.assertNotIn("unlicensed", dt2)
            self.assertNotIn("лиценз", dt2.get("error", ""))
        finally:
            mp4.unlink(missing_ok=True)

    def test_corrupt_assets_meta_refuses_instead_of_overwriting(self) -> None:
        st, d = self._req(
            "POST",
            f"/api/assets/upload?slug={self.slug}&slide_id=s_broll&filename=a.png",
            body=_make_png(),
            content_type="image/png",
        )
        self.assertEqual(st, 200, d)
        rel = d["asset"]["file"]

        meta_p = asset_store.meta_path_for(self.slug)
        corrupt = '{"uploads/other.png": {"license": "by", "title": "Keep me"'
        meta_p.write_text(corrupt, encoding="utf-8")

        st_m, dm = self._req("POST", "/api/assets/meta", {
            "slug": self.slug,
            "file": rel,
            "meta": {"license": "cc0"},
        })
        self.assertEqual(st_m, 400, dm)
        self.assertFalse(dm["ok"])
        self.assertEqual(meta_p.read_text(encoding="utf-8"), corrupt)

        st_u, du = self._req(
            "POST",
            f"/api/assets/upload?slug={self.slug}&slide_id=s_broll&filename=b.png",
            body=_make_png(200, 100),
            content_type="image/png",
        )
        self.assertEqual(st_u, 400, du)
        self.assertEqual(meta_p.read_text(encoding="utf-8"), corrupt)


if __name__ == "__main__":
    unittest.main()
