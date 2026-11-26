"""Live browser check for the 3D Studio viewport: upload a real .glb and load it in Three.js.

Requires a running console (`python scripts/console_server.py --port 8790`), Playwright with Chromium
and internet access to esm.sh (Three.js 0.170.0 is loaded from there). The check uploads a tiny valid
glTF 2.0 triangle, opens tab 05 · 3D Studio, loads it into the viewport and waits for the success
status. The uploaded file is always removed afterwards. Exit code 0 only when every check passes.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "public" / "models3d"
MODEL_NAME = "glb-viewer-check"


def build_triangle_glb() -> bytes:
    """Minimal valid GLB: one triangle, POSITION only (glTF 2.0)."""
    positions = struct.pack("<9f", 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
    gltf = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
        "accessors": [{
            "bufferView": 0,
            "componentType": 5126,
            "count": 3,
            "type": "VEC3",
            "min": [0.0, 0.0, 0.0],
            "max": [1.0, 1.0, 0.0],
        }],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 36}],
        "buffers": [{"byteLength": 36}],
    }
    json_bytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    json_bytes += b" " * ((4 - len(json_bytes) % 4) % 4)
    bin_bytes = positions + b"\x00" * ((4 - len(positions) % 4) % 4)
    total = 12 + 8 + len(json_bytes) + 8 + len(bin_bytes)
    header = struct.pack("<4sII", b"glTF", 2, total)
    json_chunk = struct.pack("<I4s", len(json_bytes), b"JSON") + json_bytes
    bin_chunk = struct.pack("<I4s", len(bin_bytes), b"BIN\x00") + bin_bytes
    return header + json_chunk + bin_chunk


def upload_model(base_url: str, glb: bytes) -> str:
    req = urllib.request.Request(
        f"{base_url}/api/3d/upload-glb?filename={MODEL_NAME}.glb",
        data=glb,
        headers={"Content-Type": "model/gltf-binary"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"upload refused: HTTP {exc.code} {exc.read().decode('utf-8', 'replace')}") from exc
    if not payload.get("ok"):
        raise RuntimeError(f"upload refused: {payload}")
    return payload["model"]["file"]


def run_checks(base_url: str) -> bool:
    ok = True
    glb = build_triangle_glb()
    model_file = upload_model(base_url, glb)
    model_path = MODELS_DIR / Path(model_file).name
    print(f"[check] uploaded {model_file} ({len(glb)} bytes)")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": 1400, "height": 900})
                errors: list[str] = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.goto(base_url, wait_until="networkidle")
                page.click('[data-tab="3d"]')
                page.wait_for_function("typeof window.loadGlbInViewport === 'function'", timeout=15000)
                page.evaluate(
                    "([u, l]) => window.loadGlbInViewport(u, l)",
                    [f"/public/{model_file}", MODEL_NAME],
                )
                page.wait_for_function(
                    "document.querySelector('#vpStatus') && "
                    "(document.querySelector('#vpStatus').textContent.startsWith('Модель загружена') || "
                    " document.querySelector('#vpStatus').textContent.startsWith('Ошибка') || "
                    " document.querySelector('#vpStatus').textContent.startsWith('Fail-closed'))",
                    timeout=60000,
                )
                status = page.text_content("#vpStatus") or ""
                print(f"[check] viewport status: {status!r}")
                loaded = status.startswith("Модель загружена")
                ok &= loaded

                canvas_count = page.locator("canvas").count()
                print(f"[check] canvas elements on page: {canvas_count}")
                ok &= canvas_count > 0

                print(f"[check] page errors: {errors or 'none'}")
                ok &= not errors
            finally:
                browser.close()
    finally:
        model_path.unlink(missing_ok=True)
        print(f"[check] removed {model_path.name}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="DUP Presenter 3D viewport live check")
    parser.add_argument("--url", default="http://127.0.0.1:8790/")
    args = parser.parse_args()
    base_url = args.url.rstrip("/")
    try:
        ok = run_checks(base_url)
    except Exception as exc:  # noqa: BLE001 - top-level reporter, exits non-zero below
        print(f"[check] FAILED: {exc}")
        ok = False
    print("RESULT: PASS" if ok else "RESULT: FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
