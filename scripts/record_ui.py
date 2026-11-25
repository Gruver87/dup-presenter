"""Scenario-driven live UI recorder (fail-closed).

Plays a JSON scenario in headless Chromium through Playwright, records the page to WebM,
converts it to MP4 with ffmpeg and writes a timeline JSON with the start/end second of every step.

Playwright does not draw the mouse pointer into its video, so a visual cursor is injected into
the page: it glides to each target before a click or typing, and shows a click ripple. The real
Playwright click happens after the glide, so the cursor is a visual aid and not the input device.

Scenario format (JSON):
    {
      "name": "local-demo",                       # slug: [a-z0-9][a-z0-9_-]{0,60}
      "url": "http://127.0.0.1:8787/",            # or file:// ; http(s) and file only
      "viewport": {"width": 1920, "height": 1080},
      "steps": [
        {"action": "goto", "url": "..."},
        {"action": "click", "selector": "button#go", "cursor_ms": 600},
        {"action": "type", "selector": "input#q", "text": "hello"},
        {"action": "scroll", "dy": 400},
        {"action": "wait", "ms": 1200}
      ]
    }

Usage:
    python scripts/record_ui.py --scenario scenarios/example_local_demo.json
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT_DIR = ROOT / "out" / "ui_recordings"

ALLOWED_ACTIONS = frozenset({"goto", "click", "type", "scroll", "wait"})
NAME_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,60}")
MAX_STEPS = 100
MAX_TOTAL_MS = 600_000
MAX_WAIT_MS = 20_000
MAX_SELECTOR_LEN = 300
MAX_TEXT_LEN = 300
MIN_VIEWPORT = 640
MAX_VIEWPORT = 3840
CURSOR_MS_DEFAULT = 600
CURSOR_MS_MAX = 3000
STEP_TIMEOUT_MS = 10_000


class RecordUIError(RuntimeError):
    """Fail-closed recorder error (invalid scenario, browser failure, missing ffmpeg)."""


def _require_int(value: Any, field: str, lo: int, hi: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RecordUIError(f"{field} must be an integer, got {value!r}")
    if not lo <= value <= hi:
        raise RecordUIError(f"{field} must be in [{lo}, {hi}], got {value}")
    return value


def _require_str(value: Any, field: str, max_len: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RecordUIError(f"{field} must be a non-empty string")
    if len(value) > max_len:
        raise RecordUIError(f"{field} longer than {max_len} characters")
    return value


def _check_url(url: str, field: str) -> str:
    if not url.startswith(("http://", "https://", "file://")):
        raise RecordUIError(f"{field}: unsupported URL scheme {url!r}")
    return url


def validate_scenario(scenario: Any) -> dict:
    """Validate and normalise a scenario. Raises RecordUIError on any problem (no partial recording)."""
    if not isinstance(scenario, dict):
        raise RecordUIError("scenario must be a JSON object")

    name = scenario.get("name")
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        raise RecordUIError(f"name must match {NAME_RE.pattern!r}, got {name!r}")

    url = _check_url(_require_str(scenario.get("url"), "url", 2000), "url")

    viewport = scenario.get("viewport") or {"width": 1920, "height": 1080}
    if not isinstance(viewport, dict):
        raise RecordUIError("viewport must be an object with width and height")
    width = _require_int(viewport.get("width"), "viewport.width", MIN_VIEWPORT, MAX_VIEWPORT)
    height = _require_int(viewport.get("height"), "viewport.height", MIN_VIEWPORT, MAX_VIEWPORT)

    steps_raw = scenario.get("steps")
    if not isinstance(steps_raw, list) or not steps_raw:
        raise RecordUIError("steps must be a non-empty list")
    if len(steps_raw) > MAX_STEPS:
        raise RecordUIError(f"at most {MAX_STEPS} steps allowed, got {len(steps_raw)}")

    steps: list[dict] = []
    total_ms = 0
    for i, raw in enumerate(steps_raw):
        where = f"steps[{i}]"
        if not isinstance(raw, dict):
            raise RecordUIError(f"{where} must be an object")
        action = raw.get("action")
        if action not in ALLOWED_ACTIONS:
            raise RecordUIError(f"{where}: unknown action {action!r}; allowed: {sorted(ALLOWED_ACTIONS)}")

        cursor_ms = _require_int(raw.get("cursor_ms", CURSOR_MS_DEFAULT), f"{where}.cursor_ms", 100, CURSOR_MS_MAX)
        step: dict[str, Any] = {"action": action, "cursor_ms": cursor_ms}

        if action == "goto":
            step["url"] = _check_url(_require_str(raw.get("url"), f"{where}.url", 2000), f"{where}.url")
            total_ms += 3_000  # navigation budget
        elif action in ("click", "type"):
            step["selector"] = _require_str(raw.get("selector"), f"{where}.selector", MAX_SELECTOR_LEN)
            if action == "type":
                step["text"] = _require_str(raw.get("text"), f"{where}.text", MAX_TEXT_LEN)
                total_ms += len(step["text"]) * 60
            total_ms += cursor_ms + 500
        elif action == "scroll":
            step["dy"] = _require_int(raw.get("dy"), f"{where}.dy", -3000, 3000)
            total_ms += 1_000
        elif action == "wait":
            step["ms"] = _require_int(raw.get("ms"), f"{where}.ms", 0, MAX_WAIT_MS)
            total_ms += step["ms"]
        steps.append(step)

    if total_ms > MAX_TOTAL_MS:
        raise RecordUIError(f"estimated scenario length {total_ms} ms exceeds {MAX_TOTAL_MS} ms")

    return {"name": name, "url": url, "viewport": {"width": width, "height": height}, "steps": steps}


# Visual cursor injected into every frame. Positions are viewport coordinates (position: fixed).
_CURSOR_INIT_JS = r"""
(() => {
  if (window.__dupCursorInstalled) return;
  window.__dupCursorInstalled = true;
  const install = () => {
    if (document.getElementById('__dup_cursor') || !document.documentElement) return;
    const c = document.createElement('div');
    c.id = '__dup_cursor';
    c.style.cssText = [
      'position:fixed', 'left:0', 'top:0', 'width:22px', 'height:22px', 'margin:-4px 0 0 -4px',
      'border-radius:50%', 'background:rgba(0,255,213,0.9)',
      'box-shadow:0 0 0 2px rgba(0,0,0,0.65),0 0 14px rgba(0,255,213,0.9)',
      'pointer-events:none', 'z-index:2147483647', 'transform:translate(0px,0px)'
    ].join(';');
    c.dataset.x = '0';
    c.dataset.y = '0';
    document.documentElement.appendChild(c);
  };
  install();
  document.addEventListener('DOMContentLoaded', install);
  window.__dupMoveTo = (x, y, ms) => new Promise((resolve) => {
    install();
    const c = document.getElementById('__dup_cursor');
    if (!c) { resolve(); return; }
    const sx = parseFloat(c.dataset.x || '0');
    const sy = parseFloat(c.dataset.y || '0');
    const t0 = performance.now();
    const frame = (now) => {
      const k = Math.min(1, (now - t0) / Math.max(1, ms));
      const e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
      const cx = sx + (x - sx) * e;
      const cy = sy + (y - sy) * e;
      c.style.transform = 'translate(' + cx + 'px,' + cy + 'px)';
      c.dataset.x = String(cx);
      c.dataset.y = String(cy);
      if (k < 1) requestAnimationFrame(frame); else resolve();
    };
    requestAnimationFrame(frame);
  });
  window.__dupRipple = (x, y) => {
    const r = document.createElement('div');
    r.style.cssText = 'position:fixed;left:' + x + 'px;top:' + y + 'px;width:40px;height:40px;margin:-20px 0 0 -20px;'
      + 'border-radius:50%;border:3px solid rgba(0,255,213,0.95);pointer-events:none;z-index:2147483646;';
    (document.documentElement || document.body).appendChild(r);
    r.animate([{ transform: 'scale(0.3)', opacity: 0.9 }, { transform: 'scale(2.2)', opacity: 0 }], { duration: 450 })
      .onfinish = () => r.remove();
  };
})();
"""


def _find_ffmpeg() -> Path:
    try:
        from audio_fx import find_ffmpeg
    except ImportError as exc:  # pragma: no cover - import guard
        raise RecordUIError(f"audio_fx unavailable, cannot locate ffmpeg: {exc}") from exc
    try:
        return find_ffmpeg()
    except Exception as exc:
        raise RecordUIError(f"ffmpeg not found: {exc}") from exc


def _pointer_target(page, selector: str) -> tuple[float, float]:
    box = page.locator(selector).first.bounding_box(timeout=STEP_TIMEOUT_MS)
    if not box:
        raise RecordUIError(f"element has no bounding box: {selector!r}")
    return box["x"] + box["width"] / 2.0, box["y"] + box["height"] / 2.0


def _run_steps(page, steps: list[dict], t0: float) -> list[dict]:
    timeline: list[dict] = []
    for index, step in enumerate(steps):
        start = time.monotonic() - t0
        action = step["action"]
        try:
            if action == "goto":
                page.goto(step["url"], wait_until="networkidle", timeout=STEP_TIMEOUT_MS * 3)
                page.wait_for_timeout(300)
            elif action == "click":
                x, y = _pointer_target(page, step["selector"])
                page.evaluate("([x, y, ms]) => window.__dupMoveTo(x, y, ms)", [x, y, step["cursor_ms"]])
                page.evaluate("([x, y]) => window.__dupRipple(x, y)", [x, y])
                page.locator(step["selector"]).first.click(timeout=STEP_TIMEOUT_MS)
                page.wait_for_timeout(300)
            elif action == "type":
                x, y = _pointer_target(page, step["selector"])
                page.evaluate("([x, y, ms]) => window.__dupMoveTo(x, y, ms)", [x, y, step["cursor_ms"]])
                page.locator(step["selector"]).first.click(timeout=STEP_TIMEOUT_MS)
                page.locator(step["selector"]).first.press_sequentially(step["text"], delay=60, timeout=STEP_TIMEOUT_MS)
                page.wait_for_timeout(300)
            elif action == "scroll":
                page.evaluate("(dy) => window.scrollBy({ top: dy, behavior: 'smooth' })", step["dy"])
                page.wait_for_timeout(900)
            elif action == "wait":
                page.wait_for_timeout(step["ms"])
        except RecordUIError:
            raise
        except Exception as exc:
            raise RecordUIError(f"step {index} ({action}) failed: {type(exc).__name__}: {exc}") from exc
        end = time.monotonic() - t0
        entry = {"index": index, "action": action, "start_sec": round(start, 3), "end_sec": round(end, 3)}
        for key in ("selector", "url", "text", "dy", "ms"):
            if key in step:
                entry[key] = step[key]
        timeline.append(entry)
    return timeline


def record_scenario(scenario: dict, *, out_dir: Path = DEFAULT_OUT_DIR, overwrite: bool = False) -> dict:
    """Validate, record and convert one scenario. Returns paths and the step timeline."""
    sc = validate_scenario(scenario)
    out_dir.mkdir(parents=True, exist_ok=True)
    mp4_path = out_dir / f"{sc['name']}.mp4"
    timeline_path = out_dir / f"{sc['name']}_timeline.json"
    if mp4_path.exists() and not overwrite:
        raise RecordUIError(f"{mp4_path.name} already exists; pass overwrite=True or use a new name")

    ffmpeg = _find_ffmpeg()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RecordUIError("playwright is not installed (pip install playwright)") from exc
    from capture_ui import CaptureUIError, _launch_browser

    vw, vh = sc["viewport"]["width"], sc["viewport"]["height"]
    with tempfile.TemporaryDirectory(prefix="record_ui_") as tmp:
        video_dir = Path(tmp)
        try:
            with sync_playwright() as p:
                browser = _launch_browser(p)
                context = browser.new_context(
                    viewport={"width": vw, "height": vh},
                    record_video_dir=str(video_dir),
                    record_video_size={"width": vw, "height": vh},
                )
                context.add_init_script(_CURSOR_INIT_JS)
                page = context.new_page()
                t0 = time.monotonic()
                try:
                    timeline = _run_steps(page, [{"action": "goto", "url": sc["url"], "cursor_ms": CURSOR_MS_DEFAULT}]
                                          + sc["steps"], t0)
                finally:
                    video_path = Path(page.video.path()) if page.video else None
                    context.close()
                    browser.close()
        except CaptureUIError as exc:
            raise RecordUIError(str(exc)) from exc

        if video_path is None or not video_path.is_file() or video_path.stat().st_size == 0:
            raise RecordUIError("Playwright produced no video file")

        tmp_mp4 = out_dir / f".{sc['name']}.tmp.mp4"
        cmd = [
            str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(video_path),
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", "-an", str(tmp_mp4),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if proc.returncode != 0 or not tmp_mp4.is_file():
            tmp_mp4.unlink(missing_ok=True)
            raise RecordUIError(f"ffmpeg conversion failed (exit {proc.returncode}): {proc.stderr[-600:]}")
        shutil.move(str(tmp_mp4), str(mp4_path))

    timeline_doc = {
        "name": sc["name"],
        "url": sc["url"],
        "viewport": sc["viewport"],
        "mp4": str(mp4_path),
        "duration_sec": timeline[-1]["end_sec"] if timeline else 0.0,
        "steps": timeline,
        "note": "Step times are wall-clock offsets from page creation; the video starts at page creation too.",
    }
    timeline_path.write_text(json.dumps(timeline_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "mp4": str(mp4_path), "timeline": str(timeline_path), "steps": len(timeline)}


def main() -> int:
    parser = argparse.ArgumentParser(description="DUP Presenter scenario-driven UI recorder")
    parser.add_argument("--scenario", required=True, help="Path to scenario JSON")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        scenario_path = Path(args.scenario).resolve()
        raw_text = scenario_path.read_text(encoding="utf-8")
        # {SCENARIO_DIR} lets a scenario reference files beside it without machine-specific paths.
        raw_text = raw_text.replace("{SCENARIO_DIR}", scenario_path.parent.as_posix())
        scenario = json.loads(raw_text)
        result = record_scenario(scenario, out_dir=Path(args.out_dir), overwrite=args.overwrite)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (RecordUIError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
