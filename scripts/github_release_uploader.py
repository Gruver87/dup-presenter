"""GitHub Release media uploader for DUP Presenter.

Solves GitHub's 100 MB git file-size limit by attaching rendered MP4s (up to 2 GB),
subtitles (.srt/.vtt), thumbnail (.png), and publish pack files to a GitHub Release
and printing copy-paste Markdown links for README.

Uses the authenticated `gh` CLI (never reads or prints tokens).

Usage:
    python scripts/github_release_uploader.py --mp4 out/radar-pro.mp4 --repo Gruver87/dup-presenter --tag media-radar-pro --dry-run
    python scripts/github_release_uploader.py --mp4 out/radar-pro.mp4 --repo Gruver87/dup-presenter --tag media-radar-pro
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GITHUB_RELEASE_ASSET_LIMIT_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB


def _run_gh(args: list[str]) -> subprocess.CompletedProcess:
    gh = shutil.which("gh")
    if not gh:
        raise RuntimeError("GitHub CLI (`gh`) not found in PATH")
    return subprocess.run([gh, *args], capture_output=True, text=True, encoding="utf-8", errors="replace")


def _detect_repo() -> str:
    res = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if res.returncode != 0:
        return ""
    url = res.stdout.strip()
    if "github.com" not in url:
        return ""
    slug = url.split("github.com")[-1].lstrip(":/").removesuffix(".git")
    return slug


def collect_companion_assets(mp4_path: Path) -> list[Path]:
    """Return MP4 plus existing companion artifacts (.srt, .vtt, _thumb.png, _chapters.txt)."""
    stem = mp4_path.stem
    parent = mp4_path.parent
    candidates = [
        mp4_path,
        parent / f"{stem}_thumb.png",
        parent / f"{stem}.srt",
        parent / f"{stem}.vtt",
        parent / f"{stem}_chapters.txt",
        parent / f"{stem}_metadata.json",
    ]
    return [p for p in candidates if p.is_file()]


def upload_to_release(
    mp4_path: Path,
    repo: str,
    tag: str,
    title: str = "",
    notes: str = "",
    include_companions: bool = True,
    dry_run: bool = False,
) -> dict:
    """Create/update a GitHub Release and upload the MP4 + companion files."""
    if not mp4_path.is_file():
        return {"ok": False, "error": f"MP4 not found: {mp4_path}"}
    if not repo or "/" not in repo:
        return {"ok": False, "error": f"Invalid GitHub repo {repo!r}; expected owner/name"}
    if not tag.strip():
        return {"ok": False, "error": "Release tag must be non-empty"}

    size = mp4_path.stat().st_size
    if size <= 0 or size > GITHUB_RELEASE_ASSET_LIMIT_BYTES:
        return {"ok": False, "error": f"MP4 size {size} bytes out of GitHub Release bounds (1B..2GiB)"}

    auth = _run_gh(["auth", "status"])
    if auth.returncode != 0:
        return {"ok": False, "error": "gh CLI is not authenticated (run `gh auth login`)"}

    assets = collect_companion_assets(mp4_path) if include_companions else [mp4_path]
    release_title = title or f"Media release: {mp4_path.stem}"
    release_notes = notes or f"Rendered video package for `{mp4_path.stem}` ({size / 1_048_576:.2f} MB)."

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "repo": repo,
            "tag": tag,
            "title": release_title,
            "assets": [{"file": p.name, "bytes": p.stat().st_size} for p in assets],
            "expected_mp4_url": f"https://github.com/{repo}/releases/download/{tag}/{mp4_path.name}",
        }

    # Check if release tag already exists
    view = _run_gh(["release", "view", tag, "--repo", repo])
    if view.returncode != 0:
        cr = _run_gh([
            "release", "create", tag,
            "--repo", repo,
            "--title", release_title,
            "--notes", release_notes,
            *[str(p) for p in assets],
        ])
        if cr.returncode != 0:
            return {"ok": False, "error": f"gh release create failed: {cr.stderr[:500]}"}
        action = "created"
    else:
        up = _run_gh([
            "release", "upload", tag,
            "--repo", repo,
            "--clobber",
            *[str(p) for p in assets],
        ])
        if up.returncode != 0:
            return {"ok": False, "error": f"gh release upload failed: {up.stderr[:500]}"}
        action = "updated"

    mp4_url = f"https://github.com/{repo}/releases/download/{tag}/{mp4_path.name}"
    thumb = mp4_path.parent / f"{mp4_path.stem}_thumb.png"
    thumb_url = f"https://github.com/{repo}/releases/download/{tag}/{thumb.name}" if thumb.is_file() else ""
    md_snippet = f"[![Watch video]({thumb_url})]({mp4_url})" if thumb_url else f"[Watch video ({mp4_path.name})]({mp4_url})"

    return {
        "ok": True,
        "dry_run": False,
        "action": action,
        "repo": repo,
        "tag": tag,
        "release_url": f"https://github.com/{repo}/releases/tag/{tag}",
        "mp4_url": mp4_url,
        "readme_markdown": md_snippet,
        "assets": [p.name for p in assets],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload DUP Presenter MP4 package to a GitHub Release")
    parser.add_argument("--mp4", required=True, help="Path to MP4 file")
    parser.add_argument("--repo", default="", help="GitHub owner/repo (defaults to origin remote)")
    parser.add_argument("--tag", default="", help="Release tag (defaults to media-<stem>)")
    parser.add_argument("--title", default="", help="Release title")
    parser.add_argument("--notes", default="", help="Release notes")
    parser.add_argument("--mp4-only", action="store_true", help="Upload only the MP4 without subtitles/thumbnail")
    parser.add_argument("--dry-run", action="store_true", help="Validate auth & assets without uploading")
    args = parser.parse_args()

    mp4 = Path(args.mp4)
    if not mp4.is_absolute():
        mp4 = ROOT / mp4
    repo = args.repo or _detect_repo()
    tag = args.tag or f"media-{mp4.stem}"

    res = upload_to_release(
        mp4_path=mp4,
        repo=repo,
        tag=tag,
        title=args.title,
        notes=args.notes,
        include_companions=not args.mp4_only,
        dry_run=args.dry_run,
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
