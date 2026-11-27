"""GitHub Release media uploader for DUP Presenter (pipeline item 7: verified publish).

Attaches rendered MP4s (up to 2 GB), subtitles, thumbnail, chapters and a release manifest to a GitHub
Release and prints copy-paste Markdown links for the README.

Guarantees (fail-closed):
  * A manifest (`<stem>_release_manifest.json`, SHA-256 + size of every asset) is written next to the MP4
    and uploaded with it, so a viewer can check the bytes they downloaded.
  * An existing asset with the same name is NEVER overwritten silently. Replacing needs `--replace`
    (which maps to `gh release upload --clobber`). Without it the publish is refused and lists the conflicts.
  * After upload the release is queried again. Success requires every local asset to be present with the
    same size. A mismatch is reported as a failed publish, not a green one.

Uses the authenticated `gh` CLI (never reads or prints tokens).

Usage:
    python scripts/github_release_uploader.py --mp4 out/radar-pro.mp4 --repo Gruver87/dup-presenter --tag media-radar-pro --dry-run
    python scripts/github_release_uploader.py --mp4 out/radar-pro.mp4 --repo Gruver87/dup-presenter --tag media-radar-pro
    python scripts/github_release_uploader.py ... --replace   # explicit overwrite of same-named assets
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
GITHUB_RELEASE_ASSET_LIMIT_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB
MANIFEST_SUFFIX = "_release_manifest.json"


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
    """Return MP4 plus existing companion artifacts (.srt, .vtt, _thumb.png, _chapters.txt, _metadata.json)."""
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


def sha256_file(path: Path, chunk: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def build_manifest(mp4_path: Path, assets: list[Path], *, repo: str, tag: str) -> dict[str, Any]:
    """Manifest of the exact bytes being published (SHA-256 + size per asset)."""
    return {
        "schema": "dup-release-manifest/1",
        "repo": repo,
        "tag": tag,
        "mp4": mp4_path.name,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "assets": [
            {"name": p.name, "bytes": p.stat().st_size, "sha256": sha256_file(p)} for p in assets
        ],
    }


def write_manifest(mp4_path: Path, manifest: dict[str, Any]) -> Path:
    path = mp4_path.parent / f"{mp4_path.stem}{MANIFEST_SUFFIX}"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def plan_asset_conflicts(existing: list[dict[str, Any]], local: list[Path], *, replace: bool) -> list[str]:
    """Names of local assets that already exist in the release. Non-empty means refuse unless replace=True."""
    if replace:
        return []
    present = {str(a.get("name")) for a in existing}
    return sorted(p.name for p in local if p.name in present)


def verify_release_assets(existing: list[dict[str, Any]], local: list[Path]) -> dict[str, Any]:
    """Every local asset must be present on the release with the same byte size."""
    remote = {str(a.get("name")): int(a.get("size") or -1) for a in existing}
    missing = [p.name for p in local if p.name not in remote]
    size_mismatch = [
        {"name": p.name, "local": p.stat().st_size, "remote": remote[p.name]}
        for p in local
        if p.name in remote and remote[p.name] != p.stat().st_size
    ]
    return {"ok": not missing and not size_mismatch, "missing": missing, "size_mismatch": size_mismatch}


def _release_assets(repo: str, tag: str) -> list[dict[str, Any]]:
    res = _run_gh(["release", "view", tag, "--repo", repo, "--json", "assets"])
    if res.returncode != 0:
        raise RuntimeError(f"gh release view failed: {res.stderr[:300]}")
    return list((json.loads(res.stdout or "{}") or {}).get("assets") or [])


def upload_to_release(
    mp4_path: Path,
    repo: str,
    tag: str,
    title: str = "",
    notes: str = "",
    include_companions: bool = True,
    dry_run: bool = False,
    replace: bool = False,
) -> dict:
    """Create or update a GitHub Release with the MP4 package, then verify what the release now contains."""
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

    companions = collect_companion_assets(mp4_path) if include_companions else [mp4_path]
    release_title = title or f"Media release: {mp4_path.stem}"
    release_notes = notes or f"Rendered video package for `{mp4_path.stem}` ({size / 1_048_576:.2f} MB)."

    manifest = build_manifest(mp4_path, companions, repo=repo, tag=tag)
    manifest_path = write_manifest(mp4_path, manifest)
    assets = companions + [manifest_path]

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "repo": repo,
            "tag": tag,
            "title": release_title,
            "manifest": manifest_path.name,
            "assets": [{"file": p.name, "bytes": p.stat().st_size} for p in assets],
            "expected_mp4_url": f"https://github.com/{repo}/releases/download/{tag}/{mp4_path.name}",
        }

    view = _run_gh(["release", "view", tag, "--repo", repo, "--json", "assets"])
    if view.returncode != 0:
        cr = _run_gh([
            "release", "create", tag,
            "--repo", repo,
            "--title", release_title,
            "--notes", release_notes,
            "--latest=false",
            *[str(p) for p in assets],
        ])
        if cr.returncode != 0:
            return {"ok": False, "error": f"gh release create failed: {cr.stderr[:500]}"}
        action = "created"
    else:
        existing = list((json.loads(view.stdout or "{}") or {}).get("assets") or [])
        conflicts = plan_asset_conflicts(existing, assets, replace=replace)
        if conflicts:
            return {
                "ok": False,
                "error": "release already has same-named assets; re-run with --replace to overwrite them",
                "conflicts": conflicts,
            }
        up = _run_gh([
            "release", "upload", tag,
            "--repo", repo,
            *(["--clobber"] if replace else []),
            *[str(p) for p in assets],
        ])
        if up.returncode != 0:
            return {"ok": False, "error": f"gh release upload failed: {up.stderr[:500]}"}
        action = "replaced" if replace else "added"

    # Verify against the release itself, not against gh's exit code.
    try:
        remote_assets = _release_assets(repo, tag)
    except (RuntimeError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": f"publish verification could not read the release: {exc}", "action": action}
    check = verify_release_assets(remote_assets, assets)
    if not check["ok"]:
        return {"ok": False, "error": "publish verification failed: release does not match local files",
                "action": action, "verification": check}

    mp4_url = f"https://github.com/{repo}/releases/download/{tag}/{mp4_path.name}"
    thumb = mp4_path.parent / f"{mp4_path.stem}_thumb.png"
    thumb_url = f"https://github.com/{repo}/releases/download/{tag}/{thumb.name}" if thumb.is_file() else ""
    md_snippet = f"[![Watch video]({thumb_url})]({mp4_url})" if thumb_url else f"[Watch video ({mp4_path.name})]({mp4_url})"

    return {
        "ok": True,
        "verified": True,
        "dry_run": False,
        "action": action,
        "repo": repo,
        "tag": tag,
        "release_url": f"https://github.com/{repo}/releases/tag/{tag}",
        "mp4_url": mp4_url,
        "readme_markdown": md_snippet,
        "manifest": manifest_path.name,
        "assets": [p.name for p in assets],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload DUP Presenter MP4 package to a GitHub Release")
    parser.add_argument("--mp4", required=True, help="Path to MP4 file")
    parser.add_argument("--repo", default="", help="GitHub owner/repo (defaults to origin remote)")
    parser.add_argument("--tag", default="", help="Release tag (defaults to media-<stem>)")
    parser.add_argument("--title", default="", help="Release title")
    parser.add_argument("--notes", default="", help="Release notes")
    parser.add_argument("--mp4-only", action="store_true", help="Upload only the MP4 (plus manifest) without companions")
    parser.add_argument("--replace", action="store_true",
                        help="Explicitly overwrite same-named assets already on the release (default: refuse)")
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
        replace=args.replace,
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
