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
    ALLOWED_SPEAKERS,
    ALLOWED_SPEAKERS_BY_LANG,
    ALLOWED_THEMES,
    ASPECT_DIMS,
    DeckValidationError,
    validate_deck,
)
from fetch_repo import RepoFetchError, looks_like_remote, normalize_git_url  # noqa: E402
from plan_deck import voice_ssml  # noqa: E402
from tiktok_uploader import refresh_access_token as tiktok_refresh, tiktok_status  # noqa: E402

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
    """On Windows, refresh DUP_LLM_* from User registry env so a newly set key works."""
    if os.name != "nt":
        return
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            for name in ("DUP_LLM_BASE_URL", "DUP_LLM_MODEL", "DUP_LLM_API_KEY"):
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
                self.status = "ok" if rc == 0 else "error"
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
    srt = OUT_DIR / f"{slug}.srt"
    vtt = OUT_DIR / f"{slug}.vtt"
    thumb = OUT_DIR / f"{slug}_thumb.png"
    return {
        "ok": True,
        "slug": slug,
        "deck": deck,
        "history": history,
        "has_mp4": mp4.is_file(),
        "mp4_mtime": int(mp4.stat().st_mtime) if mp4.is_file() else 0,
        "has_srt": srt.is_file(),
        "has_vtt": vtt.is_file(),
        "has_thumb": thumb.is_file(),
        "thumb_mtime": int(thumb.stat().st_mtime) if thumb.is_file() else 0,
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
                "job": JOBS.snapshot(),
            })
            return

        if path == "/api/deck":
            slug = (qs.get("slug") or [""])[0]
            try:
                self._json(200, read_deck_detail(slug))
            except (ValueError, FileNotFoundError) as exc:
                self._json(404, {"ok": False, "error": str(exc)})
            return

        if path.startswith("/video/") and path.endswith(".mp4"):
            slug = path[len("/video/"):-4]
            self._serve_video(slug)
            return

        if path.startswith("/out/"):
            fname = path[len("/out/"):]
            if not re.match(r"^[A-Za-z0-9_-]+(?:\.srt|\.vtt|_thumb\.png)$", fname):
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

        self._json(404, {"ok": False, "error": "Not found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            body = self._read_json()
        except json.JSONDecodeError as exc:
            self._json(400, {"ok": False, "error": f"Invalid JSON: {exc}"})
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
                "--aspect", aspect, "--voice-mode", voice_mode, "--render",
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
                "--theme", theme, "--aspect", aspect, "--voice-mode", voice_mode, "--render",
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
                deck["aspect"] = body["aspect"]
                deck["width"], deck["height"] = ASPECT_DIMS[body["aspect"]]
            if "burn_captions" in body:
                deck["burn_captions"] = bool(body["burn_captions"])
            if "background_enabled" in body:
                prov = str(body.get("background_provider") or "pixabay")
                deck["background"] = {
                    "enabled": bool(body["background_enabled"]),
                    "provider": prov if prov in {"pexels", "pixabay"} else "pixabay",
                }
            if "music_enabled" in body:
                deck["music"] = {"enabled": bool(body["music_enabled"]), "volume": 0.12}
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
                cmd = [sys.executable, str(SCRIPTS / "build_deck.py"), str(deck_path), "--render"]
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

            cmd = [sys.executable, str(SCRIPTS / "build_deck.py"), str(deck_path), "--render"]
            if not JOBS.start("render", slug, cmd):
                self._json(409, {"ok": False, "error": "Уже идёт другая сборка. Дождись её завершения."})
                return
            self._json(202, {"ok": True, "slug": slug, "step": "render"})
            return

        if path == "/api/bootstrap":
            status = bootstrap_environment(start_ollama=True)
            self._json(200, {"ok": True, "system": status, "provider": provider_info()})
            return

        if path == "/api/tiktok/refresh":
            res = tiktok_refresh(persist=True)
            self._json(200 if res.get("ok") else 400, {**res, "tiktok": tiktok_status()})
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
