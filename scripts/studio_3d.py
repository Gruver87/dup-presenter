"""Fail-closed Image-to-3D (.glb) backend for DUP Presenter 3D Studio.

Supported external Image-to-3D providers (via environment variables):
  1. TRIPO_API_KEY -> Tripo3D v2 API (https://api.tripo3d.ai/v2/openapi)
  2. FAL_KEY       -> Fal.ai TripoSR queue API (https://queue.fal.run/fal-ai/triposr)

Fail-closed policy:
  - If neither key is set, `generate_glb` raises Studio3DError immediately (no silent fallback).
  - TLS verification is always enabled.
  - All saved .glb files are validated for GLB magic header (`glTF`) and capped at 50 MB.
  - Local `.glb` uploads are also supported so existing 3D models can be inspected offline.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DIR = ROOT / "public"
MODELS_DIR = PUBLIC_DIR / "models3d"

MAX_GLB_BYTES = 50 * 1024 * 1024  # 50 MB
MAX_IMG_BYTES = 20 * 1024 * 1024  # 20 MB source image
TRIPO_BASE = "https://api.tripo3d.ai/v2/openapi"
FAL_TRIPOSR_URL = "https://queue.fal.run/fal-ai/triposr"
FAL_QUEUE_PREFIX = "https://queue.fal.run/"
POLL_TIMEOUT_SEC = 180.0
POLL_INTERVAL_SEC = 2.5


class Studio3DError(RuntimeError):
    """Raised when 3D generation or GLB validation fails (fail-closed)."""


def configured_provider() -> str | None:
    """Return 'tripo3d', 'fal', or None depending on environment variables."""
    if os.environ.get("TRIPO_API_KEY", "").strip():
        return "tripo3d"
    if os.environ.get("FAL_KEY", "").strip():
        return "fal"
    return None


def _safe_stem(name: str, fallback: str = "model") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", str(name or "").strip()).strip("-_")[:48]
    return cleaned or fallback


def validate_glb_bytes(raw: bytes) -> None:
    """Fail-closed validation of GLB binary header (`glTF` magic + size cap)."""
    if not raw or len(raw) < 12:
        raise Studio3DError("Файл слишком мал и не является корректным .glb")
    if len(raw) > MAX_GLB_BYTES:
        mb = round(len(raw) / (1024 * 1024), 1)
        raise Studio3DError(f".glb превышает лимит {MAX_GLB_BYTES // (1024 * 1024)} МБ ({mb} МБ)")
    if raw[:4] != b"glTF":
        raise Studio3DError("Некорректный формат .glb (отсутствует заголовок glTF)")


def save_glb_bytes(raw: bytes, *, name: str = "model", source: str = "local-upload") -> dict[str, Any]:
    """Validate and save a .glb binary under public/models3d/."""
    validate_glb_bytes(raw)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(raw).hexdigest()[:10]
    stem = _safe_stem(name)
    fname = f"{stem}_{digest}.glb"
    dest = MODELS_DIR / fname
    tmp = dest.with_suffix(".glb.tmp")
    tmp.write_bytes(raw)
    tmp.replace(dest)
    return {
        "file": f"models3d/{fname}",
        "name": fname,
        "bytes": len(raw),
        "source": source,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def list_models() -> list[dict[str, Any]]:
    """List saved .glb files in public/models3d/ newest first."""
    if not MODELS_DIR.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(MODELS_DIR.glob("*.glb"), key=lambda x: x.stat().st_mtime, reverse=True):
        st = p.stat()
        out.append({
            "file": f"models3d/{p.name}",
            "name": p.name,
            "bytes": st.st_size,
            "mtime": int(st.st_mtime),
        })
    return out


def _download_glb(url: str) -> bytes:
    if not str(url).startswith("https://"):
        raise Studio3DError("3D API вернул небезопасную ссылку на .glb (ожидается https://)")
    req = urllib.request.Request(url, headers={"User-Agent": "DUP-Presenter/1.3"})
    chunks: list[bytes] = []
    total = 0
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            if not str(resp.geturl()).startswith("https://"):
                raise Studio3DError("Ссылка на .glb перенаправила на небезопасный адрес (не https://)")
            while True:
                ch = resp.read(256 * 1024)
                if not ch:
                    break
                total += len(ch)
                if total > MAX_GLB_BYTES:
                    raise Studio3DError("Скачанный .glb превышает лимит 50 МБ")
                chunks.append(ch)
    except Studio3DError:
        raise
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise Studio3DError(f"Не удалось скачать .glb: {exc}") from exc
    return b"".join(chunks)


def _generate_via_tripo3d(image_bytes: bytes, ext: str, api_key: str) -> bytes:
    """Tripo3D v2: upload image -> create image_to_model task -> poll -> download GLB."""
    boundary = f"----DupPresenter{hashlib.md5(image_bytes[:64]).hexdigest()[:12]}"
    mime = {".png": "image/png", ".webp": "image/webp"}.get(ext, "image/jpeg")
    part_head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="input{ext}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode("utf-8")
    body = part_head + image_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")
    up_req = urllib.request.Request(
        f"{TRIPO_BASE}/upload",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(up_req, timeout=30) as resp:
            up_data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise Studio3DError(f"Tripo3D upload failed: {exc}") from exc

    image_token = ((up_data.get("data") or {}).get("image_token")) or ""
    if not image_token:
        raise Studio3DError(f"Tripo3D upload returned no image_token: {up_data}")

    task_payload = {
        "type": "image_to_model",
        "file": {"type": ext.lstrip("."), "file_token": image_token},
    }
    task_req = urllib.request.Request(
        f"{TRIPO_BASE}/task",
        data=json.dumps(task_payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(task_req, timeout=30) as resp:
            task_data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise Studio3DError(f"Tripo3D task creation failed: {exc}") from exc

    task_id = ((task_data.get("data") or {}).get("task_id")) or ""
    if not task_id:
        raise Studio3DError(f"Tripo3D task creation returned no task_id: {task_data}")

    deadline = time.monotonic() + POLL_TIMEOUT_SEC
    while time.monotonic() < deadline:
        poll_req = urllib.request.Request(
            f"{TRIPO_BASE}/task/{task_id}",
            headers={"Authorization": f"Bearer {api_key}"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(poll_req, timeout=20) as resp:
                st_data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise Studio3DError(f"Tripo3D poll failed: {exc}") from exc
        info = st_data.get("data") or {}
        status = str(info.get("status") or "").lower()
        if status == "success":
            out = info.get("output") or {}
            glb_url = out.get("pbr_model") or out.get("model") or ""
            if not glb_url:
                raise Studio3DError(f"Tripo3D finished without model URL: {info}")
            return _download_glb(str(glb_url))
        if status in {"failed", "cancelled", "unknown"}:
            raise Studio3DError(f"Tripo3D task failed (status={status})")
        time.sleep(POLL_INTERVAL_SEC)
    raise Studio3DError(f"Tripo3D task timed out after {int(POLL_TIMEOUT_SEC)}s")


def _generate_via_fal(image_bytes: bytes, ext: str, api_key: str) -> bytes:
    """Fal.ai TripoSR queue: submit data URI -> poll status_url -> download GLB."""
    mime = {".png": "image/png", ".webp": "image/webp"}.get(ext, "image/jpeg")
    data_uri = f"data:{mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    req = urllib.request.Request(
        FAL_TRIPOSR_URL,
        data=json.dumps({"image_url": data_uri, "output_format": "glb"}).encode("utf-8"),
        headers={"Authorization": f"Key {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            sub = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise Studio3DError(f"Fal.ai submit failed: {exc}") from exc

    status_url = str(sub.get("status_url") or "")
    response_url = str(sub.get("response_url") or "")
    if not status_url or not response_url:
        raise Studio3DError(f"Fal.ai returned unexpected queue payload: {sub}")
    # The API key is sent to these URLs, so they must stay on the Fal queue host.
    for u in (status_url, response_url):
        if not u.startswith(FAL_QUEUE_PREFIX):
            raise Studio3DError(f"Fal.ai вернул ссылку вне {FAL_QUEUE_PREFIX}: {u!r}")

    deadline = time.monotonic() + POLL_TIMEOUT_SEC
    while time.monotonic() < deadline:
        st_req = urllib.request.Request(status_url, headers={"Authorization": f"Key {api_key}"})
        try:
            with urllib.request.urlopen(st_req, timeout=20) as resp:
                st = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise Studio3DError(f"Fal.ai poll failed: {exc}") from exc
        if st.get("status") == "COMPLETED":
            res_req = urllib.request.Request(response_url, headers={"Authorization": f"Key {api_key}"})
            try:
                with urllib.request.urlopen(res_req, timeout=20) as resp:
                    out = json.loads(resp.read().decode("utf-8"))
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                raise Studio3DError(f"Fal.ai result fetch failed: {exc}") from exc
            glb_url = ((out.get("model_mesh") or {}).get("url")) or out.get("glb_url") or ""
            if not glb_url:
                raise Studio3DError(f"Fal.ai finished without model URL: {out}")
            return _download_glb(str(glb_url))
        if st.get("status") in {"FAILED", "CANCELLED"}:
            raise Studio3DError(f"Fal.ai task failed: {st}")
        time.sleep(POLL_INTERVAL_SEC)
    raise Studio3DError(f"Fal.ai task timed out after {int(POLL_TIMEOUT_SEC)}s")


def generate_glb(image_bytes: bytes, *, name: str = "model", provider: str = "auto") -> dict[str, Any]:
    """Generate a .glb 3D model from a single image via Tripo3D or Fal.ai (fail-closed)."""
    from asset_store import sniff_media

    if not image_bytes:
        raise Studio3DError("Пустой файл изображения")
    if len(image_bytes) > MAX_IMG_BYTES:
        raise Studio3DError(f"Изображение превышает лимит {MAX_IMG_BYTES // (1024 * 1024)} МБ")
    sn = sniff_media(image_bytes[:32])
    if sn is None or sn[0] != "image":
        raise Studio3DError("Для Image-to-3D нужна картинка (JPG, PNG или WebP)")
    ext = sn[1]

    chosen = provider.strip().lower() if provider else "auto"
    if chosen == "auto":
        chosen = configured_provider() or ""
    if not chosen:
        raise Studio3DError(
            "3D API не настроен: задай TRIPO_API_KEY (Tripo3D) или FAL_KEY (Fal.ai) в переменных окружения (fail-closed)."
        )

    if chosen == "tripo3d":
        key = os.environ.get("TRIPO_API_KEY", "").strip()
        if not key:
            raise Studio3DError("TRIPO_API_KEY не задан")
        glb_bytes = _generate_via_tripo3d(image_bytes, ext, key)
    elif chosen == "fal":
        key = os.environ.get("FAL_KEY", "").strip()
        if not key:
            raise Studio3DError("FAL_KEY не задан")
        glb_bytes = _generate_via_fal(image_bytes, ext, key)
    else:
        raise Studio3DError(f"Неизвестный 3D-провайдер: {provider!r}")

    return save_glb_bytes(glb_bytes, name=name, source=chosen)
