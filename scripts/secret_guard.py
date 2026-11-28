"""Fail-closed Secret Egress Guard for DUP Presenter.

Invariant:
  No secret value (from environment variables or known credential formats) may ever
  leave this computer in outbound HTTP URLs, bodies, prompts, non-allowlisted headers,
  logs, or HTTP responses from the local console server.

Mechanism:
  1. `collect_secret_values()` scans `os.environ` for any variable whose name looks
     like a secret (KEY, SECRET, TOKEN, PASSWORD, CREDENTIAL, AUTH, PRIVATE, JWT, etc.)
     and returns values of length >= 8.
  2. `assert_no_secrets_in_text(text)` raises `SecretLeakError` if any live env secret
     or known secret pattern (PEM private key, sk-..., ghp_..., AKIA..., JWT, etc.)
     appears in outbound prompts or payloads.
  3. `redact_secrets(obj)` recursively scrubs any live env secret or secret pattern
     from strings/dicts/lists before logging or returning JSON responses.
  4. `install_egress_guard()` wraps `urllib.request.urlopen` process-wide so EVERY
     outbound HTTP request in the process is inspected BEFORE a single byte is sent:
       - Blocks any live env secret or secret pattern in URL, body, or non-auth headers.
       - Enforces strict host allow-lists for known API keys in auth headers
         (e.g., RUNWAYML_API_SECRET may ONLY be sent to api.dev.runwayml.com).
       - Refuses plain HTTP to non-localhost hosts (TLS required).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

from credstore import CredStoreError, get_secret, set_secret

_SECRET_NAME_TOKENS: frozenset[str] = frozenset(
    {
        "KEY", "KEYS", "SECRET", "SECRETS", "TOKEN", "TOKENS", "PASS", "PASSWORD", "PASSWORDS", "PWD",
        "CREDENTIAL", "CREDENTIALS", "AUTH", "PRIVATE", "COOKIE", "JWT", "BEARER", "SIGNING", "PAT",
    }
)
# Known non-secret variables that merely contain a secret-like token (e.g. PATH -> "PAT" substring).
_SECRET_NAME_EXCLUDE: frozenset[str] = frozenset(
    {"PATH", "PATHEXT", "PSMODULEPATH", "HOMEPATH", "HOMEPATHS"}
)

# High-confidence secret patterns that should never appear in prompts, URLs, bodies, or logs.
_SECRET_VALUE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("pem_private_key", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    ("openai_key", re.compile(r"\bsk-(?:proj-|live-|test-)?[A-Za-z0-9_-]{20,}\b")),
    ("github_pat", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b")),
    ("github_fine_pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("runway_key", re.compile(r"\bkey_[a-f0-9]{32,}\b")),
    ("jwt_token", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
)

# Strict host allow-list for known secret env vars when sent in Authorization / API-key headers.
# If an env var is listed here, it may ONLY be transmitted in an auth header to these exact hosts.
SECRET_HOST_ALLOWLIST: dict[str, frozenset[str]] = {
    "RUNWAYML_API_SECRET": frozenset({"api.dev.runwayml.com"}),
    "SERPER_API_KEY": frozenset({"google.serper.dev"}),
    "BRAVE_API_KEY": frozenset({"api.search.brave.com"}),
    "OPENAI_API_KEY": frozenset({"api.openai.com"}),
    "DEEPSEEK_API_KEY": frozenset({"api.deepseek.com"}),
    "GITHUB_TOKEN": frozenset({"api.github.com", "uploads.github.com"}),
    "GH_TOKEN": frozenset({"api.github.com", "uploads.github.com"}),
    "PEXELS_API_KEY": frozenset({"api.pexels.com"}),
    "PIXABAY_API_KEY": frozenset({"pixabay.com"}),
    "TRIPO_API_KEY": frozenset({"api.tripo3d.ai"}),
    "FAL_KEY": frozenset({"queue.fal.run"}),
    "TIKTOK_ACCESS_TOKEN": frozenset({"open.tiktokapis.com"}),
    "TIKTOK_REFRESH_TOKEN": frozenset({"open.tiktokapis.com"}),
    "TIKTOK_CLIENT_KEY": frozenset({"open.tiktokapis.com"}),
    "TIKTOK_CLIENT_SECRET": frozenset({"open.tiktokapis.com"}),
}
# Only these secrets may appear in a request body, and only to their bound host (TikTok OAuth form fields).
BODY_BINDABLE_SECRETS: frozenset[str] = frozenset(
    {"TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN"}
)
# Every secret name that is NOT listed here (or bound dynamically in `_secret_bindings`) can never
# leave the machine: it is refused in any header, body, or URL. This is fail-closed by default.

_AUTH_HEADER_NAMES: frozenset[str] = frozenset(
    {"authorization", "x-api-key", "x-subscription-token", "api-key"}
)

_LOCAL_HOSTS: frozenset[str] = frozenset({"127.0.0.1", "localhost", "::1"})

# Strict default-deny allow-list of genuine official domains used by DUP Presenter.
# Exact hosts or suffix matches (leading dot = subdomains allowed).
ALLOWED_OUTBOUND_EXACT_HOSTS: frozenset[str] = frozenset(
    {
        "api.dev.runwayml.com",
        "google.serper.dev",
        "api.search.brave.com",
        "api.openai.com",
        "api.deepseek.com",
        "api.anthropic.com",
        "api.pexels.com",
        "images.pexels.com",
        "videos.pexels.com",
        "pixabay.com",
        "cdn.pixabay.com",
        "github.com",
        "api.github.com",
        "raw.githubusercontent.com",
        "uploads.github.com",
        "api.tripo3d.ai",
        "queue.fal.run",
        "open.tiktokapis.com",
        "speech.platform.bing.com",
    }
)
# Suffix matches are only for hosts controlled by the provider. Shared CDNs (cloudfront, githubusercontent)
# were removed: anyone can host content there, so they must never receive credentials or data.
ALLOWED_OUTBOUND_SUFFIXES: tuple[str, ...] = (
    ".runwayml.com",
    ".pexels.com",
    ".pixabay.com",
)

# Always-blocked threat indicators (even before allow-list check).
_BLOCKED_TLDS: frozenset[str] = frozenset(
    {".tk", ".ml", ".ga", ".cf", ".gq", ".zip", ".mov", ".onion", ".bit", ".top", ".xyz", ".click"}
)
_URL_SHORTENERS: frozenset[str] = frozenset(
    {"bit.ly", "tinyurl.com", "t.co", "is.gd", "cutt.ly", "rb.gy", "ow.ly", "goo.gl", "clck.ru"}
)
_SHADY_HOST_RE = re.compile(
    r"(porn|xxx|adult|casino|betting|slots|crack|warez|keygen|phish|malware|stealer|free-nitro|login-verify)",
    re.IGNORECASE,
)
_IPV4_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")

_GUARD_INSTALLED = False
_ORIG_URLOPEN = urllib.request.urlopen


class SecretLeakError(RuntimeError):
    """Raised fail-closed when a secret is about to leave the machine."""


class OutboundThreatError(SecretLeakError):
    """Raised fail-closed when an outbound request targets an unverified or threatening host."""


def _is_secret_env_name(name: str) -> bool:
    """Match whole underscore-separated tokens (RUNWAYML_API_SECRET -> SECRET), never substrings (PATH -> PAT)."""
    upper = name.upper()
    if upper in _SECRET_NAME_EXCLUDE:
        return False
    return any(tok in _SECRET_NAME_TOKENS for tok in re.split(r"[_\-\s]+", upper) if tok)


def collect_secret_env() -> dict[str, str]:
    """Return {env_name: value} for all non-trivial secret-like environment variables."""
    out: dict[str, str] = {}
    for k, v in os.environ.items():
        if not v or len(v) < 8:
            continue
        if _is_secret_env_name(k):
            out[k] = v
    return out


def _find_secret_in_text(text: str, env_secrets: dict[str, str] | None = None) -> str | None:
    """Return a safe description of the first secret found in `text`, or None."""
    if not text:
        return None
    secrets = env_secrets if env_secrets is not None else collect_secret_env()
    for name, val in secrets.items():
        if val in text:
            return f"env:{name}"
    for label, rx in _SECRET_VALUE_PATTERNS:
        if rx.search(text):
            return f"pattern:{label}"
    return None


def assert_no_secrets_in_text(text: str, *, context: str = "outbound payload") -> None:
    """Fail-closed check: raise SecretLeakError if `text` contains any secret."""
    hit = _find_secret_in_text(text)
    if hit:
        raise SecretLeakError(
            f"Blocked {context}: detected secret ({hit}). Secrets are never allowed to leave this machine."
        )


def redact_secrets(value: Any, *, _env_secrets: dict[str, str] | None = None) -> Any:
    """Recursively redact all live env secrets and secret patterns from strings/dicts/lists."""
    secrets = _env_secrets if _env_secrets is not None else collect_secret_env()
    if isinstance(value, str):
        s = value
        for name, secret_val in secrets.items():
            if secret_val in s:
                s = s.replace(secret_val, f"[REDACTED:{name}]")
        for label, rx in _SECRET_VALUE_PATTERNS:
            s = rx.sub(f"[REDACTED:{label}]", s)
        return s
    if isinstance(value, dict):
        return {k: redact_secrets(v, _env_secrets=secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_secrets(v, _env_secrets=secrets) for v in value]
    if isinstance(value, tuple):
        return tuple(redact_secrets(v, _env_secrets=secrets) for v in value)
    return value


def _check_host_safety(parsed: urllib.parse.ParseResult, *, strict: bool = True) -> None:
    """Fail-closed domain policy.

    Threat screen (always, both tiers): credentials-in-URL, non-HTTPS, raw IPs, punycode,
    URL shorteners, dangerous TLDs, shady/inappropriate hostnames.

    strict=True (any request carrying auth, body, or non-GET): host must be on the verified allow-list.
    strict=False (anonymous public read-only GET): any host that passes the threat screen.
    """
    host = (parsed.hostname or "").lower().rstrip(".")
    scheme = (parsed.scheme or "").lower()

    if not host:
        raise OutboundThreatError("СТОП: пустой или некорректный хост в исходящем запросе")

    # 1. Block embedded credentials in URL (phishing / obfuscation trick: https://good.com@evil.com)
    if parsed.username or parsed.password:
        raise OutboundThreatError(f"СТОП: обнаружены учётные данные в URL (признак фишинга) для {host!r}")

    # 2. Allow loopback localhost only (local Ollama / local console server)
    if host in _LOCAL_HOSTS:
        if scheme not in {"http", "https"}:
            raise OutboundThreatError(f"СТОП: недопустимая схема {scheme!r} для локального хоста")
        return

    # 3. Require HTTPS for all remote hosts
    if scheme != "https":
        raise OutboundThreatError(f"СТОП: запрещён незашифрованный протокол {scheme!r} для {host!r} (нужен HTTPS)")

    # 4. Block raw IP addresses (prevents SSRF to LAN/cloud metadata and bypass of domain checks)
    if _IPV4_RE.match(host) or ":" in host:
        raise OutboundThreatError(f"СТОП: запрещены прямые запросы по IP-адресу {host!r}")

    # 5. Block Punycode / IDN homograph phishing domains (xn--...)
    if any(label.startswith("xn--") for label in host.split(".")):
        raise OutboundThreatError(f"СТОП: обнаружен Punycode-домен {host!r} (риск фишинга/подмены)")

    # 6. Block URL shorteners, high-risk TLDs, and shady/inappropriate hostnames
    if host in _URL_SHORTENERS or any(host.endswith("." + s) for s in _URL_SHORTENERS):
        raise OutboundThreatError(f"СТОП: запрещён сокращатель ссылок {host!r} (скрывает реальный сайт)")
    if any(host.endswith(tld) for tld in _BLOCKED_TLDS):
        raise OutboundThreatError(f"СТОП: заблокирована опасная доменная зона для {host!r}")
    if _SHADY_HOST_RE.search(host):
        raise OutboundThreatError(f"СТОП: заблокирован подозрительный/неподобающий домен {host!r}")

    # Anonymous public read: threat screen passed -> allowed.
    if not strict:
        return

    # 7. Default-deny allow-list for requests that send credentials, bodies, or write
    if host in _allowed_exact_hosts() or any(host.endswith(sfx) for sfx in ALLOWED_OUTBOUND_SUFFIXES):
        return
    extra_raw = os.environ.get("DUP_ALLOWED_DOMAINS", "").strip()
    if extra_raw:
        extra = {d.strip().lower().rstrip(".") for d in extra_raw.split(",") if d.strip()}
        if host in extra:
            return

    raise OutboundThreatError(
        f"СТОП: домен {host!r} не входит в список проверенных сайтов для запросов с ключами/данными. Запрос заблокирован."
    )


def _llm_host() -> str:
    """Host of the configured OpenAI-compatible LLM endpoint (DUP_LLM_BASE_URL, default api.openai.com)."""
    raw = os.environ.get("DUP_LLM_BASE_URL", "").strip() or "https://api.openai.com/v1"
    return (urllib.parse.urlparse(raw).hostname or "").lower()


def _secret_bindings() -> dict[str, frozenset[str]]:
    """Exact host(s) each secret env name may be transmitted to. Unlisted names are never transmitted."""
    bindings = dict(SECRET_HOST_ALLOWLIST)
    llm = _llm_host()
    if llm:
        for name in ("DUP_LLM_API_KEY", "LLM_API_KEY"):
            bindings[name] = frozenset({llm})
    return bindings


def _allowed_exact_hosts() -> frozenset[str]:
    """Hosts allowed for requests that carry credentials or data: static list + every key binding."""
    hosts = set(ALLOWED_OUTBOUND_EXACT_HOSTS)
    for allowed in _secret_bindings().values():
        hosts |= set(allowed)
    return frozenset(hosts)


def open_read_enabled() -> bool:
    """Anonymous public read-only browsing is ON by default; set DUP_OPEN_READ=0 to force allow-list only."""
    return os.environ.get("DUP_OPEN_READ", "1").strip() not in {"0", "false", "False", "no"}


# ---------------------------------------------------------------------------
# Manual egress approvals: keys and request data leave the machine ONLY after a human grants it.
# Grants are created exclusively by `scripts/egress_approve.py` in an interactive terminal
# (typed confirmation). Web pages and code cannot create them. Each grant is host-bound,
# time-limited and use-limited, and is consumed per outbound request that carries credentials or data.
# ---------------------------------------------------------------------------

APPROVALS_FILE: Path = Path(__file__).resolve().parent.parent / "out" / "egress_approvals.json"
APPROVAL_MAX_TTL_MIN = 60
APPROVAL_MAX_USES = 500
_APPROVAL_LOCK = threading.Lock()


class EgressApprovalRequired(SecretLeakError):
    """Raised fail-closed when credentials or request data would leave without a manual approval."""


# The approvals file is signed with HMAC-SHA256; the key lives in Windows Credential Manager, never on disk.
# A file with a wrong signature blocks all egress until reset; a legacy unsigned list grants nothing.
APPROVALS_FORMAT = "dup-egress-approvals-v1"
APPROVALS_MAC_KEY_NAME = "DUP_EGRESS_APPROVALS_HMAC_KEY"
_RESET_HINT = "Сброс (все разрешения будут удалены): python scripts/egress_approve.py --reset"


def _approval_mac_key(create: bool) -> bytes | None:
    """HMAC key for the approvals file; with create=True a random key is generated on first use."""
    try:
        stored = get_secret(APPROVALS_MAC_KEY_NAME)
        if stored is None and create:
            set_secret(APPROVALS_MAC_KEY_NAME, secrets.token_hex(32))
            stored = get_secret(APPROVALS_MAC_KEY_NAME)
    except CredStoreError as exc:
        raise EgressApprovalRequired(f"Ключ подписи файла разрешений недоступен ({exc}); отправка заблокирована.") from exc
    if stored is None:
        if create:
            raise EgressApprovalRequired("Не удалось сохранить ключ подписи файла разрешений; отправка заблокирована.")
        return None
    if not re.fullmatch(r"[0-9a-f]{64}", stored):
        raise EgressApprovalRequired("Ключ подписи файла разрешений имеет неверный формат; отправка заблокирована.")
    return bytes.fromhex(stored)


def _approvals_mac(key: bytes, records: list[Any]) -> str:
    payload = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(key, APPROVALS_FORMAT.encode("ascii") + b"\n" + payload, hashlib.sha256).hexdigest()


def _load_approvals_locked() -> list[dict[str, Any]]:
    if not APPROVALS_FILE.is_file():
        return []
    try:
        data = json.loads(APPROVALS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EgressApprovalRequired(
            f"Файл разрешений {APPROVALS_FILE.name} повреждён; отправка заблокирована до исправления. {_RESET_HINT}"
        ) from exc
    if isinstance(data, list):
        return []
    if (
        not isinstance(data, dict)
        or data.get("format") != APPROVALS_FORMAT
        or not isinstance(data.get("records"), list)
        or not isinstance(data.get("mac"), str)
    ):
        raise EgressApprovalRequired(f"Файл разрешений имеет неверный формат; отправка заблокирована. {_RESET_HINT}")
    key = _approval_mac_key(create=False)
    if key is None:
        raise EgressApprovalRequired(f"Файл разрешений подписан, но ключа подписи нет; отправка заблокирована. {_RESET_HINT}")
    if not hmac.compare_digest(_approvals_mac(key, data["records"]), data["mac"]):
        raise EgressApprovalRequired(
            f"Подпись файла разрешений не совпала: файл изменён не этой программой; отправка заблокирована. {_RESET_HINT}"
        )
    return [r for r in data["records"] if isinstance(r, dict)]


def _save_approvals_locked(records: list[dict[str, Any]]) -> None:
    key = _approval_mac_key(create=True)
    doc = {"format": APPROVALS_FORMAT, "records": records, "mac": _approvals_mac(key, records)}
    APPROVALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = APPROVALS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, APPROVALS_FILE)


def reset_egress_approvals() -> None:
    """Remove every grant by writing an empty signed file. Only reduces permissions, so no confirmation is needed."""
    with _APPROVAL_LOCK:
        _save_approvals_locked([])


def _approval_host_is_allowed(host: str) -> bool:
    """A manual grant can only extend hosts that pass the threat screen AND the verified allow-list."""
    try:
        _check_host_safety(urllib.parse.urlparse(f"https://{host}/"), strict=True)
    except OutboundThreatError:
        return False
    return True


def active_approval(host: str) -> dict[str, Any] | None:
    """Non-consuming check: return the first valid grant for `host`, or None."""
    now = int(time.time())
    with _APPROVAL_LOCK:
        for rec in _load_approvals_locked():
            if rec.get("host") == host and int(rec.get("expires_ts", 0)) > now and int(rec.get("uses_left", 0)) > 0:
                return {"id": rec.get("id"), "expires_ts": rec.get("expires_ts"), "uses_left": rec.get("uses_left")}
    return None


_APPROVAL_RENEWER: Callable[[str], bool] | None = None


def set_approval_renewer(renewer: Callable[[str], bool] | None) -> None:
    """Register an on-demand renewer: called with a host when no valid grant exists; returns True if it granted.

    The dashboard registers one that grants only while its internet toggle is ON (the toggle is the user's
    standing consent) and only for its own managed hosts. None disables renewal.
    """
    global _APPROVAL_RENEWER
    _APPROVAL_RENEWER = renewer


def _try_renew(host: str) -> bool:
    renewer = _APPROVAL_RENEWER
    if renewer is None:
        return False
    try:
        return bool(renewer(host))
    except Exception as exc:  # renewal failure must refuse, never silently allow
        raise EgressApprovalRequired(
            f"СТОП: не удалось выдать разрешение для {host!r}; отправка заблокирована: {redact_secrets(str(exc))}"
        ) from exc


def ensure_egress_approval(host: str) -> dict[str, Any] | None:
    """Non-consuming check that renews on demand: valid grant for `host` (renewing if allowed), else None."""
    rec = active_approval(host)
    if rec is None and _try_renew(host):
        rec = active_approval(host)
    return rec


def _spend_one_use(host: str) -> dict[str, Any] | None:
    now = int(time.time())
    with _APPROVAL_LOCK:
        records = _load_approvals_locked()
        for rec in records:
            if rec.get("host") != host:
                continue
            if int(rec.get("expires_ts", 0)) <= now or int(rec.get("uses_left", 0)) <= 0:
                continue
            rec["uses_left"] = int(rec["uses_left"]) - 1
            _save_approvals_locked(records)
            return {"id": rec.get("id"), "uses_left": rec["uses_left"]}
    return None


def consume_egress_approval(host: str) -> dict[str, Any]:
    """Spend one use of a valid grant for `host` (renewing on demand if allowed); otherwise raise."""
    spent = _spend_one_use(host)
    if spent is None and _try_renew(host):
        spent = _spend_one_use(host)
    if spent is not None:
        return spent
    raise EgressApprovalRequired(
        f"СТОП: отправка ключей или данных на {host!r} без вашего ручного разрешения запрещена. "
        f"Выдайте разрешение в терминале: python scripts/egress_approve.py --host {host}"
    )


def grant_egress_approval(host: str, *, ttl_min: int, uses: int, confirm_text: str) -> dict[str, Any]:
    """Create a manual grant. Only callable from the interactive CLI, which requires typed confirmation."""
    clean_host = (host or "").strip().lower().rstrip(".")
    if not clean_host or "/" in clean_host or "@" in clean_host or ":" in clean_host:
        raise EgressApprovalRequired("Некорректное имя хоста для разрешения")
    if confirm_text != f"APPROVE {clean_host}":
        raise EgressApprovalRequired(f"Подтверждение не совпало. Нужно ввести точно: APPROVE {clean_host}")
    if not _approval_host_is_allowed(clean_host):
        raise EgressApprovalRequired(
            f"Хост {clean_host!r} не входит в проверенный список или заблокирован угрозой; разрешение не выдано."
        )
    ttl = max(1, min(int(ttl_min), APPROVAL_MAX_TTL_MIN))
    use_count = max(1, min(int(uses), APPROVAL_MAX_USES))
    record = {
        "id": secrets.token_hex(8),
        "host": clean_host,
        "created_ts": int(time.time()),
        "expires_ts": int(time.time()) + ttl * 60,
        "uses_left": use_count,
        "granted_by": "manual-cli",
    }
    with _APPROVAL_LOCK:
        now = int(time.time())
        records = [r for r in _load_approvals_locked() if int(r.get("expires_ts", 0)) > now]
        # One live grant per host: an existing valid grant is returned as-is. Re-granting must not
        # reset uses_left or extend the window, otherwise every automatic sync would refill the cap.
        for existing in records:
            if existing.get("host") == clean_host and int(existing.get("uses_left", 0)) > 0:
                _save_approvals_locked(records)
                return {k: existing.get(k) for k in ("id", "host", "created_ts", "expires_ts", "uses_left", "granted_by")}
        records.append(record)
        _save_approvals_locked(records)
    return record


def list_egress_approvals() -> list[dict[str, Any]]:
    """List active grants (no secrets are stored or shown)."""
    now = int(time.time())
    with _APPROVAL_LOCK:
        return [
            {k: r.get(k) for k in ("id", "host", "expires_ts", "uses_left")}
            for r in _load_approvals_locked()
            if int(r.get("expires_ts", 0)) > now
        ]


def revoke_egress_approval(approval_id: str) -> bool:
    with _APPROVAL_LOCK:
        records = _load_approvals_locked()
        kept = [r for r in records if r.get("id") != approval_id]
        if len(kept) == len(records):
            return False
        _save_approvals_locked(kept)
        return True


def inspect_outbound_request(url_or_req: Any, data: bytes | None = None) -> None:
    """Inspect an outbound urllib request before it hits the network. Raises SecretLeakError on violation."""
    method = "GET"
    if isinstance(url_or_req, urllib.request.Request):
        url = url_or_req.full_url
        req_data = data if data is not None else url_or_req.data
        headers = dict(url_or_req.header_items())
        method = url_or_req.get_method().upper()
    else:
        url = str(url_or_req)
        req_data = data
        headers = {}

    parsed = urllib.parse.urlparse(url)
    has_auth = any(h.lower() in _AUTH_HEADER_NAMES for h in headers)
    anonymous_read = (
        open_read_enabled() and method == "GET" and not has_auth and req_data is None
    )
    _check_host_safety(parsed, strict=not anonymous_read)
    host = (parsed.hostname or "").lower().rstrip(".")

    env_secrets = collect_secret_env()

    # 2. Never allow any secret in URL / query string (except Pixabay which uses query param on pixabay.com).
    url_hit = _find_secret_in_text(url, env_secrets)
    if url_hit:
        if not (url_hit == "env:PIXABAY_API_KEY" and host == "pixabay.com"):
            raise SecretLeakError(f"Blocked secret ({url_hit}) in outbound URL to {host!r}")

    bindings = _secret_bindings()

    # 3. A secret may appear in a request body ONLY if it is bound to this exact host (e.g. TikTok client_secret
    #    in its own OAuth form). Any other secret in a body is refused.
    if req_data is not None:
        if isinstance(req_data, (bytes, bytearray)):
            body_text = req_data.decode("utf-8", errors="ignore")
        else:
            body_text = str(req_data)
        for env_name, secret_val in env_secrets.items():
            if secret_val not in body_text:
                continue
            if env_name not in BODY_BINDABLE_SECRETS or host not in bindings.get(env_name, frozenset()):
                raise SecretLeakError(
                    f"Blocked secret {env_name} in request body to {host!r}: "
                    f"this key may not appear in a body for that host"
                )

    # 4. Inspect headers: non-auth headers must NEVER contain secrets; auth headers must match host allow-list.
    for h_name, h_val in headers.items():
        h_low = h_name.lower()
        h_str = str(h_val)
        if h_low not in _AUTH_HEADER_NAMES:
            hit = _find_secret_in_text(h_str, env_secrets)
            if hit:
                raise SecretLeakError(f"Blocked secret ({hit}) in non-auth header {h_name!r} to {host!r}")
            continue
        # Auth header: EVERY secret value present must be bound to this exact host. Unknown names are refused.
        for env_name, secret_val in env_secrets.items():
            if secret_val in h_str:
                allowed_hosts = bindings.get(env_name)
                if not allowed_hosts:
                    raise SecretLeakError(
                        f"Blocked {env_name}: this key is not bound to any host and can never be transmitted"
                    )
                if host not in allowed_hosts:
                    raise SecretLeakError(
                        f"Blocked {env_name} from being sent to unauthorized host {host!r} "
                        f"(allowed: {sorted(allowed_hosts)})"
                    )

    # Manual gate: credentials, request bodies, or non-GET writes need a human-granted, host-bound approval.
    sends_credentials = has_auth
    sends_data = req_data is not None or method != "GET"
    if sends_credentials or sends_data:
        if anonymous_read:  # defensive: anonymous read never reaches here
            return
        # Loopback traffic never leaves this computer (local Ollama, local console). The approval gate
        # protects data leaving the machine; secret bindings above still refuse any key to loopback.
        if host in _LOCAL_HOSTS:
            return
        consume_egress_approval(host)


class _GuardedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Every redirect hop is inspected again. A redirect that would move credentials or data to another host is refused."""

    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Any:
        old_host = (urllib.parse.urlparse(req.full_url).hostname or "").lower()
        new_host = (urllib.parse.urlparse(newurl).hostname or "").lower()
        carries_credentials = any(h.lower() in _AUTH_HEADER_NAMES for h in dict(req.header_items()))
        carries_data = req.data is not None
        if new_host != old_host and (carries_credentials or carries_data):
            raise OutboundThreatError(
                f"СТОП: редирект с ключом или данными с {old_host!r} на другой хост {new_host!r} запрещён"
            )
        new_req = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new_req is not None:
            inspect_outbound_request(new_req)
        return new_req


