"""Smoke test of the publish gate with real ffmpeg, no TTS, no Remotion and no network.

Chain checked on a 4-second synthetic MP4:
1. Media QA (real ffmpeg, real blackdetect / freezedetect) passes on the file.
2. The QA report is written next to the file and binds to its SHA-256 and byte size.
3. The TikTok gate accepts the exact file (dry run: no token, no upload).
4. A one-byte change to the same file is refused (sha256 mismatch).
5. A size change is refused (bytes mismatch).
6. The publish pack writes the LinkedIn copy with its measured lengths.

Usage:
    python scripts/smoke_publish_gate.py

Exit 0 only when every step behaves as specified. Any missing tool is a failure, not a skip.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import media_qa as mq  # noqa: E402
import publish_pack as pp  # noqa: E402
import tiktok_uploader as tu  # noqa: E402


def _make_mp4(ffmpeg: str, dest: Path) -> None:
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
        "-t", "4", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
        str(dest),
    ]
    subprocess.run(cmd, check=True, timeout=120)


def _step(name: str, ok: bool, detail: str, results: list[tuple[str, bool, str]]) -> None:
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def run() -> int:
    results: list[tuple[str, bool, str]] = []
    # Must be the same ffmpeg media QA uses (blackdetect + freezedetect). The Remotion compositor build lacks
    # those filters and lavfi sources, so it is not used here.
    try:
        ffmpeg = str(mq._find_video_qa_ffmpeg())
    except mq.MediaQAError as exc:
        _step("ffmpeg with QA filters available", False, str(exc), results)
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        mp4 = work / "smoke.mp4"
        _make_mp4(ffmpeg, mp4)

        qa = mq.run_media_qa(mp4, expect_loudnorm=False)
        _step("media QA passes", bool(qa["ok"]), f"hard_fails={qa['hard_fails']} duration={qa['duration_sec']}s", results)

        qa_path = mq.qa_report_path(mp4)
        qa_path.write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")
        err = mq.qa_binding_error(mp4)
        _step("QA report binds to the file", err is None, err or f"sha256 {qa['sha256'][:16]}...", results)

        gate = tu.tiktok_publish(mp4, dry_run=True)
        _step("TikTok gate accepts the exact file", bool(gate.get("ok")) and not gate.get("gate"),
              gate.get("error") or "dry run OK", results)

        raw = bytearray(mp4.read_bytes())
        raw[len(raw) // 2] ^= 0xFF
        mp4.write_bytes(bytes(raw))
        err = mq.qa_binding_error(mp4)
        _step("one changed byte is refused", err is not None and "sha256 mismatch" in err, err or "accepted", results)

        mp4.write_bytes(bytes(raw) + b"\x00")
        err = mq.qa_binding_error(mp4)
        _step("size change is refused", err is not None and "describes" in err, err or "accepted", results)

        blocked = tu.tiktok_publish(mp4, dry_run=True)
        _step("TikTok gate refuses the changed file", blocked.get("gate") == "media_qa" and not blocked.get("ok"),
              blocked.get("error", "not refused"), results)

        resolved = {
            "slug": "smoke",
            "brand": "DUP LABS",
            "lang": "en",
            "slides": [{"id": "u0", "title": "Smoke headline", "duration_sec": 4.0, "start_sec": 0.0}],
        }
        paths = pp.build_publish_pack(resolved, mp4_path=mp4, qa_report=qa, out_dir=work)
        text = paths["linkedin"].read_text(encoding="utf-8")
        _step("LinkedIn copy written with lengths", "## First comment" in text and "OVER LIMIT" not in text,
              paths["linkedin"].name, results)

    failed = [name for name, ok, _ in results if not ok]
    print(f"RESULT: {'PASS' if not failed else 'FAIL'} ({len(results) - len(failed)}/{len(results)} steps)")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(run())
