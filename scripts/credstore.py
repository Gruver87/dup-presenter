"""DUP Presenter — API keys in Windows Credential Manager (no third-party packages).

Each secret is a generic credential named "DUP-Presenter/<NAME>" persisted for the current Windows user
(Windows encrypts it with the user's logon credentials). Values are never logged or returned by listing.
On non-Windows systems the store is unavailable and every call raises CredStoreUnavailable.
"""

from __future__ import annotations

import ctypes
import os
import re
from ctypes import wintypes

TARGET_PREFIX = "DUP-Presenter/"
NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
MAX_BLOB_BYTES = 5 * 512  # CRED_MAX_CREDENTIAL_BLOB_SIZE

# Provider keys the studio reads from the environment (never stored in code or chat).
PROVIDER_KEY_NAMES: tuple[str, ...] = (
    "DUP_LLM_BASE_URL", "DUP_LLM_MODEL", "DUP_LLM_API_KEY",
    "SERPER_API_KEY", "BRAVE_API_KEY", "TRIPO_API_KEY", "FAL_KEY",
    "RUNWAYML_API_SECRET",
)
MEDIA_KEY_NAMES: tuple[str, ...] = ("PEXELS_API_KEY", "PIXABAY_API_KEY")

_CRED_TYPE_GENERIC = 1
_CRED_PERSIST_LOCAL_MACHINE = 2
_ERROR_NOT_FOUND = 1168


class CredStoreError(RuntimeError):
    """Credential Manager call failed; the caller must stop instead of guessing a value."""


class CredStoreUnavailable(CredStoreError):
    """Credential Manager does not exist on this system."""


class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]


class _CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", _FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


_PCRED = ctypes.POINTER(_CREDENTIALW)
_api = None


def available() -> bool:
    """True when Windows Credential Manager can be used on this system."""
    return os.name == "nt"


def _advapi():
    global _api
    if not available():
        raise CredStoreUnavailable("Windows Credential Manager is only available on Windows.")
    if _api is None:
        lib = ctypes.WinDLL("advapi32", use_last_error=True)
        lib.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(_PCRED)]
        lib.CredReadW.restype = wintypes.BOOL
        lib.CredWriteW.argtypes = [_PCRED, wintypes.DWORD]
        lib.CredWriteW.restype = wintypes.BOOL
        lib.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        lib.CredDeleteW.restype = wintypes.BOOL
        lib.CredEnumerateW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(ctypes.POINTER(_PCRED)),
        ]
        lib.CredEnumerateW.restype = wintypes.BOOL
        lib.CredFree.argtypes = [ctypes.c_void_p]
        lib.CredFree.restype = None
        _api = lib
    return _api


def _target(name: str) -> str:
    if not NAME_RE.match(name or ""):
        raise CredStoreError(f"Invalid secret name {name!r}: use 2-64 chars A-Z, 0-9, '_' starting with a letter.")
    return TARGET_PREFIX + name


def get_secret(name: str) -> str | None:
    """Return the stored value for `name`, or None when it is not stored."""
    target = _target(name)
    api = _advapi()
    pcred = _PCRED()
    if not api.CredReadW(target, _CRED_TYPE_GENERIC, 0, ctypes.byref(pcred)):
        err = ctypes.get_last_error()
        if err == _ERROR_NOT_FOUND:
            return None
        raise CredStoreError(f"CredReadW failed for {target} (Windows error {err}).")
    try:
        cred = pcred.contents
        raw = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize) if cred.CredentialBlobSize else b""
    finally:
        api.CredFree(pcred)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CredStoreError(f"Stored value for {target} is not UTF-8; refusing to use it.") from exc


def set_secret(name: str, value: str) -> None:
    """Store `value` under `name` for the current Windows user (overwrites an existing value)."""
    target = _target(name)
    if not isinstance(value, str) or not value:
        raise CredStoreError(f"Refusing to store an empty value for {target}.")
    blob = value.encode("utf-8")
    if len(blob) > MAX_BLOB_BYTES:
        raise CredStoreError(f"Value for {target} is {len(blob)} bytes; Credential Manager limit is {MAX_BLOB_BYTES}.")
    api = _advapi()
    buf = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
    cred = _CREDENTIALW()
    cred.Type = _CRED_TYPE_GENERIC
    cred.TargetName = target
    cred.CredentialBlobSize = len(blob)
    cred.CredentialBlob = ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte))
    cred.Persist = _CRED_PERSIST_LOCAL_MACHINE
    cred.UserName = name
    if not api.CredWriteW(ctypes.byref(cred), 0):
        raise CredStoreError(f"CredWriteW failed for {target} (Windows error {ctypes.get_last_error()}).")


def delete_secret(name: str) -> bool:
    """Delete `name`; True if it existed, False if it was not stored."""
    target = _target(name)
    api = _advapi()
    if api.CredDeleteW(target, _CRED_TYPE_GENERIC, 0):
        return True
    err = ctypes.get_last_error()
    if err == _ERROR_NOT_FOUND:
        return False
    raise CredStoreError(f"CredDeleteW failed for {target} (Windows error {err}).")


def list_names() -> list[str]:
    """Names (never values) of all secrets stored under the DUP-Presenter prefix."""
    api = _advapi()
    count = wintypes.DWORD(0)
    creds = ctypes.POINTER(_PCRED)()
    if not api.CredEnumerateW(TARGET_PREFIX + "*", 0, ctypes.byref(count), ctypes.byref(creds)):
        err = ctypes.get_last_error()
        if err == _ERROR_NOT_FOUND:
            return []
        raise CredStoreError(f"CredEnumerateW failed (Windows error {err}).")
    try:
        names = [creds[i].contents.TargetName[len(TARGET_PREFIX):] for i in range(count.value)]
    finally:
        api.CredFree(creds)
    return sorted(n for n in names if NAME_RE.match(n))
