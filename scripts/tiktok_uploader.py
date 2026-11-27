"""DUP Presenter — Official TikTok Content Posting API uploader & OAuth auto-refresh.

Uses only the official TikTok API:
  - Token refresh: https://open.tiktokapis.com/v2/oauth/token/ (grant_type=refresh_token)
  - Inbox draft:   https://open.tiktokapis.com/v2/post/publish/inbox/video/init/
  - Direct post:   https://open.tiktokapis.com/v2/post/publish/video/init/

Never uses cookie bots or browser automation. Never prints or logs secret token values.

Credential resolution order:
  1. Process environment / Windows User registry env (TIKTOK_*)
  2. Local repo .env (dup-presenter/.env)
  3. Sibling dup-content-engine/.env (if present on disk)

When OAuth refresh rotates TIKTOK_ACCESS_TOKEN / TIKTOK_REFRESH_TOKEN, the new
values are written back to local .env (and synced to dup-content-engine/.env if
that file already stores TikTok tokens) so both projects stay fresh automatically.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent
SECRETS_ENV = ROOT / "secrets" / "tiktok_keys.env"
LOCAL_ENV = ROOT / ".env"
SIBLING_ENV = ROOT.parent / "dup-content-engine" / ".env"
AUDIT_LOG = ROOT / "work" / "tiktok_publish_audit.jsonl"

API_BASE = "https://open.tiktokapis.com"
TOKEN_URL = f"{API_BASE}/v2/oauth/token/"

TIKTOK_KEYS = (
    "TIKTOK_CLIENT_KEY",
    "TIKTOK_CLIENT_SECRET",
    "TIKTOK_ACCESS_TOKEN",
    "TIKTOK_REFRESH_TOKEN",
    "TIKTOK_PRIVACY_LEVEL",
)


def _parse_dotenv(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.is_file():
        return data
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k in TIKTOK_KEYS and v:
            data[k] = v
    return data


def _upsert_env(path: Path, key: str, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if path.is_file():
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    out: list[str] = []
    found = False
    prefix = f"{key}="
    for line in lines:
        if line.startswith(prefix) or line.startswith(f"#{prefix}"):
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        if out and out[-1].strip():
            out.append("")
        out.append(f"{key}={value}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def _load_windows_user_tiktok_env() -> dict[str, str]:
    found: dict[str, str] = {}
    if os.name != "nt":
        return found
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as reg:
            for name in TIKTOK_KEYS:
                try:
                    val, _ = winreg.QueryValueEx(reg, name)
                    if val and str(val).strip():
                        found[name] = str(val).strip()
                except FileNotFoundError:
                    pass
    except OSError:
        pass
    return found


def load_tiktok_env() -> dict[str, Any]:
    """Load TIKTOK_* variables into os.environ from secrets/tiktok_keys.env, .env, sibling .env, or User env."""
    sources: list[str] = []
    merged: dict[str, str] = {}

    # Lowest priority first -> highest priority overwrites
    sib = _parse_dotenv(SIBLING_ENV)
    if sib:
        merged.update(sib)
        sources.append(str(SIBLING_ENV))

    loc = _parse_dotenv(LOCAL_ENV)
    if loc:
        merged.update(loc)
        sources.append(str(LOCAL_ENV))

    sec = _parse_dotenv(SECRETS_ENV)
    if sec:
        merged.update(sec)
        sources.append(str(SECRETS_ENV))

    reg = _load_windows_user_tiktok_env()
    if reg:
        merged.update(reg)
        sources.append("windows_user_env")

    # Apply fresh values from disk/registry so editing secrets/tiktok_keys.env takes effect without restart
    for k, v in merged.items():
        if v:
            os.environ[k] = v

    return {
        "sources": sources,
        "secrets_env": SECRETS_ENV.is_file(),
        "local_env": LOCAL_ENV.is_file(),
        "sibling_env": SIBLING_ENV.is_file(),
    }


def tiktok_status() -> dict[str, Any]:
    """Return honest boolean status of TikTok credentials (never returns secret values)."""
    info = load_tiktok_env()
    has_access = bool(os.environ.get("TIKTOK_ACCESS_TOKEN", "").strip())
    has_refresh = bool(os.environ.get("TIKTOK_REFRESH_TOKEN", "").strip())
    has_ck = bool(os.environ.get("TIKTOK_CLIENT_KEY", "").strip())
    has_cs = bool(os.environ.get("TIKTOK_CLIENT_SECRET", "").strip())
    can_auto_refresh = has_refresh and has_ck and has_cs
    return {
        "ready": has_access or can_auto_refresh,
        "access_token_set": has_access,
        "refresh_token_set": has_refresh,
        "client_key_set": has_ck,
        "client_secret_set": has_cs,
        "can_auto_refresh": can_auto_refresh,
        "privacy_level": os.environ.get("TIKTOK_PRIVACY_LEVEL", "SELF_ONLY").strip() or "SELF_ONLY",
        "sources": info["sources"],
    }


def refresh_access_token(persist: bool = True) -> dict[str, Any]:
    """Exchange TIKTOK_REFRESH_TOKEN for a new access_token via official TikTok OAuth API."""
    load_tiktok_env()
    client_key = os.environ.get("TIKTOK_CLIENT_KEY", "").strip()
    client_secret = os.environ.get("TIKTOK_CLIENT_SECRET", "").strip()
    refresh = os.environ.get("TIKTOK_REFRESH_TOKEN", "").strip()

    missing = [
        k
        for k, v in (
            ("TIKTOK_CLIENT_KEY", client_key),
            ("TIKTOK_CLIENT_SECRET", client_secret),
            ("TIKTOK_REFRESH_TOKEN", refresh),
        )
        if not v
    ]
    if missing:
        return {
            "ok": False,
            "error": f"Missing env for auto-refresh: {', '.join(missing)}",
            "missing_env": missing,
            "hint": "Add TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET to .env to enable automatic token rotation.",
        }

    try:
        with httpx.Client(timeout=60.0) as client:
            r = client.post(
                TOKEN_URL,
                data={
                    "client_key": client_key,
                    "client_secret": client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh,
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Cache-Control": "no-cache",
                },
            )
            payload = r.json()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"OAuth refresh request failed: {exc}"}

    body = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    token = body.get("access_token") if isinstance(body, dict) else None
    if not token:
        return {
            "ok": False,
            "error": payload.get("error") or payload.get("message") or "Empty access_token in response",
            "error_description": payload.get("error_description"),
            "http_status": r.status_code,
        }

    new_refresh = str(body.get("refresh_token") or refresh)
    expires_in = body.get("expires_in")

    persisted_paths: list[str] = []
    if persist:
        targets = [SECRETS_ENV if SECRETS_ENV.is_file() else LOCAL_ENV]
        if SIBLING_ENV.is_file():
            targets.append(SIBLING_ENV)
        for dest in targets:
            _upsert_env(dest, "TIKTOK_ACCESS_TOKEN", str(token))
            _upsert_env(dest, "TIKTOK_REFRESH_TOKEN", new_refresh)
            persisted_paths.append(str(dest))
        os.environ["TIKTOK_ACCESS_TOKEN"] = str(token)
        os.environ["TIKTOK_REFRESH_TOKEN"] = new_refresh

    return {
        "ok": True,
        "expires_in": expires_in,
        "refresh_rotated": new_refresh != refresh,
        "persisted_to": persisted_paths,
    }


def ensure_access_token() -> dict[str, Any]:
    """Return usable access_token; auto-refresh if missing."""
    load_tiktok_env()
    token = os.environ.get("TIKTOK_ACCESS_TOKEN", "").strip()
    if token:
        return {"ok": True, "access_token": token, "refreshed": False}
    ref = refresh_access_token(persist=True)
    if not ref.get("ok"):
        return ref
    token = os.environ.get("TIKTOK_ACCESS_TOKEN", "").strip()
    if not token:
        return {"ok": False, "error": "Token refresh succeeded but access_token is still empty"}
    return {"ok": True, "access_token": token, "refreshed": True}


PUBLISH_STATUS_URL = f"{API_BASE}/v2/post/publish/status/fetch/"
# Terminal states that prove the video reached TikTok. Anything else (PROCESSING_*, unknown) keeps polling.
PUBLISH_OK_STATES = frozenset({"SEND_TO_USER_INBOX", "PUBLISH_COMPLETE"})
PUBLISH_FAIL_STATES = frozenset({"FAILED"})


class TikTokStatusError(RuntimeError):
    """Status check could not be performed or TikTok returned an error (fail-closed, never 'verified')."""


def _parse_publish_status(http_status: int, body: dict[str, Any], raw_text: str = "") -> dict[str, str]:
    """Pure parser for the publish status response. Raises on HTTP or API-level errors."""
    if http_status >= 400:
        raise TikTokStatusError(f"status HTTP {http_status}: {raw_text[:300]}")
    err = str(((body.get("error") or {}).get("code")) or "ok")
    if err not in {"ok", ""}:
        raise TikTokStatusError(f"status API error: {err} {raw_text[:300]}")
    data = body.get("data") or {}
    return {"status": str(data.get("status") or ""), "fail_reason": str(data.get("fail_reason") or "")}


def _fetch_publish_status(token: str, publish_id: str) -> dict[str, str]:
    """One status request to the official Content Posting API."""
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            PUBLISH_STATUS_URL,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
            json={"publish_id": publish_id},
        )
    try:
        body = resp.json() or {}
    except ValueError:
        body = {}
    return _parse_publish_status(resp.status_code, body, resp.text or "")


def poll_publish_status(
    publish_id: str,
    fetch,
    *,
    wait_sec: float = 180.0,
    poll_sec: float = 5.0,
    sleep=None,
    clock=None,
) -> dict[str, Any]:
    """Poll `fetch(publish_id) -> {'status','fail_reason'}` until a terminal state or the deadline.

    Network and time are injected so the decision logic is testable. `verified` is True only for a
    terminal OK state; a timeout or unknown state is reported as unverified, never as success.
    """
    import time as _time

    if not publish_id:
        raise TikTokStatusError("publish_id is empty; nothing to verify")
    sleep = sleep or _time.sleep
    clock = clock or _time.monotonic
    deadline = clock() + max(0.0, float(wait_sec))
    polls = 0
    while True:
        polls += 1
        got = fetch(publish_id)
        st = got.get("status", "")
        base = {"publish_id": publish_id, "status": st or "UNKNOWN", "polls": polls}
        if st in PUBLISH_OK_STATES:
            return {**base, "verified": True, "ok": True, "fail_reason": ""}
        if st in PUBLISH_FAIL_STATES:
            return {**base, "verified": False, "ok": False, "fail_reason": got.get("fail_reason", "")}
        if clock() >= deadline:
            return {**base, "verified": False, "ok": False,
                    "fail_reason": f"timeout after {polls} poll(s); last status {st or 'UNKNOWN'}"}
        sleep(poll_sec)


def tiktok_publish_status(publish_id: str, *, wait_sec: float = 0.0, poll_sec: float = 5.0) -> dict[str, Any]:
    """Check (and optionally wait for) the TikTok processing state of an upload by publish_id."""
    ensured = ensure_access_token()
    if not ensured.get("ok"):
        return {"ok": False, "verified": False, "publish_id": publish_id, "error": ensured.get("error", "no token")}
    try:
        res = poll_publish_status(
            publish_id,
            lambda pid: _fetch_publish_status(_current_access_token(ensured["access_token"]), pid),
            wait_sec=wait_sec,
            poll_sec=poll_sec,
        )
    except TikTokStatusError as exc:
        return {"ok": False, "verified": False, "publish_id": publish_id, "error": str(exc)}
    return {**res, "ok": res["verified"], "error": "" if res["verified"] else res.get("fail_reason", "")}


def _current_access_token(fallback: str) -> str:
    """Access token after any refresh performed during the upload (refresh writes the env var)."""
    return os.environ.get("TIKTOK_ACCESS_TOKEN", "").strip() or fallback


def tiktok_publish(
    mp4: Path,
    *,
    mode: str = "inbox",
    caption: str = "",
    dry_run: bool = False,
    verify_wait_sec: float = 180.0,
) -> dict[str, Any]:
    """Upload MP4 via official TikTok Content Posting API with automatic 401 refresh + retry.

    After a successful upload the publish status is polled (verify_wait_sec); `verified` is True only when
    TikTok reports a terminal OK state. Pass verify_wait_sec=0 to skip the check (reported as NOT_CHECKED).
    """
    if not mp4.is_file():
        return {"ok": False, "error": f"MP4 not found: {mp4}"}

    mode = (mode or "inbox").strip().lower()
    if mode not in {"inbox", "direct"}:
        return {"ok": False, "error": "mode must be inbox or direct"}

    ensured = ensure_access_token()
    token = ensured.get("access_token") if ensured.get("ok") else os.environ.get("TIKTOK_ACCESS_TOKEN", "").strip()
    size = mp4.stat().st_size

    meta: dict[str, Any] = {
        "platform": "tiktok",
        "mode": mode,
        "mp4": mp4.name,
        "bytes": size,
        "caption": (caption or "")[:2200],
        "token_refreshed": bool(ensured.get("refreshed")),
    }

    if dry_run:
        st = tiktok_status()
        return {
            "ok": True,
            "dry_run": True,
            **meta,
            "tiktok_status": st,
            "message": "dry_run OK — no TikTok API call made",
        }

    if not token:
        return {
            "ok": False,
            "error": "TIKTOK_ACCESS_TOKEN missing and auto-refresh unavailable.",
            "refresh": ensured if not ensured.get("ok") else None,
            **meta,
        }

    chunk_size = size if size <= 64 * 1024 * 1024 else 10 * 1024 * 1024
    # TikTok rule: total_chunk_count = floor(video_size / chunk_size); the last
    # chunk absorbs the remainder (allowed up to 128 MB). ceil() is rejected
    # with "The total chunk count is invalid".
    total_chunks = max(1, size // chunk_size)

    if mode == "inbox":
        init_url = f"{API_BASE}/v2/post/publish/inbox/video/init/"
        body: dict[str, Any] = {
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": size,
                "chunk_size": chunk_size,
                "total_chunk_count": total_chunks,
            }
        }
    else:
        init_url = f"{API_BASE}/v2/post/publish/video/init/"
        body = {
            "post_info": {
                "title": (caption or mp4.stem)[:150],
                "privacy_level": os.environ.get("TIKTOK_PRIVACY_LEVEL", "SELF_ONLY").strip() or "SELF_ONLY",
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": size,
                "chunk_size": chunk_size,
                "total_chunk_count": total_chunks,
            },
        }

    def _headers(tok: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {tok}",
            "Content-Type": "application/json; charset=UTF-8",
        }

    def _needs_refresh(resp: httpx.Response) -> bool:
        if resp.status_code in {401, 403}:
            return True
        try:
            code = str(((resp.json() or {}).get("error") or {}).get("code") or "")
            return code in {"access_token_invalid", "scope_not_authorized"}
        except Exception:  # noqa: BLE001
            return "access_token" in (resp.text or "").lower()

    refresh_attempt: dict[str, Any] | None = None
    try:
        with httpx.Client(timeout=120.0) as client:
            print(f"[tiktok] init ({mode}) for {mp4.name} ({size / 1_048_576:.2f} MB, {total_chunks} chunk(s))...")
            init = client.post(init_url, headers=_headers(token), json=body)
            if init.status_code >= 400 or _needs_refresh(init):
                print("[tiktok] token rejected/expired — attempting automatic OAuth refresh...")
                refresh_attempt = refresh_access_token(persist=True)
                if refresh_attempt.get("ok"):
                    token = os.environ.get("TIKTOK_ACCESS_TOKEN", "").strip()
                    meta["token_refreshed"] = True
                    print("[tiktok] token refreshed automatically; retrying init...")
                    init = client.post(init_url, headers=_headers(token), json=body)
                if init.status_code >= 400 or _needs_refresh(init):
                    return {
                        "ok": False,
                        "error": f"TikTok init failed (HTTP {init.status_code}): {init.text[:500]}",
                        "refresh_attempt": refresh_attempt,
                        **meta,
                    }

            init_json = init.json() or {}
            err_code = str(((init_json.get("error") or {}).get("code") or "ok"))
            if err_code not in {"ok", ""}:
                return {
                    "ok": False,
                    "error": f"TikTok init error: {err_code} {init.text[:400]}",
                    **meta,
                }

            data = init_json.get("data") or {}
            upload_url = data.get("upload_url")
            publish_id = data.get("publish_id")
            if not upload_url:
                return {"ok": False, "error": f"No upload_url returned: {init.text[:400]}", **meta}

            with mp4.open("rb") as f:
                for i in range(total_chunks):
                    start = i * chunk_size
                    is_last = i == total_chunks - 1
                    chunk = f.read(size - start if is_last else chunk_size)
                    end = start + len(chunk) - 1
                    if not chunk or (is_last and end != size - 1):
                        return {
                            "ok": False,
                            "error": f"Local read mismatch on chunk {i + 1}: expected end {size - 1}, got {end}",
                            **meta,
                        }
                    print(f"[tiktok] uploading chunk {i + 1}/{total_chunks} ({len(chunk) / 1_048_576:.2f} MB)...")
                    put = client.put(
                        upload_url,
                        headers={
                            "Content-Type": "video/mp4",
                            "Content-Length": str(len(chunk)),
                            "Content-Range": f"bytes {start}-{end}/{size}",
                        },
                        content=chunk,
                    )
                    if put.status_code not in {200, 201, 206}:
                        return {
                            "ok": False,
                            "error": f"Chunk {i + 1} upload failed: HTTP {put.status_code} {put.text[:300]}",
                            **meta,
                        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"TikTok upload error: {exc}", **meta}

    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    audit_row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "platform": "tiktok",
        "mode": mode,
        "publish_id": publish_id,
        "mp4": mp4.name,
        "bytes": size,
        "token_refreshed": meta["token_refreshed"],
    }
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(audit_row, ensure_ascii=False) + "\n")

    # Item 6: the upload call returning is not proof that TikTok processed it. Poll the publish status
    # until a terminal OK state (or the deadline) and report what was actually verified.
    if verify_wait_sec > 0 and publish_id:
        verification = tiktok_publish_status(publish_id, wait_sec=verify_wait_sec)
    else:
        verification = {"verified": False, "ok": False, "status": "NOT_CHECKED", "publish_id": publish_id}
    verified = bool(verification.get("verified"))
    if verified:
        msg = (
            "Verified in TikTok Inbox (Draft) — open TikTok app to review and publish"
            if mode == "inbox"
            else "Verified: TikTok reports the direct post as published"
        )
    else:
        msg = (
            f"Upload accepted but NOT verified (status={verification.get('status', 'NOT_CHECKED')}): "
            f"{verification.get('error') or verification.get('fail_reason') or 'verification not run'}"
        )
    print(f"[{'OK' if verified else 'WARN'}] {msg} | publish_id={publish_id}")
    return {
        "ok": True,
        "verified": verified,
        "dry_run": False,
        "publish_id": publish_id,
        "publish_status": verification,
        "message": msg,
        **meta,
    }


def interactive_oauth(redirect_uri: str = "https://github.com", scopes: str = "user.info.basic,video.upload") -> dict[str, Any]:
    """One-shot official TikTok OAuth login using Client Key/Secret from secrets/tiktok_keys.env."""
    import secrets as py_secrets
    import urllib.parse
    import webbrowser

    load_tiktok_env()
    client_key = os.environ.get("TIKTOK_CLIENT_KEY", "").strip()
    client_secret = os.environ.get("TIKTOK_CLIENT_SECRET", "").strip()
    if not client_key or not client_secret:
        return {"ok": False, "error": "Fill TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET in secrets/tiktok_keys.env first."}

    state = py_secrets.token_urlsafe(12)
    params = urllib.parse.urlencode({
        "client_key": client_key,
        "scope": scopes,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": state,
    })
    auth_url = f"https://www.tiktok.com/v2/auth/authorize/?{params}"
    print("\n1. Открываю страницу авторизации TikTok в браузере...")
    print(f"   {auth_url}\n")
    try:
        webbrowser.open(auth_url)
    except Exception:  # noqa: BLE001
        pass

    print("2. Нажми 'Authorize' / 'Продолжить' в TikTok.")
    print("3. Сразу после редиректа на https://github.com/?code=... скопируй ВСЮ адресную строку и вставь сюда:\n")
    raw = input("Вставь URL (или сам code): ").strip().strip('"').strip("'")
    if not raw:
        return {"ok": False, "error": "Empty URL"}

    if raw.startswith("code="):
        raw = "https://dummy.local/?" + raw
    parsed = urllib.parse.urlparse(raw)
    qs = urllib.parse.parse_qs(parsed.query, keep_blank_values=False)
    if "error" in qs:
        return {"ok": False, "error": f"TikTok error: {qs.get('error')} {qs.get('error_description')}"}
    code = (qs.get("code") or [None])[0]
    if not code and "://" not in raw and "=" not in raw:
        code = raw
    if not code:
        return {"ok": False, "error": "No ?code= found in pasted URL. Copy immediately after Authorize."}
    code = urllib.parse.unquote(code)

    try:
        with httpx.Client(timeout=60.0) as client:
            r = client.post(
                TOKEN_URL,
                data={
                    "client_key": client_key,
                    "client_secret": client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded", "Cache-Control": "no-cache"},
            )
            payload = r.json()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"Token exchange failed: {exc}"}

    body = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    token = body.get("access_token") if isinstance(body, dict) else None
    refresh = body.get("refresh_token") if isinstance(body, dict) else None
    if not token:
        return {
            "ok": False,
            "error": payload.get("error") or payload.get("message") or "No access_token",
            "error_description": payload.get("error_description"),
            "http_status": r.status_code,
        }

    targets = [SECRETS_ENV if SECRETS_ENV.is_file() else LOCAL_ENV]
    if SIBLING_ENV.is_file():
        targets.append(SIBLING_ENV)
    for dest in targets:
        _upsert_env(dest, "TIKTOK_ACCESS_TOKEN", str(token))
        if refresh:
            _upsert_env(dest, "TIKTOK_REFRESH_TOKEN", str(refresh))

    return {
        "ok": True,
        "expires_in": body.get("expires_in"),
        "refresh_saved": bool(refresh),
        "persisted_to": [str(t) for t in targets],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="DUP Presenter — TikTok uploader & OAuth refresh")
    parser.add_argument("--status", action="store_true", help="Show TikTok credential readiness (no secrets)")
    parser.add_argument("--refresh", action="store_true", help="Refresh TikTok OAuth access_token")
    parser.add_argument("--oauth", action="store_true", help="Run interactive TikTok OAuth login")
    parser.add_argument("--mp4", default="", help="Path to MP4 file to upload")
    parser.add_argument("--mode", choices=["inbox", "direct"], default="inbox")
    parser.add_argument("--caption", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check-publish", default="", metavar="PUBLISH_ID",
                        help="Check the processing status of an earlier upload (item 6)")
    parser.add_argument("--verify-wait-sec", type=float, default=180.0,
                        help="Seconds to poll for a terminal state after upload (0 = skip verification)")
    args = parser.parse_args()

    if args.status:
        print(json.dumps(tiktok_status(), ensure_ascii=False, indent=2))
        return 0

    if args.check_publish:
        res = tiktok_publish_status(args.check_publish.strip(), wait_sec=max(0.0, args.verify_wait_sec))
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res.get("verified") else 1

    if args.oauth:
        res = interactive_oauth()
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res.get("ok") else 1

    if args.refresh:
        res = refresh_access_token(persist=True)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res.get("ok") else 1

    if not args.mp4:
        print("[FAIL] Specify --mp4 <file>, --refresh, or --status", file=sys.stderr)
        return 2

    res = tiktok_publish(
        Path(args.mp4), mode=args.mode, caption=args.caption, dry_run=args.dry_run,
        verify_wait_sec=max(0.0, args.verify_wait_sec),
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))
    if args.dry_run:
        return 0 if res.get("ok") else 1
    # Exit 0 only when TikTok confirmed the state. With verification disabled, an upload is not a success.
    return 0 if (res.get("ok") and res.get("verified")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
