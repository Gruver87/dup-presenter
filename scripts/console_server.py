"""DUP Presenter — local web console (127.0.0.1 only).

Provides a browser control room to:
  - pick a project folder and generate a full presentation MP4;
  - preview the rendered MP4 and inspect every slide;
  - send natural-language feedback to revise the deck and re-render;
  - switch voice speaker (eugene / xenia) and re-render;
  - watch live build logs and version history.

Security:
  - binds strictly to 127.0.0.1 (never 0.0.0.0);
  - no wildcard CORS;
  - slug is validated with a strict regex (no path traversal);
  - API keys are never returned or logged.

Usage:
    python scripts/console_server.py --port 8790
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
UI_HTML = SCRIPTS / "console_ui.html"
DECKS_DIR = ROOT / "decks"
OUT_DIR = ROOT / "out"
WORK_DIR = ROOT / "work"

sys.path.insert(0, str(SCRIPTS))
from build_deck import (  # noqa: E402
    ALLOWED_CAPTION_STYLES,
    ALLOWED_SPEAKERS,
    ALLOWED_SPEAKERS_BY_LANG,
    ALLOWED_THEMES,
    ASPECT_DIMS,
    DeckValidationError,
    validate_deck,
)
from director_presets import DirectorPresetError, PRESET_CATALOG, apply_director_preset  # noqa: E402
from fetch_repo import RepoFetchError, looks_like_remote, normalize_git_url  # noqa: E402
from idea_engine import GENRE_CATALOG, IdeaDeckExistsError, IdeaEngineError, auto_fix_deck, critique_deck, generate_ideas, write_idea_deck  # noqa: E402
from md_deck import MarkdownDeckError, MarkdownDeckExists, MarkdownImportError, write_deck_from_markdown  # noqa: E402
from plan_deck import voice_ssml  # noqa: E402
from thumbnail_studio import ThumbnailError, build_thumbnail_props, render_thumbnail  # noqa: E402
from tiktok_uploader import EXIT_PENDING as TIKTOK_EXIT_PENDING, refresh_access_token as tiktok_refresh, tiktok_status  # noqa: E402
from video_pack import VideoPackError, pack_cli_args, plan_video_pack  # noqa: E402
from storyboard_gate import StoryboardGateError, approve as sb_approve, gate_status, revoke as sb_revoke, storyboard_view  # noqa: E402
from asset_store import (  # noqa: E402
    AssetStoreError,
    MAX_UPLOAD_BYTES,
    PUBLIC_DIR as ASSETS_PUBLIC_DIR,
    bind_asset_to_slide,
    inspect_asset,
    save_from_url,
    save_uploaded_bytes,
    search_free_archives,
    unlicensed_deck_assets,
    update_asset_meta,
)
from web_search import configured_provider as web_search_provider  # noqa: E402
from studio_3d import (  # noqa: E402
    MAX_GLB_BYTES,
    MAX_IMG_BYTES,
    Studio3DError,
    configured_provider as studio_3d_provider,
    generate_glb as studio_3d_generate,
    list_models as studio_3d_list,
    save_glb_bytes as studio_3d_save_glb,
)

from theme_catalog import THEME_CATALOG  # noqa: E402
from tts_engines import KOKORO_DEFAULT, KOKORO_VOICE_CATALOG  # noqa: E402

VOICE_CATALOG = {
    "ru": [
        {"id": "dmitry", "label": "Dmitry — мужской (онлайн, нужен интернет; офлайн → Eugene)"},
        {"id": "svetlana", "label": "Svetlana — женский (онлайн, нужен интернет; офлайн → Eugene)"},
        {"id": "eugene", "label": "Eugene — мужской (офлайн)"},
        {"id": "xenia", "label": "Xenia — женский (чистый)"},
        {"id": "aidar", "label": "Aidar — мужской"},
        {"id": "baya", "label": "Baya — женский"},
        {"id": "kseniya", "label": "Kseniya — женский"},
    ],
    "en": [
        *[{"id": v["id"], "label": f"Kokoro · {v['label']}"} for v in KOKORO_VOICE_CATALOG],
        {"id": "en_1", "label": "Silero v3 · en_1 — Male (запасной)"},
        {"id": "en_0", "label": "Silero v3 · en_0 — Female (запасной)"},
        {"id": "en_5", "label": "Silero v3 · en_5 — Male (deep, запасной)"},
        {"id": "en_2", "label": "Silero v3 · en_2 — Female (soft, запасной)"},
    ],
}

SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def _load_user_env_into_os() -> None:
    """On Windows, refresh provider keys from User registry env so a newly set key works without relaunch."""
    if os.name != "nt":
        return
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            for name in (
                "DUP_LLM_BASE_URL", "DUP_LLM_MODEL", "DUP_LLM_API_KEY",
                "SERPER_API_KEY", "BRAVE_API_KEY", "TRIPO_API_KEY", "FAL_KEY",
            ):
                if not os.environ.get(name):
                    try:
                        val, _ = winreg.QueryValueEx(key, name)
                        if val:
                            os.environ[name] = str(val)
                    except FileNotFoundError:
                        pass
    except OSError:
        pass


def _valid_slug(slug: str) -> str:
    s = (slug or "").strip()
    if not SLUG_RE.match(s):
        raise ValueError("Slug must be 1..64 Latin letters, digits, '_' or '-'")
    return s


class JobRunner:
    """Single-slot background runner for deck build / plan / feedback commands."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.status = "idle"  # idle | running | ok | error
        self.step = ""
        self.slug = ""
        self.started_at = 0.0
        self.finished_at = 0.0
        self.exit_code: int | None = None
        self.lines: list[str] = []

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "status": self.status,
                "step": self.step,
                "slug": self.slug,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "exit_code": self.exit_code,
                "log": "\n".join(self.lines[-200:]),
            }

    def start(self, step: str, slug: str, cmd: list[str]) -> bool:
        with self._lock:
            if self.status == "running":
                return False
            self.status = "running"
            self.step = step
            self.slug = slug
            self.started_at = time.time()
            self.finished_at = 0.0
            self.exit_code = None
            self.lines = [f"[{step}] starting..."]

        t = threading.Thread(target=self._run, args=(cmd,), daemon=True)
        t.start()
        return True

    def _run(self, cmd: list[str]) -> None:
        _load_user_env_into_os()
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                with self._lock:
                    self.lines.append(line.rstrip())
                    if len(self.lines) > 1000:
                        self.lines = self.lines[-600:]
            rc = proc.wait()
            with self._lock:
                self.exit_code = rc
                if rc == 0:
                    self.status = "ok"
                elif rc == TIKTOK_EXIT_PENDING and self.step.startswith("tiktok"):
                    # TikTok accepted the upload but has not confirmed it yet: not an error, re-check later.
                    self.status = "pending"
                else:
                    self.status = "error"
                self.finished_at = time.time()
                self.lines.append(f"[done] exit_code={rc}")
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self.exit_code = 1
                self.status = "error"
                self.finished_at = time.time()
                self.lines.append(f"[error] {exc}")


JOBS = JobRunner()


def list_videos() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not OUT_DIR.is_dir():
        return items
    for p in sorted(OUT_DIR.glob("*.mp4")):
        if p.name.startswith("."):
            continue
        slug = p.stem
        if not SLUG_RE.match(slug):
            continue
        items.append({
            "slug": slug,
            "file": p.name,
            "mb": round(p.stat().st_size / 1_048_576, 2),
            "mtime": int(p.stat().st_mtime),
            "has_srt": (OUT_DIR / f"{slug}.srt").is_file(),
            "has_vtt": (OUT_DIR / f"{slug}.vtt").is_file(),
            "has_thumb": (OUT_DIR / f"{slug}_thumb.png").is_file(),
        })
    return items