_GUARDED_OPENER = urllib.request.build_opener(_GuardedRedirectHandler)


def _guarded_urlopen(url: Any, data: Any = None, *args: Any, **kwargs: Any) -> Any:
    if args:
        raise SecretLeakError("Неподдерживаемые позиционные аргументы urlopen под защитой egress")
    timeout = kwargs.pop("timeout", 30.0)
    if kwargs:
        raise SecretLeakError(f"Неподдерживаемые аргументы urlopen под защитой egress: {sorted(kwargs)}")
    inspect_outbound_request(url, data=data)
    return _GUARDED_OPENER.open(url, data, timeout=timeout)


_HTTPX_GUARD_INSTALLED = False


_BODILESS_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "DELETE"})


def _inspect_httpx_request(request: Any) -> None:
    """Run the same egress inspection on an httpx.Request before it is sent (each redirect hop included)."""
    method = str(request.method).upper()
    url = str(request.url)
    headers = {str(k): str(v) for k, v in request.headers.items()}
    try:
        body: bytes = request.content
    except Exception as exc:  # unread stream: only bodiless methods may be read here
        # Redirect hops of GET/HEAD/OPTIONS/DELETE have no payload; read them so the body is inspected
        # like any other request. Any other unread stream is refused (fail-closed).
        if method not in _BODILESS_METHODS:
            raise SecretLeakError(
                "Потоковое тело запроса нельзя проверить на ключи и данные; отправка заблокирована"
            ) from exc
        request.read()
        body = request.content
    inspect_outbound_request(
        urllib.request.Request(url, data=body or None, headers=headers, method=method)
    )


