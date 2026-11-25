"""DUP Presenter — fail-closed MP4 video merger (using bundled Remotion ffmpeg/ffprobe).

Merges 2 or more MP4 files from out/ into a single MP4 (with normalized resolution,
30 fps, 48 kHz AAC 320K audio), plus a thumbnail PNG and merged SRT/VTT if available.

Usage:
    python scripts/merge_videos.py --out full_demo radar dup-protocol
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "out"
SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class MergeError(RuntimeError):
    """Raised when video merging cannot be performed safely."""


def find_bin(name: str) -> str:
    on_path = shutil.which(name)
    if on_path:
        return on_path
    exe = f"{name}.exe" if sys.platform == "win32" else name
    hits = sorted((ROOT / "node_modules" / "@remotion").glob(f"*/{exe}"))
    if hits:
        return str(hits[0])
    raise MergeError(f"{name} not found on PATH or in node_modules/@remotion")


def probe_video(ffprobe: str, path: Path) -> dict:
    res = subprocess.run(
        [ffprobe, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if res.returncode != 0:
        raise MergeError(f"ffprobe failed on {path.name}: {res.stderr.strip()}")
    data = json.loads(res.stdout)
    v_stream = next((s for s in data.get("streams") or [] if s.get("codec_type") == "video"), None)
    a_stream = next((s for s in data.get("streams") or [] if s.get("codec_type") == "audio"), None)
    if not v_stream:
        raise MergeError(f"No video stream in {path.name}")
    return {
        "width": int(v_stream.get("width") or 1920),
        "height": int(v_stream.get("height") or 1080),
        "has_audio": a_stream is not None,
        "duration": float((data.get("format") or {}).get("duration") or 0.0),
    }


def _parse_srt_ts(ts: str) -> float:
    h, m, rest = ts.strip().split(":")
    s, ms = rest.replace(".", ",").split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def _fmt_ts(sec: float, sep: str) -> str:
    ms = int(round(max(0.0, sec) * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def merge_subtitles(slugs: list[str], durations: list[float], out_slug: str) -> None:
    srt_paths = [OUT_DIR / f"{s}.srt" for s in slugs]
    if not all(p.is_file() for p in srt_paths):
        return
    srt_out: list[str] = []
    vtt_out: list[str] = ["WEBVTT", ""]
    idx = 1
    offset = 0.0
    for p, dur in zip(srt_paths, durations):
        blocks = re.split(r"\r?\n\r?\n", p.read_text(encoding="utf-8").strip())
        for blk in blocks:
            lines = [ln.strip() for ln in blk.splitlines() if ln.strip()]
            if len(lines) >= 3 and "-->" in lines[1]:
                a, b = [x.strip() for x in lines[1].split("-->", 1)]
                start = offset + _parse_srt_ts(a)
                end = offset + _parse_srt_ts(b)
                text = " ".join(lines[2:])
                srt_out += [str(idx), f"{_fmt_ts(start, ',')} --> {_fmt_ts(end, ',')}", text, ""]
                vtt_out += [f"{_fmt_ts(start, '.')} --> {_fmt_ts(end, '.')}", text, ""]
                idx += 1
        offset += dur
    (OUT_DIR / f"{out_slug}.srt").write_text("\n".join(srt_out), encoding="utf-8")
    (OUT_DIR / f"{out_slug}.vtt").write_text("\n".join(vtt_out), encoding="utf-8")
    print(f"[merge] wrote merged subtitles {out_slug}.srt & {out_slug}.vtt ({idx - 1} cues)")


def merge_videos(out_slug: str, clip_slugs: list[str]) -> Path:
    if not SLUG_RE.match(out_slug):
        raise MergeError(f"Invalid output slug: {out_slug!r}")
    if len(clip_slugs) < 2:
        raise MergeError("Select at least 2 videos to merge.")

    inputs: list[Path] = []
    for s in clip_slugs:
        if not SLUG_RE.match(s):
            raise MergeError(f"Invalid clip slug: {s!r}")
        p = OUT_DIR / f"{s}.mp4"
        if not p.is_file():
            raise MergeError(f"Input video not found: {p}")
        inputs.append(p)

    ffmpeg = find_bin("ffmpeg")
    ffprobe = find_bin("ffprobe")
    infos = [probe_video(ffprobe, p) for p in inputs]
    target_w, target_h = infos[0]["width"], infos[0]["height"]
    print(f"[merge] target={target_w}x{target_h}, clips={len(inputs)}: {', '.join(clip_slugs)}")

    out_mp4 = OUT_DIR / f"{out_slug}.mp4"
    tmp_mp4 = OUT_DIR / f".{out_slug}.merging.mp4"

    cmd: list[str] = [ffmpeg, "-y", "-hide_banner", "-loglevel", "warning"]
    for p in inputs:
        cmd += ["-i", str(p)]

    filters: list[str] = []
    concat_inputs: list[str] = []
    for i, info in enumerate(infos):
        filters.append(
            f"[{i}:v]scale={target_w}:{target_h},format=yuv420p[v{i}]"
        )
        if info["has_audio"]:
            filters.append(f"[{i}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[a{i}]")
        else:
            filters.append(f"anullsrc=r=48000:cl=stereo:d={info['duration']:.3f}[a{i}]")
        concat_inputs.append(f"[v{i}][a{i}]")

    filters.append(f"{''.join(concat_inputs)}concat=n={len(inputs)}:v=1:a=1[vout][aout]")

    cmd += [
        "-filter_complex", ";".join(filters),
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "320k",
        "-movflags", "+faststart",
        str(tmp_mp4),
    ]
    print(f"[merge] running ffmpeg -> {out_mp4.name}")
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0 or not tmp_mp4.is_file():
        tmp_mp4.unlink(missing_ok=True)
        raise MergeError(f"ffmpeg failed (exit={res.returncode}): {res.stderr.strip()}")

    tmp_mp4.replace(out_mp4)
    thumb = OUT_DIR / f"{out_slug}_thumb.png"
    subprocess.run(
        [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-ss", "1.5", "-i", str(out_mp4), "-frames:v", "1", str(thumb)],
        capture_output=True,
    )
    merge_subtitles(clip_slugs, [i["duration"] for i in infos], out_slug)
    size_mb = out_mp4.stat().st_size / 1_048_576
    total_s = sum(i["duration"] for i in infos)
    print(f"[OK] Merged: {out_mp4} ({size_mb:.2f} MB, ~{total_s:.1f}s)")
    return out_mp4


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge 2+ MP4 videos from out/")
    parser.add_argument("--out", required=True, help="Output slug (creates out/<slug>.mp4)")
    parser.add_argument("clips", nargs="+", help="Input slugs in order (e.g. dup-protocol radar)")
    args = parser.parse_args()
    merge_videos(args.out, args.clips)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MergeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(2)
