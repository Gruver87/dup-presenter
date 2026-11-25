"""Playwright live UI capture tool with automatic virtual-camera focus coordinates.

Captures clean borderless screenshots (no OS window chrome / taskbar) of any local
or web dashboard into public/screens/<name>.png and computes normalized focus points
(x, y in 0..1) for target CSS selectors so Remotion's ScreenWindow3D can zoom smoothly
onto key UI regions.

Usage:
    python scripts/capture_ui.py --url http://127.0.0.1:8080 --out radar_live_auto.png --focus-selector "table" --zoom 1.45
    python scripts/capture_ui.py --spec work/capture_spec.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCREENS_DIR = ROOT / "public" / "screens"


class CaptureUIError(RuntimeError):
    """Fail-closed UI capture error."""


def _launch_browser(p):
    """Launch headless Chromium: prefer Playwright's binary, fall back to system Chrome/Edge."""
    last_exc: Exception | None = None
    attempts = [
        {"headless": True},
        {"headless": True, "channel": "chrome"},
        {"headless": True, "channel": "msedge"},
    ]
    for kw in attempts:
        try:
            return p.chromium.launch(**kw)
        except Exception as exc:
            last_exc = exc
    raise CaptureUIError(f"Could not launch Chromium/Chrome/Edge via Playwright: {last_exc}") from last_exc


def capture_shot(
    url: str,
    out_name: str,
    width: int = 1440,
    height: int = 860,
    wait_ms: int = 1200,
    click_selectors: list[str] | None = None,
    focus_selector: str = "",
    zoom: float = 1.45,
    timeout_ms: int = 20000,
    device_scale: int = 1,
) -> dict:
    """Capture a borderless screenshot via Playwright Chromium and compute optional focus coordinates.

    device_scale=2 produces a 2x raster so small UI text stays legible after 3D zoom in the video.
    """
    if not url.startswith(("http://", "https://", "file://")):
        raise CaptureUIError(f"Unsupported URL scheme: {url!r}")
    if device_scale not in (1, 2, 3):
        raise CaptureUIError(f"device_scale must be 1, 2 or 3, got {device_scale!r}")
    if Path(out_name).name != out_name or not out_name.lower().endswith(".png"):
        raise CaptureUIError(f"out_name must be a plain .png filename inside public/screens, got {out_name!r}")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise CaptureUIError("playwright is not installed (pip install playwright && playwright install chromium)") from exc

    SCREENS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SCREENS_DIR / out_name
    focus: dict | None = None

    with sync_playwright() as p:
        browser = _launch_browser(p)
        try:
            page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=device_scale)
            page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            for sel in click_selectors or []:
                page.locator(sel).first.click(timeout=5000)
                page.wait_for_timeout(350)
            if wait_ms > 0:
                page.wait_for_timeout(wait_ms)
            if focus_selector:
                box = page.locator(focus_selector).first.bounding_box(timeout=5000)
                if box and width > 0 and height > 0:
                    cx = (box["x"] + box["width"] / 2.0) / float(width)
                    cy = (box["y"] + box["height"] / 2.0) / float(height)
                    focus = {
                        "x": round(min(0.95, max(0.05, cx)), 3),
                        "y": round(min(0.95, max(0.05, cy)), 3),
                        "zoom": round(min(2.2, max(1.1, float(zoom))), 2),
                    }
            page.screenshot(path=str(out_path), full_page=False)
        finally:
            browser.close()

    if not out_path.is_file() or out_path.stat().st_size == 0:
        raise CaptureUIError(f"Playwright wrote no screenshot to {out_path}")

    return {
        "ok": True,
        "src": f"screens/{out_name}",
        "path": str(out_path),
        "bytes": out_path.stat().st_size,
        "viewport": [width, height],
        "focus": focus,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="DUP Presenter Playwright live UI capture")
    parser.add_argument("--url", default="", help="Page URL to capture")
    parser.add_argument("--out", default="", help="Output PNG filename inside public/screens/")
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=860)
    parser.add_argument("--wait-ms", type=int, default=1200)
    parser.add_argument("--click", action="append", default=[], help="Optional CSS selector(s) to click before shot")
    parser.add_argument("--focus-selector", default="", help="Optional CSS selector for ScreenWindow3D auto-zoom")
    parser.add_argument("--zoom", type=float, default=1.45)
    parser.add_argument("--device-scale", type=int, default=1, choices=[1, 2, 3], help="2 = retina raster for crisp text")
    parser.add_argument("--spec", default="", help="Optional JSON spec containing a list of shots")
    args = parser.parse_args()

    try:
        if args.spec:
            sp = Path(args.spec)
            if not sp.is_absolute():
                sp = ROOT / sp
            spec = json.loads(sp.read_text(encoding="utf-8"))
            shots = spec.get("shots") if isinstance(spec, dict) else spec
            results = [capture_shot(**s) for s in shots]
            print(json.dumps({"ok": True, "shots": results}, ensure_ascii=False, indent=2))
            return 0
        if not args.url or not args.out:
            print("[ERROR] Provide --url and --out, or --spec <file.json>", file=sys.stderr)
            return 2
        res = capture_shot(
            url=args.url,
            out_name=args.out,
            width=args.width,
            height=args.height,
            wait_ms=args.wait_ms,
            click_selectors=args.click,
            focus_selector=args.focus_selector,
            zoom=args.zoom,
            device_scale=args.device_scale,
        )
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
