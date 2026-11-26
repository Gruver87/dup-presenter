"""Tests for Timeline (slide reorder + voice WAV waveform) and 3D Studio (GLB upload + fail-closed API)."""
from __future__ import annotations

import http.client
import io
import json
import os
import shutil
import struct
import sys
import threading
import unittest
import uuid
import wave
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import console_server  # noqa: E402
import studio_3d  # noqa: E402


def _make_wav(path: Path, seconds: float = 1.0, rate: int = 16000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = int(rate * seconds)
    samples = struct.pack(f"<{n}h", *[int(12000 * ((i % 40) / 40.0)) for i in range(n)])
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(samples)


def _make_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


def _make_minimal_glb() -> bytes:
    # Valid 12-byte GLB header: magic 'glTF', version 2, total length 12.
    return b"glTF" + struct.pack("<II", 2, 12)


class TimelineAnd3DTests(unittest.TestCase):
    def setUp(self) -> None:
        self.slug = f"tl3d-test-{uuid.uuid4().hex[:8]}"
        self.deck_path = console_server.DECKS_DIR / f"{self.slug}.json"
        self.deck_path.write_text(
            json.dumps({
                "slug": self.slug,
                "brand": "DUP",
                "lang": "ru",
                "theme": "quantum_ledger",
                "aspect": "16:9",
                "width": 1920,
                "height": 1080,
                "voice": {"speaker": "dmitry", "lang": "ru", "mode": "single"},
                "slides": [
                    {"id": "s1", "type": "quote", "tag": "01", "title": "First", "subtitle": "A", "voice_text": "Первый слайд."},
                    {"id": "s2", "type": "quote", "tag": "02", "title": "Second", "subtitle": "B", "voice_text": "Второй слайд."},
                    {"id": "s3", "type": "quote", "tag": "03", "title": "Third", "subtitle": "C", "voice_text": "Третий слайд."},
                ],
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.voice_wav = console_server.ASSETS_PUBLIC_DIR / "voice" / f"{self.slug}_s1.wav"
        _make_wav(self.voice_wav, seconds=1.2)
        self.created_models: list[Path] = []

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), console_server.ConsoleHandler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.deck_path.unlink(missing_ok=True)
        self.voice_wav.unlink(missing_ok=True)
        for p in self.created_models:
            p.unlink(missing_ok=True)
        shutil.rmtree(console_server.WORK_DIR / self.slug, ignore_errors=True)

    def _req(self, method: str, path: str, body: bytes | dict | None = None, content_type: str = "application/json") -> tuple[int, dict | bytes, str]:
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
            ct = resp.getheader("Content-Type") or ""
            if "application/json" in ct:
                return resp.status, json.loads(raw.decode("utf-8")), ct
            return resp.status, raw, ct
        finally:
            conn.close()

    def test_timeline_waveform_and_voice_endpoint(self) -> None:
        st, d, _ = self._req("GET", f"/api/deck?slug={self.slug}")
        self.assertEqual(st, 200)
        tl = d["timeline"]
        self.assertEqual([x["id"] for x in tl], ["s1", "s2", "s3"])
        self.assertTrue(tl[0]["has_audio"])
        self.assertAlmostEqual(tl[0]["duration_sec"], 1.2, places=1)
        self.assertEqual(len(tl[0]["peaks"]), 24)
        self.assertFalse(tl[1]["has_audio"])

        st_w, raw_w, ct_w = self._req("GET", f"/voice/{self.slug}/s1.wav")
        self.assertEqual(st_w, 200)
        self.assertIn("audio/wav", ct_w)
        self.assertTrue(raw_w.startswith(b"RIFF"))

        st_bad, _, _ = self._req("GET", f"/voice/{self.slug}/../evil.wav")
        self.assertEqual(st_bad, 400)

    def test_slide_reorder_and_fail_closed_validation(self) -> None:
        st, d, _ = self._req("POST", "/api/slides/reorder", {"slug": self.slug, "order": ["s3", "s1", "s2"]})
        self.assertEqual(st, 200, d)
        self.assertEqual(d["order"], ["s3", "s1", "s2"])
        saved = json.loads(self.deck_path.read_text(encoding="utf-8"))
        self.assertEqual([s["id"] for s in saved["slides"]], ["s3", "s1", "s2"])

        # Missing slide id -> 400 fail-closed
        st_bad, _, _ = self._req("POST", "/api/slides/reorder", {"slug": self.slug, "order": ["s1", "s2"]})
        self.assertEqual(st_bad, 400)

    def test_3d_studio_upload_glb_and_fail_closed_api(self) -> None:
        # 1) Invalid non-GLB refused
        st_bad, _, _ = self._req("POST", "/api/3d/upload-glb?filename=bad.glb", body=b"not a glb file", content_type="model/gltf-binary")
        self.assertEqual(st_bad, 400)

        # 2) Valid GLB accepted, listed, and served with model/gltf-binary
        glb = _make_minimal_glb()
        st_ok, d_ok, _ = self._req("POST", f"/api/3d/upload-glb?filename={self.slug}.glb", body=glb, content_type="model/gltf-binary")
        self.assertEqual(st_ok, 200, d_ok)
        model_file = d_ok["model"]["file"]
        self.created_models.append(studio_3d.PUBLIC_DIR / model_file)

        st_m, dm, _ = self._req("GET", "/api/3d/models")
        self.assertEqual(st_m, 200)
        self.assertTrue(any(m["file"] == model_file for m in dm["models"]))

        st_pub, raw_pub, ct_pub = self._req("GET", f"/public/{model_file}")
        self.assertEqual(st_pub, 200)
        self.assertIn("model/gltf-binary", ct_pub)
        self.assertEqual(raw_pub[:4], b"glTF")

        # 3) Generate 3D without TRIPO_API_KEY / FAL_KEY -> fail-closed 503
        env = {k: v for k, v in os.environ.items() if k not in {"TRIPO_API_KEY", "FAL_KEY"}}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(console_server, "_load_user_env_into_os", lambda: None):
            st_gen, d_gen, _ = self._req("POST", "/api/3d/generate?name=testcube", body=_make_png(), content_type="image/png")
        self.assertEqual(st_gen, 503, d_gen)
        self.assertFalse(d_gen["ok"])

    def test_fal_queue_urls_outside_fal_host_are_refused(self) -> None:
        requested: list[str] = []

        class _Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def fake_urlopen(req, timeout=None):
            url = req.full_url
            requested.append(url)
            if url == studio_3d.FAL_TRIPOSR_URL:
                return _Resp(json.dumps({
                    "status_url": "https://evil.example.com/status",
                    "response_url": "https://queue.fal.run/fal-ai/triposr/requests/1",
                }).encode("utf-8"))
            raise AssertionError(f"unexpected request to {url}")

        with mock.patch.object(studio_3d.urllib.request, "urlopen", side_effect=fake_urlopen):
            with self.assertRaises(studio_3d.Studio3DError):
                studio_3d._generate_via_fal(_make_png(), ".png", "test-key")
        self.assertEqual(requested, [studio_3d.FAL_TRIPOSR_URL])


if __name__ == "__main__":
    unittest.main()