def list_decks() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not DECKS_DIR.is_dir():
        return items
    for p in sorted(DECKS_DIR.glob("*.json")):
        slug = p.stem
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        mp4 = OUT_DIR / f"{slug}.mp4"
        versions_dir = WORK_DIR / slug / "versions"
        versions = sorted(v.stem for v in versions_dir.glob("v*.json")) if versions_dir.is_dir() else []
        items.append({
            "slug": slug,
            "brand": data.get("brand", ""),
            "slides_count": len(data.get("slides") or []),
            "speaker": (data.get("voice") or {}).get("speaker", "dmitry"),
            "has_mp4": mp4.is_file(),
            "mp4_mb": round(mp4.stat().st_size / 1_048_576, 2) if mp4.is_file() else 0.0,
            "mp4_mtime": int(mp4.stat().st_mtime) if mp4.is_file() else 0,
            "versions_count": len(versions),
        })
    return items


def _wav_waveform(wav_path: Path, bins: int = 24) -> tuple[float, list[float]]:
    """Compute (duration_sec, normalized_peak_bars[bins]) from a local 16-bit PCM WAV."""
    import wave
    import numpy as np

    try:
        with wave.open(str(wav_path), "rb") as wf:
            fr = wf.getframerate() or 24000
            n_frames = wf.getnframes()
            ch = wf.getnchannels() or 1
            sw = wf.getsampwidth()
            raw = wf.readframes(n_frames)
        dur = round(n_frames / float(fr), 2) if n_frames > 0 else 0.0
        if not raw or sw != 2:
            return dur, [0.25] * bins
        arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        if ch > 1:
            arr = arr.reshape(-1, ch).mean(axis=1)
        arr = np.abs(arr)
        peak = float(arr.max()) if arr.size else 0.0
        if peak <= 0.0 or arr.size < bins:
            return dur, [0.15] * bins
        chunks = np.array_split(arr, bins)
        bars = [round(max(0.08, float(c.max()) / peak), 2) for c in chunks]
        return dur, bars
    except Exception:
        return 0.0, []


def build_timeline(slug: str, deck: dict[str, Any]) -> list[dict[str, Any]]:
    """Build per-slide timeline blocks with real voice WAV duration + waveform when available."""
    voice_dir = ASSETS_PUBLIC_DIR / "voice"
    items: list[dict[str, Any]] = []
    running = 0.0
    for idx, s in enumerate(deck.get("slides") or []):
        sid = str(s.get("id") or f"s{idx + 1}")
        wav = voice_dir / f"{slug}_{sid}.wav"
        has_audio = wav.is_file()
        peaks: list[float] = []
        if has_audio:
            dur, peaks = _wav_waveform(wav, bins=24)
            if dur <= 0.0:
                dur = 4.0
        else:
            text = str(s.get("voice_text") or "")
            words = len(text.split())
            dur = max(3.5, round(words / 2.3 + 1.2, 1))
        items.append({
            "index": idx,
            "id": sid,
            "type": str(s.get("type") or ""),
            "title": str(s.get("title") or sid),
            "start_sec": round(running, 2),
            "duration_sec": dur,
            "has_audio": has_audio,
            "audio_url": f"/voice/{slug}/{sid}.wav?t={int(wav.stat().st_mtime)}" if has_audio else "",
            "peaks": peaks,
        })
        running += dur
    return items


def read_deck_detail(slug: str) -> dict[str, Any]:
    slug = _valid_slug(slug)
    deck_path = DECKS_DIR / f"{slug}.json"
    if not deck_path.is_file():
        raise FileNotFoundError(f"Deck not found: {slug}")
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    hist_path = WORK_DIR / slug / "history.jsonl"
    history: list[dict[str, Any]] = []
    if hist_path.is_file():
        for ln in hist_path.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if ln:
                try:
                    history.append(json.loads(ln))
                except json.JSONDecodeError:
                    pass
    mp4 = OUT_DIR / f"{slug}.mp4"
    draft_mp4 = OUT_DIR / f"{slug}_draft.mp4"
    srt = OUT_DIR / f"{slug}.srt"
    vtt = OUT_DIR / f"{slug}.vtt"
    thumb = OUT_DIR / f"{slug}_thumb.png"
    cover = OUT_DIR / f"{slug}_cover.png"
    post_copy = OUT_DIR / f"{slug}_post_copy.md"
    chapters = OUT_DIR / f"{slug}_chapters.txt"
    metadata = OUT_DIR / f"{slug}_metadata.json"
    qa_path = OUT_DIR / f"{slug}_qa.json"
    credits = OUT_DIR / f"{slug}_visual_credits.txt"
    qa_summary: dict[str, Any] | None = None
    if qa_path.is_file():
        try:
            qr = json.loads(qa_path.read_text(encoding="utf-8"))
            # media_qa writes loudness under "audio" (integrated_lufs / true_peak_dbtp).
            audio_qa = qr.get("audio") or {}
            qa_summary = {
                "ok": bool(qr.get("ok")),
                "lufs": audio_qa.get("integrated_lufs"),
                "true_peak_db": audio_qa.get("true_peak_dbtp"),
            }
        except (OSError, json.JSONDecodeError):
            qa_summary = None
    return {
        "ok": True,
        "slug": slug,
        "deck": deck,
        "history": history,
        "has_mp4": mp4.is_file(),
        "mp4_mtime": int(mp4.stat().st_mtime) if mp4.is_file() else 0,
        "has_draft": draft_mp4.is_file(),
        "draft_mtime": int(draft_mp4.stat().st_mtime) if draft_mp4.is_file() else 0,
        "has_srt": srt.is_file(),
        "has_vtt": vtt.is_file(),
        "has_thumb": thumb.is_file(),
        "thumb_mtime": int(thumb.stat().st_mtime) if thumb.is_file() else 0,
        "has_cover": cover.is_file(),
        "cover_mtime": int(cover.stat().st_mtime) if cover.is_file() else 0,
        "has_post_copy": post_copy.is_file(),
        "has_chapters": chapters.is_file(),
        "has_metadata": metadata.is_file(),
        "has_qa": qa_path.is_file(),
        "qa_summary": qa_summary,
        "has_credits": credits.is_file(),
        "timeline": build_timeline(slug, deck),
    }


OLLAMA_TAGS_URL = "http://127.0.0.1:11434/api/tags"


def _find_ollama_exe() -> str | None:
    """Locate ollama executable in PATH or standard Windows install folder."""
    found = shutil.which("ollama")
    if found:
        return found
    if os.name == "nt":
        local_app = os.environ.get("LOCALAPPDATA", "")
        if local_app:
            candidate = Path(local_app) / "Programs" / "Ollama" / "ollama.exe"
            if candidate.is_file():
                return str(candidate)
    return None


