"""DUP Presenter — fail-closed Git repository fetcher (HTTPS shallow clone).

Accepts either:
  - https://github.com/owner/repo[.git] (or any public https://*.git host)
  - shorthand owner/repo (expanded to https://github.com/owner/repo.git)

Security & fail-closed rules:
  - HTTPS only (refuses file://, ssh://, git://, local paths, flag-like strings starting with '-');
  - GIT_TERMINAL_PROMPT=0 so missing/private repos fail immediately instead of hanging;
  - shallow clone (--depth 1 --single-branch --no-tags) into work/_repos/<slug>;
  - never executes git hooks (--config core.hooksPath=NUL).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

SHORTHAND_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
HTTPS_URL_RE = re.compile(r"^https://[A-Za-z0-9.-]+/[A-Za-z0-9_./-]+$")


class RepoFetchError(RuntimeError):
    """Raised when a remote repository URL is invalid or cannot be cloned."""


def looks_like_remote(source: str) -> bool:
    s = (source or "").strip()
    return s.startswith("https://") or bool(SHORTHAND_RE.match(s))


def normalize_git_url(source: str) -> tuple[str, str]:
    """Return (https_clone_url, suggested_slug). Fails closed on unsafe URLs."""
    s = (source or "").strip().rstrip("/")
    if not s or s.startswith("-") or ".." in s:
        raise RepoFetchError("Empty or unsafe repository URL.")
    if SHORTHAND_RE.match(s):
        owner, repo = s.split("/", 1)
        repo_clean = repo[:-4] if repo.endswith(".git") else repo
        return f"https://github.com/{owner}/{repo_clean}.git", _clean_slug(repo_clean)

    # Strip /tree/<branch> or /blob/... if user pasted a GitHub browser URL
    m_gh = re.match(r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)(?:/.*)?$", s)
    if m_gh:
        owner, repo = m_gh.group(1), m_gh.group(2)
        repo_clean = repo[:-4] if repo.endswith(".git") else repo
        return f"https://github.com/{owner}/{repo_clean}.git", _clean_slug(repo_clean)

    if not HTTPS_URL_RE.match(s) or ".." in s:
        raise RepoFetchError(f"Only public https:// repository URLs or owner/repo are allowed: {source!r}")
    tail = s.rsplit("/", 1)[-1]
    repo_clean = tail[:-4] if tail.endswith(".git") else tail
    return s, _clean_slug(repo_clean)


def _clean_slug(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", name).strip("-_")
    return (slug or "repo")[:64]


def fetch_repo(source: str, work_root: Path, slug: str) -> Path:
    """Shallow-clone a public HTTPS repo into work_root/_repos/<slug> and return its path."""
    url, _ = normalize_git_url(source)
    repos_dir = work_root / "_repos"
    repos_dir.mkdir(parents=True, exist_ok=True)
    dest = repos_dir / slug

    if dest.exists():
        shutil.rmtree(dest, ignore_errors=False)

    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    cmd = [
        "git", "clone",
        "--depth", "1",
        "--single-branch",
        "--no-tags",
        "--config", "core.hooksPath=NUL" if os.name == "nt" else "core.hooksPath=/dev/null",
        "--", url, str(dest),
    ]
    print(f"[fetch] cloning {url} -> {dest}")
    res = subprocess.run(cmd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    if res.returncode != 0:
        shutil.rmtree(dest, ignore_errors=True)
        detail = (res.stderr or res.stdout or "").strip().splitlines()[-3:]
        raise RepoFetchError(f"git clone failed (exit={res.returncode}): {' | '.join(detail)}")
    return dest
