"""Fail-closed Cinema AI adapter for DUP Presenter (Runway Dev API + daily credit budget).

Supports:
  1. Offline structured prompt builder (`build_cinema_prompts`) for free web tools
     (Krea, Dreamina, Runway Web) and API calls alike.
  2. Official Runway Dev API (`RUNWAYML_API_SECRET`) for:
       - Text-to-Image (`POST /v1/text_to_image`)
       - Image-to-Video (`POST /v1/image_to_video`)
  3. Daily credit budget (`DUP_CINEMA_DAILY_CREDITS`, default 150 credits = $1.50/day)
     enforced BEFORE every paid call and refunded if the call fails.

Fail-closed policy:
  - Never hardcodes secrets; reads `RUNWAYML_API_SECRET` from Windows environment only.
  - TLS verification is always enabled (default `urllib.request` SSL context).
  - Missing key, unknown model, budget exhausted, corrupt budget file, HTTP errors,
    failed tasks, timeouts and malformed JSON all raise `CinemaApiError`.
  - Publication is NOT part of this module. Output stays under public/cinema/generated/.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from secret_guard import (
    SecretLeakError,
    assert_no_secrets_in_text,
    guard_status,
    install_egress_guard,
    redact_secrets,
)

install_egress_guard()

ROOT = Path(__file__).resolve().parent.parent
BUDGET_FILE = ROOT / "out" / "cinema_budget.json"

RUNWAY_API_BASE = "https://api.dev.runwayml.com/v1"
RUNWAY_API_VERSION = "2024-11-06"
DEFAULT_HTTP_TIMEOUT_SEC = 30.0
DEFAULT_POLL_INTERVAL_SEC = 3.0
DEFAULT_DAILY_CAP_CREDITS: int | None = None
CREDIT_USD = 0.01
DEFAULT_CINEMA_STYLE = (
    "cinematic, dark observatory hall, volumetric cyan light, floating dust, "
    "35mm film look, shallow depth of field, 16:9, no text, no logos"
)
DEFAULT_MOTION_SUFFIX = (
    "slow camera dolly-in, subtle atmospheric motion, dust drifts through the light, "
    "no camera cuts, no text"
)
ALLOWED_RATIOS: frozenset[str] = frozenset({"1280:720", "720:1280", "1104:832", "832:1104", "960:960", "1584:672"})
# Models verified against Runway Dev pricing page (2026-11-28):
#   gen4_image       — Gen-4 Image 720p  $0.05/image  = 5 credits
#   gen4_image_turbo — Gen-4 Image Turbo $0.02/image  = 2 credits
#   gen4_turbo       — Gen-4 Turbo       $0.05/second = 5 credits/second
ALLOWED_IMAGE_MODELS: frozenset[str] = frozenset({"gen4_image", "gen4_image_turbo"})
ALLOWED_VIDEO_MODELS: frozenset[str] = frozenset({"gen4_turbo"})

_BUDGET_LOCK = threading.Lock()


class CinemaApiError(RuntimeError):
    """Raised when a Cinema API request is misconfigured or fails (fail-closed)."""


# ---------------------------------------------------------------------------
# Configuration status
# ---------------------------------------------------------------------------

def configured_provider() -> str | None:
    """Return 'runway' if RUNWAYML_API_SECRET is set, else None."""
    if os.environ.get("RUNWAYML_API_SECRET", "").strip():
        return "runway"
    return None


def cinema_api_status() -> dict[str, Any]:
    """Return honest configuration and budget status for Cinema AI generation."""
    provider = configured_provider()
    status: dict[str, Any] = {
        "provider": provider,
        "configured": provider is not None,
        "env_var": "RUNWAYML_API_SECRET",
        "image_models": sorted(ALLOWED_IMAGE_MODELS),
        "video_models": sorted(ALLOWED_VIDEO_MODELS),
        "secret_guard": guard_status(),
    }
    try:
        status["budget"] = budget_status()
    except CinemaApiError as exc:
        status["budget"] = {"ok": False, "error": str(exc)}
    return status


# ---------------------------------------------------------------------------
# Daily credit budget (reserve before call, refund on failure)
# ---------------------------------------------------------------------------

def daily_cap_credits() -> int | None:
    """Return optional daily credit cap if DUP_CINEMA_DAILY_CREDITS is set, else None (unlimited)."""
    raw = os.environ.get("DUP_CINEMA_DAILY_CREDITS", "").strip()
    if not raw:
        return DEFAULT_DAILY_CAP_CREDITS
    try:
        value = int(raw)
    except ValueError as exc:
        raise CinemaApiError("DUP_CINEMA_DAILY_CREDITS должен быть целым числом") from exc
    if value < 0:
        raise CinemaApiError("DUP_CINEMA_DAILY_CREDITS не может быть отрицательным")
    return value


def estimate_credits(kind: str, model: str, duration: int = 0) -> int:
    """Credit cost per Runway Dev pricing (1 credit = $0.01)."""
    if kind == "image":
        if model not in ALLOWED_IMAGE_MODELS:
            raise CinemaApiError(f"Unsupported image model {model!r}")
        return 2 if model == "gen4_image_turbo" else 5
    if kind == "video":
        if model not in ALLOWED_VIDEO_MODELS:
            raise CinemaApiError(f"Unsupported video model {model!r}")
        if duration not in (5, 10):
            raise CinemaApiError("duration must be 5 or 10 seconds")
        return 5 * duration
    raise CinemaApiError("kind must be 'image' or 'video'")


def _utc_day() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def _read_budget_locked() -> dict[str, Any]:
    """Return today's ledger. Caller must hold _BUDGET_LOCK."""
    today = _utc_day()
    if not BUDGET_FILE.is_file():
        return {"day": today, "spent": 0, "log": []}
    try:
        data = json.loads(BUDGET_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CinemaApiError(f"cinema_budget.json повреждён, исправьте или удалите файл: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("spent"), int) or not isinstance(data.get("log"), list):
        raise CinemaApiError("cinema_budget.json имеет неверный формат")
    if data.get("day") != today:
        return {"day": today, "spent": 0, "log": data.get("log", [])[-50:]}
    return data


def _write_budget_locked(data: dict[str, Any]) -> None:
    BUDGET_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = BUDGET_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, BUDGET_FILE)


def budget_status() -> dict[str, Any]:
    cap = daily_cap_credits()
    with _BUDGET_LOCK:
        data = _read_budget_locked()
    spent = int(data["spent"])
    return {
        "ok": True,
        "day_utc": data["day"],
        "cap_credits": cap,
        "unlimited": cap is None,
        "spent_credits": spent,
        "remaining_credits": None if cap is None else max(0, cap - spent),
        "cap_usd": None if cap is None else round(cap * CREDIT_USD, 2),
        "spent_usd": round(spent * CREDIT_USD, 2),
    }


def _reserve(cost: int, meta: dict[str, Any]) -> None:
    cap = daily_cap_credits()
    with _BUDGET_LOCK:
        data = _read_budget_locked()
        spent = int(data["spent"])
        if cap is not None and spent + cost > cap:
            raise CinemaApiError(
                f"Дневной лимит Runway исчерпан: нужно {cost} кредитов, осталось {max(0, cap - spent)} из {cap}"
            )
        data["spent"] = spent + cost
        data["log"].append({"ts": int(time.time()), "event": "reserve", "cost": cost, **meta})
        data["log"] = data["log"][-200:]
        _write_budget_locked(data)


def _release(cost: int, meta: dict[str, Any]) -> None:
    with _BUDGET_LOCK:
        data = _read_budget_locked()
        data["spent"] = max(0, int(data["spent"]) - cost)
        data["log"].append({"ts": int(time.time()), "event": "refund", "cost": cost, **meta})
        data["log"] = data["log"][-200:]
        _write_budget_locked(data)


def _with_budget(cost: int, meta: dict[str, Any], call: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    _reserve(cost, meta)
    try:
        return call()
    except BaseException:
        _release(cost, meta)
        raise


# ---------------------------------------------------------------------------
# Prompts (free, offline)
# ---------------------------------------------------------------------------

def build_cinema_prompts(
    topic: str,
    scenes: list[str],
    *,
    style: str = DEFAULT_CINEMA_STYLE,
) -> list[dict[str, str]]:
    """Build consistent image + image-to-video prompts for a list of scenes."""
    clean_topic = " ".join(str(topic or "").split()).strip()
    if not clean_topic:
        raise CinemaApiError("topic must not be empty")
    clean_scenes = [" ".join(str(s or "").split()).strip() for s in (scenes or [])]
    clean_scenes = [s for s in clean_scenes if s]
    if not clean_scenes:
        raise CinemaApiError("scenes must contain at least one non-empty scene description")
    clean_style = " ".join(str(style or DEFAULT_CINEMA_STYLE).split()).strip() or DEFAULT_CINEMA_STYLE

    out: list[dict[str, str]] = []
    for idx, scene in enumerate(clean_scenes):
        out.append(
            {
                "index": f"{idx:02d}",
                "scene": scene,
                "image_prompt": (
                    f"Generate one image now, without questions: {clean_topic} — {scene}. "
                    f"Style: {clean_style}"
                ),
                "video_prompt": f"{scene}, {DEFAULT_MOTION_SUFFIX}",
            }
        )
    return out


# ---------------------------------------------------------------------------
# Runway Dev API transport
# ---------------------------------------------------------------------------

def _require_runway_key() -> str:
    key = os.environ.get("RUNWAYML_API_SECRET", "").strip()
    if not key:
        raise CinemaApiError(
            "RUNWAYML_API_SECRET не задан. Задайте переменную окружения Windows RUNWAYML_API_SECRET и перезапустите сервер."
        )
    return key


def _runway_request(
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: float = DEFAULT_HTTP_TIMEOUT_SEC,
) -> dict[str, Any]:
    api_key = _require_runway_key()
    url = f"{RUNWAY_API_BASE}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "X-Runway-Version": RUNWAY_API_VERSION,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "DUP-Presenter/1.3",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = redact_secrets(exc.read().decode("utf-8", errors="replace")[:300])
        raise CinemaApiError(f"Runway API HTTP {exc.code}: {detail}") from exc
    except SecretLeakError:
        raise
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise CinemaApiError(f"Runway API request failed: {redact_secrets(str(exc))}") from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CinemaApiError(f"Runway API returned invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise CinemaApiError("Runway API returned non-object JSON payload")
    return parsed


def _poll_runway_task(
    task_id: str,
    *,
    poll_timeout_sec: float,
    poll_interval_sec: float = DEFAULT_POLL_INTERVAL_SEC,
) -> dict[str, Any]:
    deadline = time.monotonic() + max(5.0, float(poll_timeout_sec))
    while time.monotonic() < deadline:
        task = _runway_request("GET", f"/tasks/{task_id}")
        status = str(task.get("status") or "").upper()
        if status == "SUCCEEDED":
            return task
        if status in {"FAILED", "CANCELLED", "CANCELED"}:
            reason = str(task.get("failure") or task.get("failureCode") or status)
            raise CinemaApiError(f"Runway task {task_id} failed: {reason}")
        time.sleep(poll_interval_sec)
    raise CinemaApiError(f"Runway task {task_id} timed out after {poll_timeout_sec:.0f}s")


def _download_file(url: str, out_path: Path, *, timeout: float = 60.0) -> Path:
    if not str(url).startswith("https://"):
        raise CinemaApiError(f"Refusing non-HTTPS media URL: {url!r}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "DUP-Presenter/1.3"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            blob = resp.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise CinemaApiError(f"Failed to download generated media: {exc}") from exc
    if not blob:
        raise CinemaApiError("Downloaded media file is empty")
    out_path.write_bytes(blob)
    return out_path


def _encode_image_data_uri(image_path: Path) -> str:
    if not image_path.is_file():
        raise CinemaApiError(f"Source image not found: {image_path}")
    mime, _ = mimetypes.guess_type(str(image_path))
    if not mime or not mime.startswith("image/"):
        mime = "image/png"
    b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


# ---------------------------------------------------------------------------
# Paid generation (budget-gated)
# ---------------------------------------------------------------------------

def generate_image_runway(
    prompt: str,
    *,
    out_path: Path,
    ratio: str = "1280:720",
    model: str = "gen4_image",
    poll_timeout_sec: float = 180.0,
) -> dict[str, Any]:
    """Generate a single keyframe image via Runway Dev API and save to `out_path`."""
    clean_prompt = " ".join(str(prompt or "").split()).strip()
    if not clean_prompt:
        raise CinemaApiError("prompt must not be empty")
    assert_no_secrets_in_text(clean_prompt, context="Runway image prompt")
    if ratio not in ALLOWED_RATIOS:
        raise CinemaApiError(f"Unsupported ratio {ratio!r}; allowed: {sorted(ALLOWED_RATIOS)}")
    cost = estimate_credits("image", model)
    meta = {"kind": "image", "model": model, "out": str(out_path)}

    def _call() -> dict[str, Any]:
        created = _runway_request(
            "POST",
            "/text_to_image",
            payload={"model": model, "promptText": clean_prompt, "ratio": ratio},
        )
        task_id = str(created.get("id") or "").strip()
        if not task_id:
            raise CinemaApiError("Runway API response missing task 'id'")
        finished = _poll_runway_task(task_id, poll_timeout_sec=poll_timeout_sec)
        outputs = finished.get("output")
        if not isinstance(outputs, list) or not outputs or not isinstance(outputs[0], str):
            raise CinemaApiError(f"Runway task {task_id} succeeded without output URL")
        saved = _download_file(outputs[0], Path(out_path))
        return {
            "ok": True,
            "provider": "runway",
            "kind": "image",
            "model": model,
            "task_id": task_id,
            "path": str(saved),
            "bytes": saved.stat().st_size,
            "credits": cost,
        }

    return _with_budget(cost, meta, _call)


def generate_video_runway(
    image_source: str | Path,
    prompt: str,
    *,
    out_path: Path,
    duration: int = 5,
    ratio: str = "1280:720",
    model: str = "gen4_turbo",
    poll_timeout_sec: float = 300.0,
) -> dict[str, Any]:
    """Animate a keyframe image into a video clip via Runway Dev API and save to `out_path`."""
    clean_prompt = " ".join(str(prompt or "").split()).strip()
    if not clean_prompt:
        raise CinemaApiError("prompt must not be empty")
    assert_no_secrets_in_text(clean_prompt, context="Runway video prompt")
    if ratio not in ALLOWED_RATIOS:
        raise CinemaApiError(f"Unsupported ratio {ratio!r}; allowed: {sorted(ALLOWED_RATIOS)}")
    cost = estimate_credits("video", model, duration)
    meta = {"kind": "video", "model": model, "duration": duration, "out": str(out_path)}

    if isinstance(image_source, Path) or not str(image_source).startswith(("https://", "data:image/")):
        prompt_image = _encode_image_data_uri(Path(image_source))
    else:
        prompt_image = str(image_source)

    def _call() -> dict[str, Any]:
        created = _runway_request(
            "POST",
            "/image_to_video",
            payload={
                "model": model,
                "promptImage": prompt_image,
                "promptText": clean_prompt,
                "duration": duration,
                "ratio": ratio,
            },
        )
        task_id = str(created.get("id") or "").strip()
        if not task_id:
            raise CinemaApiError("Runway API response missing task 'id'")
        finished = _poll_runway_task(task_id, poll_timeout_sec=poll_timeout_sec)
        outputs = finished.get("output")
        if not isinstance(outputs, list) or not outputs or not isinstance(outputs[0], str):
            raise CinemaApiError(f"Runway task {task_id} succeeded without output URL")
        saved = _download_file(outputs[0], Path(out_path))
        return {
            "ok": True,
            "provider": "runway",
            "kind": "video",
            "model": model,
            "task_id": task_id,
            "path": str(saved),
            "bytes": saved.stat().st_size,
            "credits": cost,
        }

    return _with_budget(cost, meta, _call)


def generate_batch_runway(
    scenes: list[str],
    *,
    topic: str,
    out_dir: Path,
    make_video: bool = False,
    duration: int = 5,
    ratio: str = "1280:720",
    image_model: str = "gen4_image",
    video_model: str = "gen4_turbo",
) -> dict[str, Any]:
    """Generate keyframes (and optionally clips) for a list of scenes within the daily budget.

    Pre-checks the whole batch against the remaining budget before the first paid call.
    Stops at the first failure and reports what was already produced.
    """
    prompts = build_cinema_prompts(topic, scenes)
    per_scene = estimate_credits("image", image_model)
    if make_video:
        per_scene += estimate_credits("video", video_model, duration)
    total = per_scene * len(prompts)
    status = budget_status()
    if status["remaining_credits"] is not None and total > status["remaining_credits"]:
        raise CinemaApiError(
            f"Серия стоит {total} кредитов ({len(prompts)} сцен × {per_scene}), "
            f"а на сегодня осталось {status['remaining_credits']} из {status['cap_credits']}. "
            "Уменьшите число сцен или отключите видео."
        )

    results: list[dict[str, Any]] = []
    for item in prompts:
        idx = item["index"]
        entry: dict[str, Any] = {"index": idx, "scene": item["scene"]}
        try:
            img = generate_image_runway(
                item["image_prompt"], out_path=out_dir / f"{idx}_keyframe.png", ratio=ratio, model=image_model
            )
            entry["image"] = img
            if make_video:
                vid = generate_video_runway(
                    Path(img["path"]),
                    item["video_prompt"],
                    out_path=out_dir / f"{idx}_clip.mp4",
                    duration=duration,
                    ratio=ratio,
                    model=video_model,
                )
                entry["video"] = vid
        except CinemaApiError as exc:
            entry["error"] = str(exc)
            results.append(entry)
            return {"ok": False, "stopped_at": idx, "results": results, "budget": budget_status()}
        results.append(entry)
    return {"ok": True, "results": results, "budget": budget_status()}
