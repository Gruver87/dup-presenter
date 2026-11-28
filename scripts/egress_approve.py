"""Manual egress approval CLI for DUP Presenter.

Only a human at an interactive terminal can allow API keys or request data to leave this computer.
  python scripts/egress_approve.py --host api.dev.runwayml.com --ttl-min 15 --uses 100
  python scripts/egress_approve.py --list
  python scripts/egress_approve.py --revoke <id>
  python scripts/egress_approve.py --reset      (remove all grants; also clears a file with a bad signature)

Fail-closed:
  - Non-interactive runs (piped input, scheduled tasks, other programs) are refused.
  - You must type the exact phrase `APPROVE <host>`.
  - Only verified allow-listed hosts can be approved.
  - Grants expire (max 60 minutes) and are use-limited (max 500 requests).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from secret_guard import (  # noqa: E402
    EgressApprovalRequired,
    grant_egress_approval,
    list_egress_approvals,
    reset_egress_approvals,
    revoke_egress_approval,
)


def _fmt_ts(ts: int | None) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(ts or 0)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manually allow API keys/request data to a verified host.")
    parser.add_argument("--host", help="Host to approve, e.g. api.dev.runwayml.com")
    parser.add_argument("--ttl-min", type=int, default=15, help="Validity in minutes (1-60, default 15)")
    parser.add_argument("--uses", type=int, default=100, help="Max outbound requests (1-500, default 100)")
    parser.add_argument("--list", action="store_true", help="Show active approvals")
    parser.add_argument("--revoke", metavar="ID", help="Revoke an approval by id")
    parser.add_argument("--reset", action="store_true", help="Remove all approvals (writes an empty signed file)")
    args = parser.parse_args(argv)

    if args.reset:
        try:
            reset_egress_approvals()
        except EgressApprovalRequired as exc:
            print(f"ОТКАЗ: {exc}", file=sys.stderr)
            return 1
        print("Все разрешения удалены.")
        return 0

    if args.list:
        try:
            items = list_egress_approvals()
        except EgressApprovalRequired as exc:
            print(f"ОТКАЗ: {exc}", file=sys.stderr)
            return 1
        if not items:
            print("Активных разрешений нет. Ключи и данные никуда не уходят без вашего разрешения.")
        for it in items:
            print(f"{it['id']}  host={it['host']}  until={_fmt_ts(it['expires_ts'])}  uses_left={it['uses_left']}")
        return 0

    if args.revoke:
        ok = revoke_egress_approval(args.revoke)
        print("Отозвано." if ok else "Разрешение с таким id не найдено.")
        return 0 if ok else 1

    if not args.host:
        parser.error("укажите --host (или --list / --revoke)")

    if not sys.stdin.isatty():
        print("ОТКАЗ: нужен интерактивный терминал. Автоматическое разрешение запрещено.", file=sys.stderr)
        return 2

    host = args.host.strip().lower()
    print("Вы разрешаете программе отправлять API-ключи и данные запросов на этот сайт:")
    print(f"  хост:      {host}")
    print(f"  срок:      до {min(max(args.ttl_min, 1), 60)} мин")
    print(f"  запросов:  до {min(max(args.uses, 1), 500)}")
    print("Ключи уйдут только на этот хост. Отозвать: --revoke <id> или --list.")
    typed = input(f"Чтобы подтвердить, введите точно: APPROVE {host}\n> ").strip()

    try:
        rec = grant_egress_approval(host, ttl_min=args.ttl_min, uses=args.uses, confirm_text=typed)
    except EgressApprovalRequired as exc:
        print(f"ОТКАЗ: {exc}", file=sys.stderr)
        return 1
    print(f"Разрешение выдано: id={rec['id']} host={rec['host']} до {_fmt_ts(rec['expires_ts'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
