"""DUP Presenter - one command: project folder -> facts -> plan -> deck -> voice -> MP4.

Examples:
    python scripts/make_project_deck.py "C:\\path\\to\\dup-market-radar" --slug radar --render
    python scripts/make_project_deck.py --slug radar --feedback "больше про paper-режим" --render
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
from fetch_repo import RepoFetchError, fetch_repo, looks_like_remote  # noqa: E402


def run(args: list[str]) -> None:
    print(f"[run] {' '.join(args)}")
    res = subprocess.run(args, cwd=str(ROOT))
    if res.returncode != 0:
        raise SystemExit(f"Step failed (exit={res.returncode}): {' '.join(args)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="DUP Presenter: project (folder or GitHub URL) to presentation")
    parser.add_argument("folder", nargs="?", help="Local folder OR public GitHub/Git HTTPS URL (omit with --feedback)")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--feedback", help="Natural-language change request")
    parser.add_argument("--slides", type=int, default=None)
    parser.add_argument("--model", default="qwen2.5:14b", help="Model id (Ollama or cloud override)")
    parser.add_argument("--provider", choices=["ollama", "cloud"], default="ollama")
    parser.add_argument("--lang", choices=["ru", "en"], default="ru", help="Language of slides and voice")
    parser.add_argument("--speaker", default="", help="Silero speaker id")
    parser.add_argument("--theme", default="neon_cyber", help="Visual theme")
    parser.add_argument("--aspect", choices=["16:9", "9:16"], default="16:9")
    parser.add_argument("--voice-mode", choices=["single", "podcast"], default="single")
    parser.add_argument("--no-captions", action="store_true")
    parser.add_argument("--render", action="store_true", help="Render MP4 after building the voice")
    parser.add_argument("--draft", action="store_true", help="With --render: render only the draft preview (storyboard gate before master)")
    args = parser.parse_args()

    py = sys.executable
    work = ROOT / "work" / args.slug
    work.mkdir(parents=True, exist_ok=True)
    facts_path = work / "facts.json"

    if args.folder:
        source_path = args.folder
        if looks_like_remote(args.folder):
            try:
                source_path = str(fetch_repo(args.folder, ROOT / "work", args.slug))
            except RepoFetchError as exc:
                raise SystemExit(f"[ERROR] {exc}") from exc
        run([py, str(SCRIPTS / "analyze_project.py"), source_path, "--out", str(facts_path)])
    elif not facts_path.is_file() and not args.feedback:
        raise SystemExit("Pass a project folder or GitHub URL for the first run.")

    plan_cmd = [
        py, str(SCRIPTS / "plan_deck.py"), "--slug", args.slug, "--facts", str(facts_path),
        "--model", args.model, "--provider", args.provider, "--lang", args.lang,
        "--theme", args.theme, "--aspect", args.aspect, "--voice-mode", args.voice_mode,
    ]
    if args.speaker:
        plan_cmd += ["--speaker", args.speaker]
    if args.no_captions:
        plan_cmd.append("--no-captions")
    if args.feedback:
        plan_cmd += ["--feedback", args.feedback]
    if args.slides:
        plan_cmd += ["--slides", str(args.slides)]
    run(plan_cmd)

    build_cmd = [py, str(SCRIPTS / "build_deck.py"), str(ROOT / "decks" / f"{args.slug}.json")]
    if args.render:
        build_cmd.append("--render")
        if args.draft:
            build_cmd.append("--draft")
    run(build_cmd)
    if args.render and args.draft:
        print(f"[OK] deck {args.slug} built; draft in out\\{args.slug}_draft.mp4 (approve storyboard before master)")
    else:
        print(f"[OK] deck {args.slug} built" + (f"; MP4 in out\\{args.slug}.mp4" if args.render else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
