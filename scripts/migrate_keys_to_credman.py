"""Move DUP Presenter API keys into Windows Credential Manager. Prints names and statuses only, never values.

  python scripts/migrate_keys_to_credman.py                 copy + verify (sources are left untouched)
  python scripts/migrate_keys_to_credman.py --remove-file-keys       also drop verified keys from secrets/media_keys.env
  python scripts/migrate_keys_to_credman.py --remove-registry-keys   also drop verified keys from the User environment

Sources: secrets/media_keys.env (PEXELS_API_KEY, PIXABAY_API_KEY) and HKCU\\Environment (provider keys).
A key already stored with a different value is a conflict: it is left alone unless --overwrite is given.
A source is removed only after the stored value was read back and matched exactly.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from credstore import (  # noqa: E402
    MEDIA_KEY_NAMES,
    PROVIDER_KEY_NAMES,
    CredStoreError,
    available,
    get_secret,
    set_secret,
)

ROOT = Path(__file__).resolve().parent.parent
MEDIA_ENV = ROOT / "secrets" / "media_keys.env"


def _read_media_file() -> dict[str, str]:
    found: dict[str, str] = {}
    if not MEDIA_ENV.is_file():
        return found
    for raw in MEDIA_ENV.read_text(encoding="utf-8-sig", errors="strict").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k in MEDIA_KEY_NAMES and v:
            found[k] = v
    return found


def _read_registry() -> dict[str, str]:
    import winreg

    found: dict[str, str] = {}
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
        for name in PROVIDER_KEY_NAMES:
            try:
                val, _ = winreg.QueryValueEx(key, name)
            except FileNotFoundError:
                continue
            if isinstance(val, str) and val.strip():
                found[name] = val.strip()
    return found


def _remove_file_keys(names: set[str]) -> None:
    lines = MEDIA_ENV.read_text(encoding="utf-8-sig", errors="strict").splitlines()
    kept = [ln for ln in lines if not ("=" in ln and ln.split("=", 1)[0].strip() in names)]
    tmp = MEDIA_ENV.with_suffix(".env.tmp")
    tmp.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    os.replace(tmp, MEDIA_ENV)


def _remove_registry_keys(names: set[str]) -> None:
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as key:
        for name in names:
            winreg.DeleteValue(key, name)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Move API keys into Windows Credential Manager (values never printed).")
    ap.add_argument("--overwrite", action="store_true", help="Replace a stored value that differs from the source")
    ap.add_argument("--remove-file-keys", action="store_true", help="Drop verified keys from secrets/media_keys.env")
    ap.add_argument("--remove-registry-keys", action="store_true", help="Drop verified keys from HKCU\\Environment")
    args = ap.parse_args(argv)

    if not available():
        print("ОТКАЗ: Windows Credential Manager есть только в Windows.", file=sys.stderr)
        return 2

    sources: list[tuple[str, str, str]] = []
    sources += [(n, "media_keys.env", v) for n, v in _read_media_file().items()]
    sources += [(n, "registry", v) for n, v in _read_registry().items()]
    if not sources:
        print("Ключей в старых местах не найдено.")
        return 0

    verified: dict[str, set[str]] = {"media_keys.env": set(), "registry": set()}
    failed = 0
    for name, origin, value in sources:
        try:
            stored = get_secret(name)
            if stored is not None and stored != value and not args.overwrite:
                status = "КОНФЛИКТ: в хранилище другое значение (не тронуто; --overwrite заменит)"
                failed += 1
            else:
                if stored != value:
                    set_secret(name, value)
                if get_secret(name) == value:
                    verified[origin].add(name)
                    status = "в хранилище, проверено" if stored != value else "уже было в хранилище, совпадает"
                else:
                    status = "ОШИБКА: обратное чтение не совпало"
                    failed += 1
        except CredStoreError as exc:
            status = f"ОШИБКА: {exc}"
            failed += 1
        print(f"{name:<22} {origin:<15} {status}")

    if args.remove_file_keys and verified["media_keys.env"]:
        _remove_file_keys(verified["media_keys.env"])
        print(f"Удалено из media_keys.env: {', '.join(sorted(verified['media_keys.env']))}")
    if args.remove_registry_keys and verified["registry"]:
        _remove_registry_keys(verified["registry"])
        print(f"Удалено из переменных Windows: {', '.join(sorted(verified['registry']))}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