def _install_httpx_guard() -> bool:
    """Wrap httpx's per-hop send so TikTok / Pexels / archive / visual clients obey the same rules."""
    global _HTTPX_GUARD_INSTALLED
    if _HTTPX_GUARD_INSTALLED:
        return True
    try:
        import httpx
    except ImportError:
        return False
    orig_sync = httpx.Client._send_single_request
    orig_async = httpx.AsyncClient._send_single_request

    def _guarded_sync(self: Any, request: Any) -> Any:
        _inspect_httpx_request(request)
        return orig_sync(self, request)

    async def _guarded_async(self: Any, request: Any) -> Any:
        _inspect_httpx_request(request)
        return await orig_async(self, request)

    httpx.Client._send_single_request = _guarded_sync  # type: ignore[method-assign]
    httpx.AsyncClient._send_single_request = _guarded_async  # type: ignore[method-assign]
    _HTTPX_GUARD_INSTALLED = True
    return True


def install_egress_guard() -> bool:
    """Install the process-wide urllib.request.urlopen secret egress guard (idempotent)."""
    global _GUARD_INSTALLED, _ORIG_URLOPEN
    if _GUARD_INSTALLED:
        return True
    _ORIG_URLOPEN = urllib.request.urlopen
    urllib.request.urlopen = _guarded_urlopen  # type: ignore[assignment]
    _GUARD_INSTALLED = True
    _install_httpx_guard()
    return True


def guard_status() -> dict[str, Any]:
    """Return honest status of the secret & domain egress guard (never returns secret values)."""
    try:
        active: int | None = len(list_egress_approvals())
        approvals_error = ""
    except EgressApprovalRequired as exc:
        active, approvals_error = None, str(exc)
    return {
        "installed": _GUARD_INSTALLED,
        "urllib_guard": _GUARD_INSTALLED,
        "httpx_guard": _HTTPX_GUARD_INSTALLED,
        "redirect_hops_inspected": True,
        "secret_bindings_count": len(_secret_bindings()),
        "tracked_env_secrets_count": len(collect_secret_env()),
        "allowlisted_hosts_count": len(ALLOWED_OUTBOUND_EXACT_HOSTS),
        "anonymous_public_read": open_read_enabled(),
        "auth_and_write_default_deny": True,
        "manual_approval_required_for_keys_and_data": True,
        "active_approvals": active,
        "approvals_signed": True,
        "approvals_error": approvals_error,
    }