def _probe_ollama(timeout: float = 2.0) -> tuple[bool, list[str]]:
    """Return (online, installed_model_names) from local Ollama daemon."""
    try:
        with urllib.request.urlopen(OLLAMA_TAGS_URL, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        names = [m["name"] for m in data.get("models") or [] if m.get("name")]
        return True, names
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return False, []


def ensure_ollama_running(wait_sec: float = 8.0) -> dict[str, Any]:
    """Start local `ollama serve` in background if installed and currently offline."""
    online, models = _probe_ollama(timeout=1.5)
    if online:
        return {"online": True, "started": False, "installed": True, "models": models}
    exe = _find_ollama_exe()
    if not exe:
        return {"online": False, "started": False, "installed": False, "models": []}
    creationflags = 0
    if os.name == "nt":
        creationflags = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
        )
    try:
        subprocess.Popen(
            [exe, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
        )
    except OSError:
        return {"online": False, "started": False, "installed": True, "models": []}

    deadline = time.time() + wait_sec
    while time.time() < deadline:
        time.sleep(0.5)
        online, models = _probe_ollama(timeout=1.2)
        if online:
            return {"online": True, "started": True, "installed": True, "models": models}
    return {"online": False, "started": True, "installed": True, "models": []}


def system_status(ollama_online: bool | None = None, ollama_models: list[str] | None = None) -> dict[str, Any]:
    """Honest on-disk and local-daemon health snapshot for all Presenter components."""
    _load_user_env_into_os()
    if ollama_online is None or ollama_models is None:
        ollama_online, ollama_models = _probe_ollama(timeout=1.5)
    has_key = bool(os.environ.get("DUP_LLM_API_KEY"))
    silero_dir = ROOT / "models" / "silero"
    ffmpeg_ok = (ROOT / "node_modules" / "@remotion" / "compositor-win32-x64-msvc" / "ffmpeg.exe").is_file() or bool(shutil.which("ffmpeg"))
    remotion_ok = (ROOT / "node_modules" / ".bin" / "remotion.cmd").is_file() or (ROOT / "node_modules" / ".bin" / "remotion").is_file()
    return {
        "cloud_configured": has_key,
        "cloud_model": os.environ.get("DUP_LLM_MODEL", "") if has_key else "",
        "ollama_installed": bool(_find_ollama_exe()),
        "ollama_online": ollama_online,
        "ollama_models": ollama_models,
        "silero_ru_ready": (silero_dir / "v5_ru.pt").is_file(),
        "silero_en_ready": (silero_dir / "v3_en.pt").is_file(),
        "ffmpeg_ready": ffmpeg_ok,
        "remotion_ready": remotion_ok,
        "git_ready": bool(shutil.which("git")),
        "tiktok": tiktok_status(),
        "web_search_provider": web_search_provider(),
        "studio_3d_provider": studio_3d_provider(),
    }


def bootstrap_environment(start_ollama: bool = True) -> dict[str, Any]:
    """Auto-load env, auto-start Ollama if installed & offline, auto-refresh TikTok if possible."""
    _load_user_env_into_os()
    tt = tiktok_status()
    if tt.get("can_auto_refresh") and not tt.get("access_token_set"):
        tiktok_refresh(persist=True)
    if start_ollama:
        ol = ensure_ollama_running(wait_sec=8.0)
        return system_status(ollama_online=ol["online"], ollama_models=ol["models"])
    return system_status()


def provider_info() -> dict[str, Any]:
    _load_user_env_into_os()
    has_key = bool(os.environ.get("DUP_LLM_API_KEY"))
    env_model = os.environ.get("DUP_LLM_MODEL", "") if has_key else ""
    cloud_models = ["deepseek-chat", "deepseek-reasoner", "gpt-4o", "gpt-4o-mini", "qwen/qwen-2.5-72b-instruct"]
    if env_model and env_model not in cloud_models:
        cloud_models.insert(0, env_model)
    elif env_model:
        cloud_models.remove(env_model)
        cloud_models.insert(0, env_model)
    ollama_online, live_models = _probe_ollama(timeout=1.5)
    ollama_models = live_models if live_models else ["qwen2.5:14b", "qwen2.5:7b"]
    sys_info = system_status(ollama_online=ollama_online, ollama_models=live_models)
    return {
        "default_provider": "cloud" if has_key else "ollama",
        "cloud_configured": has_key,
        "cloud_model": env_model,
        "cloud_models": cloud_models,
        "ollama_online": ollama_online,
        "ollama_model": ollama_models[0],
        "ollama_models": ollama_models,
        "system": sys_info,
        "voices": VOICE_CATALOG,
        "themes": THEME_CATALOG,
        "aspects": list(ASPECT_DIMS.keys()),
        "speakers": sorted(ALLOWED_SPEAKERS),
    }


class ConsoleHandler(BaseHTTPRequestHandler):
    server_version = "DUPPresenterConsole/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        pass

    def _json(self, code: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _refuse(self, code: int, payload: dict[str, Any]) -> None:
        """Refuse a request after draining its body.

        Answering 403 with an unread request body and closing the socket makes Windows send a TCP reset,
        so the client can lose the 403 and see ConnectionAbortedError. Draining first avoids that race.
        The drain is bounded by the same 2 MB cap used by _read_json.
        """
        n = int(self.headers.get("Content-Length") or 0)
        if 0 < n <= 2_000_000:
            self.rfile.read(n)
        self.close_connection = True
        self._json(code, payload)

    def _guard_local_request(self, *, state_changing: bool) -> bool:
        """Refuse DNS-rebinding (foreign Host) and cross-site POSTs from other browser tabs.

        Browsers attach Origin / Sec-Fetch-Site to cross-site requests; a "simple" text/plain POST
        needs no CORS preflight, so without this check any web page could trigger renders,
        deck overwrites or TikTok uploads on 127.0.0.1. Non-browser clients send no Origin.
        """
        port = self.server.server_address[1]
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
        host = (self.headers.get("Host") or "").strip().lower()
        if host not in allowed:
            self._refuse(403, {"ok": False, "error": "Forbidden: console accepts only 127.0.0.1 / localhost Host"})
            return False
        if state_changing:
            origin = (self.headers.get("Origin") or "").strip().lower()
            if origin and origin.removeprefix("http://") not in allowed:
                self._refuse(403, {"ok": False, "error": "Forbidden: cross-origin request refused"})
                return False
            fetch_site = (self.headers.get("Sec-Fetch-Site") or "").strip().lower()
            if fetch_site and fetch_site not in {"same-origin", "none"}:
                self._refuse(403, {"ok": False, "error": "Forbidden: cross-site request refused"})
                return False
        return True

    def _read_json(self) -> dict[str, Any]:
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > 2_000_000:
            return {}
        return json.loads(self.rfile.read(n).decode("utf-8"))

    def _serve_video(self, slug: str) -> None:
        try:
            slug = _valid_slug(slug)
        except ValueError:
            self._json(400, {"ok": False, "error": "Invalid slug"})
            return
        mp4 = OUT_DIR / f"{slug}.mp4"
        if not mp4.is_file():
            self._json(404, {"ok": False, "error": "MP4 not found"})
            return
        size = mp4.stat().st_size
        rng = self.headers.get("Range")
        start, end = 0, size - 1
        status = 200
        if rng and rng.startswith("bytes="):
            part = rng[6:].split(",")[0].strip()
            s_str, _, e_str = part.partition("-")
            if s_str:
                start = int(s_str)
            if e_str:
                end = min(int(e_str), size - 1)
            if start > end or start >= size:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            status = 206
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with mp4.open("rb") as fh:
            fh.seek(start)
            left = length
            while left > 0:
                chunk = fh.read(min(262_144, left))
                if not chunk:
                    break
                self.wfile.write(chunk)
                left -= len(chunk)

    def do_GET(self) -> None:  # noqa: N802
        if not self._guard_local_request(state_changing=False):
            return
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path in {"/", "/index.html"}:
            if not UI_HTML.is_file():
                self._json(500, {"ok": False, "error": "console_ui.html missing"})
                return
            data = UI_HTML.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if path == "/api/live":
            self._json(200, {"ok": True, "live": True, "product": "DUP Presenter Console"})
            return

        if path == "/api/state":
            self._json(200, {
                "ok": True,
                "decks": list_decks(),
                "videos": list_videos(),
                "provider": provider_info(),
                "genres": GENRE_CATALOG,
                "presets": PRESET_CATALOG,
                "job": JOBS.snapshot(),
            })
            return

        if path == "/api/storyboard":
            slug = (qs.get("slug") or [""])[0]
            try:
                slug = _valid_slug(slug)
                view = storyboard_view(slug)
            except (ValueError, StoryboardGateError) as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            self._json(200, {"ok": True, **view, "frames_base": f"/storyboard/{slug}/"})
            return

        sb_frame = re.match(r"^/storyboard/([A-Za-z0-9][A-Za-z0-9_-]{0,63})/([A-Za-z0-9_-]{1,64}\.jpg)$", path)
        if sb_frame:
            fpath = WORK_DIR / sb_frame.group(1) / "storyboard" / sb_frame.group(2)
            if not fpath.is_file():
                self._json(404, {"ok": False, "error": "Frame not found"})
                return
            data = fpath.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return

        if path == "/api/deck":
            slug = (qs.get("slug") or [""])[0]
            try:
                self._json(200, read_deck_detail(slug))
            except (ValueError, FileNotFoundError) as exc:
                self._json(404, {"ok": False, "error": str(exc)})
            return

        if path == "/api/pronunciation":
            from ru_speech import get_latin_ru, load_pronunciation_overrides  # noqa: E402

            self._json(200, {
                "ok": True,
                "overrides": load_pronunciation_overrides(),
                "merged": get_latin_ru(),
            })
            return

        if path.startswith("/video/") and path.endswith(".mp4"):
            slug = path[len("/video/"):-4]
            self._serve_video(slug)
            return

        if path.startswith("/out/"):
            fname = path[len("/out/"):]
            if not re.match(r"^[A-Za-z0-9_-]+(?:\.srt|\.vtt|_thumb\.png|_cover\.png|_chapters\.txt|_post_copy\.md|_metadata\.json|_qa\.json|_visual_credits\.txt)$", fname):
                self._json(400, {"ok": False, "error": "Invalid asset name"})
                return
            fpath = OUT_DIR / fname
            if not fpath.is_file():
                self._json(404, {"ok": False, "error": "Asset not found"})
                return
            ct = "image/png" if fname.endswith(".png") else ("text/vtt; charset=utf-8" if fname.endswith(".vtt") else "text/plain; charset=utf-8")
            data = fpath.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return

        if path == "/api/assets/inspect":
            qs = parse_qs(parsed.query)
            raw_slug = (qs.get("slug") or [""])[0]
            rel_file = (qs.get("file") or [""])[0]
            try:
                slug = _valid_slug(raw_slug)
                info = inspect_asset(slug, rel_file)
            except (ValueError, AssetStoreError) as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            self._json(200, {"ok": True, "asset": info})
            return

        if path == "/api/assets/search":
            qs = parse_qs(parsed.query)
            q = (qs.get("q") or [""])[0]
            kind = (qs.get("kind") or ["any"])[0]
            try:
                lim = int((qs.get("limit") or ["8"])[0])
            except ValueError:
                lim = 8
            try:
                res = search_free_archives(q, kind=kind, limit=lim)
            except AssetStoreError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            self._json(200, res)
            return

        if path == "/api/3d/models":
            self._json(200, {"ok": True, "provider": studio_3d_provider(), "models": studio_3d_list()})
            return

        if path.startswith("/voice/") and path.endswith(".wav"):
            parts = path[len("/voice/"):-4].split("/")
            if len(parts) != 2:
                self._json(400, {"ok": False, "error": "Invalid voice path"})
                return
            try:
                v_slug = _valid_slug(parts[0])
            except ValueError:
                self._json(400, {"ok": False, "error": "Invalid slug"})
                return
            sid = parts[1]
            if not re.match(r"^[A-Za-z0-9_-]{1,64}$", sid):
                self._json(400, {"ok": False, "error": "Invalid slide id"})
                return
            wpath = ASSETS_PUBLIC_DIR / "voice" / f"{v_slug}_{sid}.wav"
            if not wpath.is_file():
                self._json(404, {"ok": False, "error": "Voice WAV not found"})
                return
            data = wpath.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return

        if path.startswith("/public/"):
            rel = path[len("/public/"):]
            if not re.match(r"^(?:uploads|visual|cinema|screens|models3d)/[A-Za-z0-9_./-]+\.(?:jpg|jpeg|png|webp|mp4|webm|glb)$", rel, re.IGNORECASE) or ".." in rel.split("/"):
                self._json(400, {"ok": False, "error": "Invalid public media path"})
                return
            fpath = (ASSETS_PUBLIC_DIR / rel).resolve()
            if ASSETS_PUBLIC_DIR.resolve() not in fpath.parents or not fpath.is_file():
                self._json(404, {"ok": False, "error": "Media not found"})
                return
            ext = fpath.suffix.lower()
            ct_map = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".webp": "image/webp",
                ".mp4": "video/mp4",
                ".webm": "video/webm",
                ".glb": "model/gltf-binary",
            }
            data = fpath.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ct_map.get(ext, "application/octet-stream"))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return

        self._json(404, {"ok": False, "error": "Not found"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._guard_local_request(state_changing=True):
            return
        parsed = urlparse(self.path)
        path = parsed.path

        # Binary upload path for drag-and-drop files (up to MAX_UPLOAD_BYTES = 100 MB).
        if path == "/api/assets/upload" and "application/json" not in (self.headers.get("Content-Type") or "").lower():
            qs = parse_qs(parsed.query)
            raw_slug = (qs.get("slug") or [""])[0]
            slide_id = (qs.get("slide_id") or [""])[0].strip()
            filename = (qs.get("filename") or [""])[0].strip()
            try:
                slug = _valid_slug(raw_slug)
            except ValueError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if length <= 0:
                self._json(400, {"ok": False, "error": "Пустой запрос загрузки"})
                return
            if length > MAX_UPLOAD_BYTES:
                self._json(413, {"ok": False, "error": f"Файл превышает лимит {MAX_UPLOAD_BYTES // (1024 * 1024)} МБ"})
                return
            raw = self.rfile.read(length)
            try:
                asset = save_uploaded_bytes(slug, raw, filename=filename)
                if slide_id:
                    deck_path = DECKS_DIR / f"{slug}.json"
                    if not deck_path.is_file():
                        self._json(404, {"ok": False, "error": f"Колода не найдена: {slug}"})
                        return
                    deck = json.loads(deck_path.read_text(encoding="utf-8"))
                    updated = bind_asset_to_slide(deck, slide_id, asset)
                    deck_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            except AssetStoreError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            self._json(200, {"ok": True, "asset": asset, "bound_slide": slide_id or None})
            return

        # Binary upload of local .glb into 3D Studio (up to 50 MB).
        if path == "/api/3d/upload-glb":
            qs = parse_qs(parsed.query)
            filename = (qs.get("filename") or ["model.glb"])[0].strip()
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if length <= 0:
                self._json(400, {"ok": False, "error": "Пустой файл .glb"})
                return
            if length > MAX_GLB_BYTES:
                self._json(413, {"ok": False, "error": f".glb превышает лимит {MAX_GLB_BYTES // (1024 * 1024)} МБ"})
                return
            raw = self.rfile.read(length)
            try:
                model = studio_3d_save_glb(raw, name=Path(filename).stem or "model", source="local-upload")
            except Studio3DError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            self._json(200, {"ok": True, "model": model})
            return

        # Binary image upload -> external Image-to-3D API (Tripo3D / Fal.ai, fail-closed).
        if path == "/api/3d/generate":
            _load_user_env_into_os()
            qs = parse_qs(parsed.query)
            name = (qs.get("name") or ["model"])[0].strip()
            provider = (qs.get("provider") or ["auto"])[0].strip()
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if length <= 0:
                self._json(400, {"ok": False, "error": "Загрузи картинку (вид спереди) для генерации 3D"})
                return
            if length > MAX_IMG_BYTES:
                self._json(413, {"ok": False, "error": f"Картинка превышает лимит {MAX_IMG_BYTES // (1024 * 1024)} МБ"})
                return
            raw = self.rfile.read(length)
            try:
                model = studio_3d_generate(raw, name=name, provider=provider)
            except Studio3DError as exc:
                self._json(503 if "не настроен" in str(exc) else 502, {"ok": False, "error": str(exc)})
                return
            self._json(200, {"ok": True, "model": model})
            return

        try:
            body = self._read_json()
        except json.JSONDecodeError as exc:
            self._json(400, {"ok": False, "error": f"Invalid JSON: {exc}"})
            return

        if path == "/api/slides/reorder":
            try:
                slug = _valid_slug(str(body.get("slug") or ""))
            except ValueError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            order = body.get("order")
            if not isinstance(order, list) or not order:
                self._json(400, {"ok": False, "error": "Передай непустой список id слайдов в поле 'order'"})
                return
            deck_path = DECKS_DIR / f"{slug}.json"
            if not deck_path.is_file():
                self._json(404, {"ok": False, "error": f"Колода не найдена: {slug}"})
                return
            deck = json.loads(deck_path.read_text(encoding="utf-8"))
            slides = deck.get("slides") or []
            by_id = {str(s.get("id")): s for s in slides}
            req_ids = [str(x) for x in order]
            if len(req_ids) != len(slides) or set(req_ids) != set(by_id.keys()):
                self._json(400, {"ok": False, "error": "Список 'order' должен точно совпадать с текущими id слайдов"})
                return
            deck["slides"] = [by_id[sid] for sid in req_ids]
            try:
                validate_deck(deck)
            except DeckValidationError as exc:
                self._json(400, {"ok": False, "error": f"Валидация не прошла: {exc}"})
                return
            deck_path.write_text(json.dumps(deck, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self._json(200, {"ok": True, "slug": slug, "order": req_ids, "timeline": build_timeline(slug, deck)})
            return

        if path == "/api/assets/upload":
            try:
                slug = _valid_slug(str(body.get("slug") or ""))
            except ValueError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            slide_id = str(body.get("slide_id") or "").strip()
            url = str(body.get("url") or "").strip()
            meta = body.get("meta") if isinstance(body.get("meta"), dict) else {}
            if not url:
                self._json(400, {"ok": False, "error": "Укажи https:// ссылку (url) или отправь файл бинарно"})
                return
            try:
                asset = save_from_url(slug, url, meta=meta)
                if slide_id:
                    deck_path = DECKS_DIR / f"{slug}.json"
                    if not deck_path.is_file():
                        self._json(404, {"ok": False, "error": f"Колода не найдена: {slug}"})
                        return
                    deck = json.loads(deck_path.read_text(encoding="utf-8"))
                    updated = bind_asset_to_slide(deck, slide_id, asset)
                    deck_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            except AssetStoreError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            self._json(200, {"ok": True, "asset": asset, "bound_slide": slide_id or None})
            return

        if path == "/api/assets/meta":
            try:
                slug = _valid_slug(str(body.get("slug") or ""))
            except ValueError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            rel_file = str(body.get("file") or "").strip()
            patch = body.get("meta") if isinstance(body.get("meta"), dict) else body
            try:
                updated = update_asset_meta(slug, rel_file, patch)
            except AssetStoreError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            self._json(200, {"ok": True, "asset": updated})
            return

        if path == "/api/pick-folder":
            picker = SCRIPTS / "pick_folder.ps1"
            res = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(picker)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            chosen = (res.stdout or "").strip()
            self._json(200, {"ok": bool(chosen), "path": chosen})
            return

        if path == "/api/generate":
            source = str(body.get("folder") or "").strip()
            if not source:
                self._json(400, {"ok": False, "error": "Укажи локальную папку проекта или ссылку GitHub."})
                return
            suggested_slug = ""
            if looks_like_remote(source):
                try:
                    source, suggested_slug = normalize_git_url(source)
                except RepoFetchError as exc:
                    self._json(400, {"ok": False, "error": str(exc)})
                    return
            elif not Path(source).is_dir():
                self._json(400, {"ok": False, "error": f"Папка проекта не найдена: {source!r}"})
                return
            else:
                suggested_slug = Path(source).name
            try:
                slug = _valid_slug(str(body.get("slug") or suggested_slug))
            except ValueError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            provider = "cloud" if body.get("provider") == "cloud" else "ollama"
            lang = "en" if body.get("lang") == "en" else "ru"
            speaker = str(body.get("speaker") or (KOKORO_DEFAULT if lang == "en" else "dmitry")).strip()
            if speaker not in ALLOWED_SPEAKERS_BY_LANG[lang]:
                self._json(400, {"ok": False, "error": f"Голос {speaker!r} не подходит для языка {lang!r}"})
                return
            theme = str(body.get("theme") or "neon_cyber").strip()
            if theme not in ALLOWED_THEMES:
                self._json(400, {"ok": False, "error": f"Неизвестная тема: {theme}"})
                return
            aspect = "9:16" if body.get("aspect") == "9:16" else "16:9"
            voice_mode = "podcast" if body.get("voice_mode") == "podcast" else "single"
            burn_captions = body.get("burn_captions", True) is not False
            model = str(body.get("model") or "").strip()
            slides = int(body.get("slides") or 6)
            slides = max(3, min(12, slides))
            cmd = [
                sys.executable, str(SCRIPTS / "make_project_deck.py"),
                source, "--slug", slug, "--provider", provider, "--slides", str(slides),
                "--lang", lang, "--speaker", speaker, "--theme", theme,
                "--aspect", aspect, "--voice-mode", voice_mode, "--render", "--draft",
            ]
            if not burn_captions:
                cmd.append("--no-captions")
            if model:
                cmd += ["--model", model]
            if not JOBS.start("generate", slug, cmd):
                self._json(409, {"ok": False, "error": "Уже идёт другая сборка. Дождись её завершения."})
                return
            self._json(202, {"ok": True, "slug": slug, "step": "generate"})
            return

        if path == "/api/feedback":
            try:
                slug = _valid_slug(str(body.get("slug") or ""))
            except ValueError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            feedback = str(body.get("feedback") or "").strip()
            if not feedback:
                self._json(400, {"ok": False, "error": "Напиши, что нужно поменять в ролике."})
                return
            provider = "cloud" if body.get("provider") == "cloud" else "ollama"
            lang = "en" if body.get("lang") == "en" else "ru"
            speaker = str(body.get("speaker") or "").strip()
            theme = str(body.get("theme") or "neon_cyber").strip()
            aspect = "9:16" if body.get("aspect") == "9:16" else "16:9"
            voice_mode = "podcast" if body.get("voice_mode") == "podcast" else "single"
            burn_captions = body.get("burn_captions", True) is not False
            model = str(body.get("model") or "").strip()
            cmd = [
                sys.executable, str(SCRIPTS / "make_project_deck.py"),
                "--slug", slug, "--feedback", feedback, "--provider", provider, "--lang", lang,
                "--theme", theme, "--aspect", aspect, "--voice-mode", voice_mode, "--render", "--draft",
            ]
            if speaker:
                cmd += ["--speaker", speaker]
            if not burn_captions:
                cmd.append("--no-captions")
            if model:
                cmd += ["--model", model]
            if not JOBS.start("feedback", slug, cmd):
                self._json(409, {"ok": False, "error": "Уже идёт другая сборка. Дождись её завершения."})
                return
            self._json(202, {"ok": True, "slug": slug, "step": "feedback"})
            return

        if path == "/api/import-md":
            markdown = str(body.get("markdown") or "")
            if not markdown.strip():
                self._json(400, {"ok": False, "error": "Вставь Markdown-текст с блоком front matter (slug, lang и слайды)."})
                return
            try:
                deck = write_deck_from_markdown(markdown, DECKS_DIR)
            except MarkdownDeckExists as exc:
                self._json(409, {"ok": False, "error": str(exc)})
                return
            except MarkdownImportError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            except MarkdownDeckError as exc:
                self._json(400, {"ok": False, "error": f"Markdown не разобран: {exc}"})
                return
            self._json(200, {"ok": True, "slug": deck["slug"]})
            return

        if path == "/api/ideas":
            _load_user_env_into_os()
            topic = str(body.get("topic") or "").strip()
            lang = str(body.get("lang") or "ru").strip().lower()
            genre = str(body.get("genre") or "all").strip().lower()
            mode = str(body.get("mode") or "template").strip().lower()
            model = str(body.get("model") or "").strip()
            try:
                count = int(body.get("count") or 5)
            except (TypeError, ValueError):
                self._json(400, {"ok": False, "error": "count должен быть числом от 1 до 7"})
                return
            web_search = bool(body.get("web_search", False))
            try:
                res = generate_ideas(
                    topic, lang=lang, genre=genre, count=count, mode=mode, model=model, web_search=web_search
                )
            except IdeaEngineError as exc:
                self._json(400 if (mode == "template" or web_search) else 502, {"ok": False, "error": str(exc)})
                return
            self._json(200, res)
            return

        if path == "/api/ideas/to-deck":
            idea = body.get("idea")
            slug = str(body.get("slug") or "").strip()
            overwrite = bool(body.get("overwrite", False))
            try:
                deck, deck_path = write_idea_deck(idea, DECKS_DIR, slug=slug, overwrite=overwrite)
            except IdeaDeckExistsError as exc:
                self._json(409, {"ok": False, "error": str(exc)})
                return
            except (IdeaEngineError, DeckValidationError) as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            self._json(200, {"ok": True, "slug": deck["slug"], "path": str(deck_path)})
            return

        if path == "/api/critique":
            try:
                slug = _valid_slug(str(body.get("slug") or ""))
            except ValueError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            deck_path = DECKS_DIR / f"{slug}.json"
            if not deck_path.is_file():
                self._json(404, {"ok": False, "error": f"Колода не найдена: {slug}"})
                return
            try:
                deck = json.loads(deck_path.read_text(encoding="utf-8"))
                report = critique_deck(deck, lang=str(body.get("lang") or ""))
            except IdeaEngineError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            self._json(200, report)
            return

        if path == "/api/critique/autofix":
            try:
                slug = _valid_slug(str(body.get("slug") or ""))
            except ValueError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            deck_path = DECKS_DIR / f"{slug}.json"
            if not deck_path.is_file():
                self._json(404, {"ok": False, "error": f"Колода не найдена: {slug}"})
                return
            try:
                deck = json.loads(deck_path.read_text(encoding="utf-8"))
                fixed, changes = auto_fix_deck(deck)
                deck_path.write_text(json.dumps(fixed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            except (IdeaEngineError, DeckValidationError) as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            self._json(200, {"ok": True, "slug": slug, "changes": changes, "critique": critique_deck(fixed)})
            return

        if path == "/api/apply-preset":
            try:
                slug = _valid_slug(str(body.get("slug") or ""))
            except ValueError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            preset_id = str(body.get("preset") or "").strip()
            deck_path = DECKS_DIR / f"{slug}.json"
            if not deck_path.is_file():
                self._json(404, {"ok": False, "error": f"Колода не найдена: {slug}"})
                return
            try:
                deck = json.loads(deck_path.read_text(encoding="utf-8"))
                updated = apply_director_preset(deck, preset_id, override_existing=True)
                validate_deck(updated)
                deck_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            except (DirectorPresetError, DeckValidationError) as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            self._json(200, {"ok": True, "slug": slug, "preset": preset_id})
            return

        if path == "/api/thumbnail":
            try:
                slug = _valid_slug(str(body.get("slug") or ""))
            except ValueError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            deck_path = DECKS_DIR / f"{slug}.json"
            if not deck_path.is_file():
                self._json(404, {"ok": False, "error": f"Колода не найдена: {slug}"})
                return
            try:
                deck = json.loads(deck_path.read_text(encoding="utf-8"))
                props = build_thumbnail_props(
                    deck=deck,
                    accent_badge=str(body.get("badge") or ""),
                )
                out_png = OUT_DIR / f"{slug}_cover.png"
                res = render_thumbnail(out_png, props, dry_run=False)
            except ThumbnailError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            self._json(200, res)
            return

        if path == "/api/video-pack/plan":
            try:
                slug = _valid_slug(str(body.get("slug") or ""))
            except ValueError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            deck_path = DECKS_DIR / f"{slug}.json"
            if not deck_path.is_file():
                self._json(404, {"ok": False, "error": f"Колода не найдена: {slug}"})
                return
            try:
                plan = plan_video_pack(
                    deck_path,
                    include_short=bool(body.get("include_short", True)),
                    include_thumbnail=bool(body.get("include_thumbnail", True)),
                    translate_to=str(body.get("translate_to") or ""),
                    preset=str(body.get("preset") or ""),
                )
            except (VideoPackError, DirectorPresetError, DeckValidationError) as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            self._json(200, plan)
            return

        if path == "/api/video-pack/build":
            try:
                slug = _valid_slug(str(body.get("slug") or ""))
            except ValueError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            deck_path = DECKS_DIR / f"{slug}.json"
            if not deck_path.is_file():
                self._json(404, {"ok": False, "error": f"Колода не найдена: {slug}"})
                return
            # Fail-closed: video_pack renders master with --require-storyboard, so check the gate up front.
            try:
                sb_status = gate_status(slug)
            except StoryboardGateError as exc:
                self._json(409, {"ok": False, "error": str(exc)})
                return
            if not sb_status["can_master"]:
                self._json(409, {"ok": False, "error": f"Video Pack заблокирован: {sb_status['reason']}", "storyboard": sb_status})
                return
            # Never replace existing MP4s implicitly: overwrite only on explicit opt-in.
            cmd = [
                sys.executable,
                str(SCRIPTS / "video_pack.py"),
                *pack_cli_args(
                    deck_path,
                    include_short=bool(body.get("include_short", True)),
                    include_thumbnail=bool(body.get("include_thumbnail", True)),
                    translate_to=str(body.get("translate_to") or "").strip(),
                    overwrite=body.get("overwrite") is True,
                ),
            ]
            if not JOBS.start("video_pack", slug, cmd):
                self._json(409, {"ok": False, "error": "Уже идёт сборка. Дождись окончания в «Логах»."})
                return
            self._json(202, {"ok": True, "slug": slug, "step": "video_pack"})
            return

        if path == "/api/save-deck":
            try:
                slug = _valid_slug(str(body.get("slug") or ""))
            except ValueError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            deck_path = DECKS_DIR / f"{slug}.json"
            if not deck_path.is_file():
                self._json(404, {"ok": False, "error": f"Колода не найдена: {slug}"})
                return
            deck = json.loads(deck_path.read_text(encoding="utf-8"))
            if "theme" in body and body["theme"] in ALLOWED_THEMES:
                deck["theme"] = body["theme"]
            if "aspect" in body and body["aspect"] in ASPECT_DIMS:
                # A format change rewrites the master's dimensions. Refuse unless explicitly confirmed, and
                # refuse before writing anything, so a stale console selector cannot silently re-aspect a deck.
                old_aspect = str(deck.get("aspect") or "16:9")
                if body["aspect"] != old_aspect and not bool(body.get("confirm_aspect_change")):
                    self._json(409, {
                        "ok": False,
                        "error": f"Смена формата {old_aspect} → {body['aspect']} не подтверждена. "
                                 "Сохранение отменено, файл не изменён.",
                    })
                    return
                deck["aspect"] = body["aspect"]
                deck["width"], deck["height"] = ASPECT_DIMS[body["aspect"]]
            if "burn_captions" in body:
                deck["burn_captions"] = bool(body["burn_captions"])
            if "caption_style" in body:
                style = str(body.get("caption_style") or "").strip()
                if style not in ALLOWED_CAPTION_STYLES:
                    self._json(400, {"ok": False, "error": f"Стиль субтитров {style!r} не поддерживается; допустимо: {sorted(ALLOWED_CAPTION_STYLES)}"})
                    return
                deck["caption_style"] = style
            if "background_enabled" in body:
                existing_bg = deck.get("background") if isinstance(deck.get("background"), dict) else {}
                prov = str(body.get("background_provider") or existing_bg.get("provider") or "pixabay")
                deck["background"] = {
                    **existing_bg,
                    "enabled": bool(body["background_enabled"]),
                    "provider": prov if prov in {"pexels", "pixabay"} else "pixabay",
                }
            if "music_enabled" in body:
                existing_music = deck.get("music") if isinstance(deck.get("music"), dict) else {}
                deck["music"] = {
                    **existing_music,
                    "enabled": bool(body["music_enabled"]),
                    "volume": existing_music.get("volume", 0.12),
                }
            voice = deck.setdefault("voice", {})
            if body.get("speaker"):
                voice["speaker"] = str(body["speaker"])
            if body.get("voice_mode") in {"single", "podcast"}:
                voice["mode"] = body["voice_mode"]

            edits = body.get("slides")
            if isinstance(edits, list):
                by_id = {s.get("id"): s for s in deck.get("slides") or []}
                for ed in edits:
                    target = by_id.get(ed.get("id"))
                    if not target:
                        continue
                    if "title" in ed:
                        target["title"] = str(ed["title"]).strip()
                    if "subtitle" in ed:
                        target["subtitle"] = str(ed["subtitle"]).strip()
                    if "background_query" in ed:
                        bq = str(ed["background_query"] or "").strip()
                        if bq:
                            target["background_query"] = bq
                        else:
                            target.pop("background_query", None)
                    if "voice_text" in ed:
                        vt = str(ed["voice_text"]).strip()
                        if vt:
                            target["voice_text"] = vt
                            target["voice_ssml"] = voice_ssml(vt, rate=voice.get("rate", "95%"))
                    if isinstance(ed.get("bullets"), list) and "bullets" in target:
                        for i, b_ed in enumerate(ed["bullets"]):
                            if i < len(target["bullets"]):
                                target["bullets"][i]["title"] = str(b_ed.get("title", "")).strip()
                                target["bullets"][i]["desc"] = str(b_ed.get("desc", "")).strip()
                    if isinstance(ed.get("kpis"), list) and target.get("type") == "kpi":
                        kpis_new = []
                        for k_ed in ed["kpis"]:
                            value = str(k_ed.get("value", "")).strip()
                            label = str(k_ed.get("label", "")).strip()
                            if not (1 <= len(value) <= 12) or not label:
                                self._json(400, {"ok": False, "error": f"Slide {target.get('id')}: kpi value must be 1..12 chars and label required"})
                                return
                            kpis_new.append({"value": value, "label": label})
                        target["kpis"] = kpis_new

            try:
                validate_deck(deck)
            except DeckValidationError as exc:
                self._json(400, {"ok": False, "error": f"Валидация не прошла: {exc}"})
                return
            deck_path.write_text(json.dumps(deck, ensure_ascii=False, indent=2), encoding="utf-8")

            if body.get("render", True):
                # Saving edits changes the deck, which invalidates any storyboard approval:
                # the save path builds a DRAFT only. Master MP4 needs a new approval (/api/render).
                cmd = [sys.executable, str(SCRIPTS / "build_deck.py"), str(deck_path), "--render", "--draft"]
                if not JOBS.start("save-render", slug, cmd):
                    self._json(409, {"ok": False, "error": "Сохранено, но уже идёт другая сборка."})
                    return
                self._json(202, {"ok": True, "slug": slug, "step": "save-render"})
                return
            self._json(200, {"ok": True, "slug": slug, "saved": True})
            return

        if path == "/api/render":
            try:
                slug = _valid_slug(str(body.get("slug") or ""))
            except ValueError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            deck_path = DECKS_DIR / f"{slug}.json"
            if not deck_path.is_file():
                self._json(404, {"ok": False, "error": f"Колода не найдена: {slug}"})
                return
            speaker = str(body.get("speaker") or "").strip()
            if speaker:
                if speaker not in ALLOWED_SPEAKERS:
                    self._json(400, {"ok": False, "error": f"Неизвестный голос: {speaker}"})
                    return
                deck = json.loads(deck_path.read_text(encoding="utf-8"))
                deck.setdefault("voice", {})["speaker"] = speaker
                try:
                    validate_deck(deck)
                except DeckValidationError as exc:
                    self._json(400, {"ok": False, "error": str(exc)})
                    return
                deck_path.write_text(json.dumps(deck, ensure_ascii=False, indent=2), encoding="utf-8")

            is_draft = bool(body.get("draft"))
            cmd = [sys.executable, str(SCRIPTS / "build_deck.py"), str(deck_path), "--render"]
            if is_draft:
                cmd.append("--draft")
            elif str(body.get("only_slide") or "").strip():
                self._json(400, {"ok": False, "error": "Мастер-сборка по одному слайду не допускается: для проверки собери черновик"})
                return
            else:
                # Fail-closed: master MP4 only for a storyboard-approved deck + draft (build_deck re-checks).
                try:
                    sb_status = gate_status(slug)
                except StoryboardGateError as exc:
                    self._json(409, {"ok": False, "error": str(exc)})
                    return
                if not sb_status["can_master"]:
                    self._json(409, {"ok": False, "error": f"Мастер заблокирован: {sb_status['reason']}", "storyboard": sb_status})
                    return
                cmd.append("--require-storyboard")
            only_slide = str(body.get("only_slide") or "").strip()
            if only_slide:
                if not re.match(r"^[A-Za-z0-9_-]+$", only_slide):
                    self._json(400, {"ok": False, "error": "Invalid only_slide id"})
                    return
                cmd += ["--only-slide", only_slide]
            if body.get("offline_only"):
                cmd.append("--offline-only")
            if body.get("crf") is not None:
                try:
                    crf_val = int(body["crf"])
                except (TypeError, ValueError):
                    self._json(400, {"ok": False, "error": "Invalid crf integer"})
                    return
                if not (14 <= crf_val <= 32):
                    self._json(400, {"ok": False, "error": "crf must be in [14, 32]"})
                    return
                cmd += ["--crf", str(crf_val)]
            if not JOBS.start("render", slug, cmd):
                self._json(409, {"ok": False, "error": "Уже идёт другая сборка. Дождись её завершения."})
                return
            self._json(202, {"ok": True, "slug": slug, "step": "render", "only_slide": only_slide or None, "draft": is_draft})
            return

        if path == "/api/storyboard/build":
            try:
                slug = _valid_slug(str(body.get("slug") or ""))
            except ValueError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            try:
                sb_status = gate_status(slug)
            except StoryboardGateError as exc:
                self._json(409, {"ok": False, "error": str(exc)})
                return
            if not sb_status["draft_fresh"]:
                self._json(409, {"ok": False, "error": f"Нельзя собрать раскадровку: {sb_status['reason']}", "storyboard": sb_status})
                return
            cmd = [sys.executable, str(SCRIPTS / "storyboard_gate.py"), "build", slug]
            if not JOBS.start("storyboard", slug, cmd):
                self._json(409, {"ok": False, "error": "Уже идёт другая сборка. Дождись её завершения."})
                return
            self._json(202, {"ok": True, "slug": slug, "step": "storyboard"})
            return

        if path in {"/api/storyboard/approve", "/api/storyboard/revoke"}:
            try:
                slug = _valid_slug(str(body.get("slug") or ""))
            except ValueError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            try:
                sb_status = sb_approve(slug) if path.endswith("/approve") else sb_revoke(slug)
            except StoryboardGateError as exc:
                self._json(409, {"ok": False, "error": str(exc)})
                return
            self._json(200, {"ok": True, "status": sb_status})
            return

        if path == "/api/pronunciation":
            from ru_speech import get_latin_ru, save_pronunciation_overrides  # noqa: E402

            raw = body.get("overrides")
            if not isinstance(raw, dict):
                self._json(400, {"ok": False, "error": "Expected JSON object 'overrides'"})
                return
            save_pronunciation_overrides({str(k): str(v) for k, v in raw.items()})
            self._json(200, {"ok": True, "overrides": raw, "total_entries": len(get_latin_ru())})
            return

        if path == "/api/cutdown":
            try:
                slug = _valid_slug(str(body.get("slug") or ""))
            except ValueError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            src_deck = DECKS_DIR / f"{slug}.json"
            if not src_deck.is_file():
                self._json(404, {"ok": False, "error": f"Deck not found: {slug}"})
                return
            from make_cutdown import build_short_cutdown  # noqa: E402

            try:
                deck_data = json.loads(src_deck.read_text(encoding="utf-8"))
                short = build_short_cutdown(deck_data, max_slides=int(body.get("max_slides") or 4))
                out_p = DECKS_DIR / f"{short['slug']}.json"
                out_p.write_text(json.dumps(short, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            except Exception as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            self._json(200, {"ok": True, "slug": short["slug"], "slides": len(short["slides"]), "aspect": short["aspect"]})
            return

        if path == "/api/qa":
            try:
                slug = _valid_slug(str(body.get("slug") or ""))
            except ValueError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            mp4 = OUT_DIR / f"{slug}.mp4"
            if not mp4.is_file():
                self._json(404, {"ok": False, "error": f"MP4 not found: out/{slug}.mp4"})
                return
            from media_qa import run_media_qa  # noqa: E402

            try:
                rep = run_media_qa(mp4, expect_loudnorm=bool(body.get("expect_loudnorm", True)))
            except Exception as exc:
                self._json(500, {"ok": False, "error": str(exc)})
                return
            self._json(200 if rep["ok"] else 422, rep)
            return

        if path == "/api/github-release":
            try:
                slug = _valid_slug(str(body.get("slug") or ""))
            except ValueError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            mp4 = OUT_DIR / f"{slug}.mp4"
            if not mp4.is_file():
                self._json(404, {"ok": False, "error": f"MP4 not found: out/{slug}.mp4"})
                return
            cmd = [sys.executable, str(SCRIPTS / "github_release_uploader.py"), "--mp4", str(mp4)]
            repo = str(body.get("repo") or "").strip()
            tag = str(body.get("tag") or "").strip()
            if repo:
                cmd += ["--repo", repo]
            if tag:
                cmd += ["--tag", tag]
            if body.get("dry_run", True):
                cmd.append("--dry-run")
            if not JOBS.start("github-release", slug, cmd):
                self._json(409, {"ok": False, "error": "Уже идёт другая задача. Дождись её завершения."})
                return
            self._json(202, {"ok": True, "slug": slug, "step": "github-release", "dry_run": bool(body.get("dry_run", True))})
            return

        if path == "/api/bootstrap":
            status = bootstrap_environment(start_ollama=True)
            self._json(200, {"ok": True, "system": status, "provider": provider_info()})
            return

        if path == "/api/tiktok/refresh":
            res = tiktok_refresh(persist=True)
            self._json(200 if res.get("ok") else 400, {**res, "tiktok": tiktok_status()})
            return

        if path == "/api/tiktok/recheck":
            # Re-query uploads TikTok accepted but has not confirmed yet (audit log). Runs as a job.
            cmd = [sys.executable, str(SCRIPTS / "tiktok_uploader.py"), "--recheck-pending", "--verify-wait-sec", "120"]
            if not JOBS.start("tiktok_recheck", "", cmd):
                self._json(409, {"ok": False, "error": "Уже идёт другая задача. Дождись её завершения."})
                return
            self._json(202, {"ok": True, "step": "tiktok_recheck"})
            return

        if path == "/api/tiktok/upload":
            try:
                slug = _valid_slug(str(body.get("slug") or ""))
            except ValueError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            mp4 = OUT_DIR / f"{slug}.mp4"
            if not mp4.is_file():
                self._json(404, {"ok": False, "error": f"MP4 не найден: out/{slug}.mp4"})
                return
            # Fail-closed: if this slug has a deck, refuse upload unless storyboard is approved for current deck.
            # Merged videos from Tab 03 have no decks/<slug>.json and remain uploadable.
            if (DECKS_DIR / f"{slug}.json").is_file():
                # Fail-closed: any uploaded asset in the deck without a licence blocks publishing.
                try:
                    deck_obj = json.loads((DECKS_DIR / f"{slug}.json").read_text(encoding="utf-8"))
                    unlicensed = unlicensed_deck_assets(slug, deck_obj)
                except (OSError, json.JSONDecodeError, AssetStoreError) as exc:
                    self._json(409, {"ok": False, "error": f"Проверка лицензий не пройдена: {exc}"})
                    return
                if unlicensed:
                    self._json(
                        409,
                        {
                            "ok": False,
                            "error": (
                                "Отправка в TikTok заблокирована: у ассетов не указана лицензия. "
                                "Откройте инспектор ассета, выберите лицензию (CC0, own, PDM, CC BY…) и сохраните: "
                                + ", ".join(unlicensed)
                            ),
                            "unlicensed": unlicensed,
                        },
                    )
                    return
                try:
                    sb_status = gate_status(slug)
                except StoryboardGateError as exc:
                    self._json(409, {"ok": False, "error": str(exc)})
                    return
                if not sb_status["can_master"]:
                    self._json(
                        409,
                        {
                            "ok": False,
                            "error": f"Отправка в TikTok заблокирована: {sb_status['reason']}",
                            "storyboard": sb_status,
                        },
                    )
                    return
            mode = str(body.get("mode") or "inbox").strip().lower()
            if mode not in {"inbox", "direct"}:
                mode = "inbox"
            caption = str(body.get("caption") or "").strip()[:2200]
            dry_run = bool(body.get("dry_run", False))
            cmd = [
                sys.executable,
                str(SCRIPTS / "tiktok_uploader.py"),
                "--mp4", str(mp4),
                "--mode", mode,
            ]
            if caption:
                cmd += ["--caption", caption]
            if dry_run:
                cmd.append("--dry-run")
            if not JOBS.start("tiktok", slug, cmd):
                self._json(409, {"ok": False, "error": "Уже идёт другая задача. Дождись её завершения."})
                return
            self._json(202, {"ok": True, "slug": slug, "step": "tiktok", "mode": mode})
            return

        if path == "/api/merge":
            try:
                out_slug = _valid_slug(str(body.get("out_slug") or ""))
            except ValueError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            raw_clips = body.get("clips")
            if not isinstance(raw_clips, list) or len(raw_clips) < 2:
                self._json(400, {"ok": False, "error": "Выбери минимум 2 видео для склейки."})
                return
            clips: list[str] = []
            for c in raw_clips:
                try:
                    cs = _valid_slug(str(c))
                except ValueError as exc:
                    self._json(400, {"ok": False, "error": str(exc)})
                    return
                if not (OUT_DIR / f"{cs}.mp4").is_file():
                    self._json(404, {"ok": False, "error": f"Видео не найдено: out/{cs}.mp4"})
                    return
                clips.append(cs)
            cmd = [sys.executable, str(SCRIPTS / "merge_videos.py"), "--out", out_slug, *clips]
            if not JOBS.start("merge", out_slug, cmd):
                self._json(409, {"ok": False, "error": "Уже идёт другая сборка. Дождись её завершения."})
                return
            self._json(202, {"ok": True, "slug": out_slug, "step": "merge"})
            return

        self._json(404, {"ok": False, "error": "Not found"})


def main() -> int:
    parser = argparse.ArgumentParser(description="DUP Presenter local web console")
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--open", action="store_true", help="Open browser on start")
    parser.add_argument("--no-auto-ollama", action="store_true", help="Do not auto-start Ollama on startup")
    args = parser.parse_args()

    st = bootstrap_environment(start_ollama=not args.no_auto_ollama)
    print(
        f"[bootstrap] cloud={'OK:' + st['cloud_model'] if st['cloud_configured'] else 'off'} | "
        f"ollama={'ONLINE:' + ','.join(st['ollama_models']) if st['ollama_online'] else 'offline'} | "
        f"tts_ru={'OK' if st['silero_ru_ready'] else 'auto'} | tts_en={'OK' if st['silero_en_ready'] else 'auto'} | "
        f"ffmpeg={'OK' if st['ffmpeg_ready'] else 'MISSING'} | remotion={'OK' if st['remotion_ready'] else 'MISSING'}"
    )
    server = ThreadingHTTPServer(("127.0.0.1", args.port), ConsoleHandler)
    url = f"http://127.0.0.1:{args.port}"
    print(f"[console] DUP Presenter Console listening on {url}")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[console] stopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
