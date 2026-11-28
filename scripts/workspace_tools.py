"""Fail-closed local workspace tools for DUP Presenter.

Capabilities (mirrors safe engineering workflow):
  - `list_dir(path)`        — inspect files and folders (names, types, sizes).
  - `find_files(pattern)`   — search for files by glob pattern inside allowed roots.
  - `read_text_file(path)`  — read text files safely (secret filenames refused, content redacted).
  - `create_dir(path)`      — create a new folder inside allowed roots.
  - `delete_path(path, ...)`— REFUSED by default; requires explicit user confirmation phrase
                              (`DELETE <filename>`) and never deletes directories recursively.

Fail-closed invariants:
  - Strict root jail: only `dup-presenter` root and `DUP_Radar_Keyframes` (or `DUP_WORKSPACE_ROOTS`).
  - Path traversal (`..`), symlinks escaping the jail, and sensitive/secret files
    (`.env`, `*.pem`, `*.key`, `*secret*`, `*credential*`, `id_rsa*`) are always refused.
  - All returned text is scrubbed via `secret_guard.redact_secrets()`.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from secret_guard import redact_secrets

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EXTRA_ROOT = Path.home() / "Desktop" / "DUP_Radar_Keyframes"

_FORBIDDEN_FILE_RE = re.compile(
    r"(^|/|\.)(env|pem|key|p12|pfx|jks|kdbx|id_rsa|id_ed25519|credentials|secrets?)$",
    re.IGNORECASE,
)
_FORBIDDEN_DIR_NAMES: frozenset[str] = frozenset({".git", ".ssh", ".aws", ".gnupg", "__pycache__", "node_modules"})


class WorkspaceGuardError(RuntimeError):
    """Raised fail-closed when a workspace operation violates sandbox or safety rules."""


def allowed_roots() -> list[Path]:
    """Return resolved list of allowed workspace root directories."""
    roots: list[Path] = [ROOT.resolve()]
    if DEFAULT_EXTRA_ROOT.exists():
        roots.append(DEFAULT_EXTRA_ROOT.resolve())
    extra = os.environ.get("DUP_WORKSPACE_ROOTS", "").strip()
    if extra:
        for item in extra.split(os.pathsep):
            p = item.strip()
            if p:
                rp = Path(p).expanduser().resolve()
                if rp not in roots:
                    roots.append(rp)
    return roots


def _resolve_in_jail(raw_path: str | Path) -> Path:
    """Resolve `raw_path` and verify it stays strictly inside `allowed_roots()`."""
    text = str(raw_path or "").strip()
    if not text:
        return ROOT.resolve()
    p = Path(text)
    if not p.is_absolute():
        p = ROOT / p
    try:
        resolved = p.resolve()
    except OSError as exc:
        raise WorkspaceGuardError(f"Некорректный путь: {exc}") from exc

    roots = allowed_roots()
    for r in roots:
        if resolved == r or r in resolved.parents:
            return resolved
    raise WorkspaceGuardError(
        f"СТОП: путь {str(resolved)!r} выходит за пределы разрешённых рабочих папок."
    )


def _assert_not_secret_path(path: Path) -> None:
    name = path.name
    if name.lower().startswith(".env") or _FORBIDDEN_FILE_RE.search(name):
        raise WorkspaceGuardError(f"СТОП: доступ к секретному файлу {name!r} запрещён.")
    for part in path.parts:
        if part.lower() in _FORBIDDEN_DIR_NAMES:
            raise WorkspaceGuardError(f"СТОП: доступ к служебной папке {part!r} запрещён.")


def list_dir(raw_path: str | Path = "", *, limit: int = 200) -> dict[str, Any]:
    """List files and subdirectories inside an allowed folder."""
    target = _resolve_in_jail(raw_path)
    _assert_not_secret_path(target)
    if not target.exists():
        raise WorkspaceGuardError(f"Папка не найдена: {target}")
    if not target.is_dir():
        raise WorkspaceGuardError(f"Это файл, а не папка: {target}")

    entries: list[dict[str, Any]] = []
    for child in sorted(target.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
        if child.name.lower() in _FORBIDDEN_DIR_NAMES or child.name.lower().startswith(".env"):
            continue
        try:
            st = child.stat()
            size = st.st_size if child.is_file() else None
        except OSError:
            size = None
        entries.append(
            {
                "name": child.name,
                "kind": "dir" if child.is_dir() else "file",
                "size": size,
                "path": str(child),
            }
        )
        if len(entries) >= max(1, min(int(limit), 500)):
            break

    return {"ok": True, "path": str(target), "count": len(entries), "entries": entries}


def find_files(pattern: str, raw_root: str | Path = "", *, limit: int = 100) -> dict[str, Any]:
    """Find files matching a glob pattern inside an allowed folder."""
    clean_pat = str(pattern or "").strip()
    if not clean_pat:
        raise WorkspaceGuardError("Укажите шаблон поиска (например, *.mp4 или *radar*)")
    if ".." in clean_pat:
        raise WorkspaceGuardError("СТОП: '..' в шаблоне поиска запрещено")

    base = _resolve_in_jail(raw_root)
    _assert_not_secret_path(base)
    if not base.is_dir():
        raise WorkspaceGuardError(f"Папка поиска не найдена: {base}")

    matches: list[dict[str, Any]] = []
    for item in base.rglob(clean_pat):
        if any(p.lower() in _FORBIDDEN_DIR_NAMES for p in item.parts):
            continue
        if item.name.lower().startswith(".env") or _FORBIDDEN_FILE_RE.search(item.name):
            continue
        matches.append(
            {
                "name": item.name,
                "kind": "dir" if item.is_dir() else "file",
                "path": str(item),
            }
        )
        if len(matches) >= max(1, min(int(limit), 200)):
            break
    return {"ok": True, "root": str(base), "pattern": clean_pat, "count": len(matches), "matches": matches}


def read_text_file(raw_path: str | Path, *, max_bytes: int = 32768) -> dict[str, Any]:
    """Read a text file inside allowed roots with secret redaction."""
    target = _resolve_in_jail(raw_path)
    _assert_not_secret_path(target)
    if not target.is_file():
        raise WorkspaceGuardError(f"Файл не найден: {target}")
    raw = target.read_bytes()[: max(256, min(int(max_bytes), 131072))]
    if b"\x00" in raw:
        raise WorkspaceGuardError(f"Файл {target.name!r} бинарный — текстовое чтение отклонено")
    text = redact_secrets(raw.decode("utf-8", errors="replace"))
    return {
        "ok": True,
        "path": str(target),
        "bytes": target.stat().st_size,
        "truncated": target.stat().st_size > len(raw),
        "content": text,
    }


def create_dir(raw_path: str | Path) -> dict[str, Any]:
    """Create a folder inside allowed workspace roots (never overwrites or deletes anything)."""
    target = _resolve_in_jail(raw_path)
    _assert_not_secret_path(target)
    if target.exists() and not target.is_dir():
        raise WorkspaceGuardError(f"По пути {target} уже существует файл")
    existed = target.is_dir()
    target.mkdir(parents=True, exist_ok=True)
    return {"ok": True, "path": str(target), "created": not existed}


def delete_path(
    raw_path: str | Path,
    *,
    confirmed_by_user: bool = False,
    confirm_phrase: str = "",
) -> dict[str, Any]:
    """Fail-closed delete: ALWAYS refused unless user explicitly confirms with `DELETE <name>`."""
    target = _resolve_in_jail(raw_path)
    _assert_not_secret_path(target)
    expected = f"DELETE {target.name}"
    if not confirmed_by_user or confirm_phrase.strip() != expected:
        raise WorkspaceGuardError(
            f"СТОП: удаление без явного разрешения пользователя запрещено. "
            f"Требуется подтверждение '{expected}'."
        )
    if target.is_dir():
        raise WorkspaceGuardError("СТОП: рекурсивное удаление папок запрещено политикой безопасности.")
    if not target.is_file():
        raise WorkspaceGuardError(f"Файл не найден: {target}")
    target.unlink()
    return {"ok": True, "deleted": str(target)}
