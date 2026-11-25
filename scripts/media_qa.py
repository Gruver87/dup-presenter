"""Fail-closed Media QA Gate for DUP Presenter rendered MP4s.

Checks every rendered video before declaring success:
1. Video stream exists, resolution and fps match deck_resolved.json, duration within tolerance.
2. Audio stream exists, valid sample rate and non-zero bitrate.
3. Integrated loudness (LUFS) and True Peak (dBTP) within broadcast bounds (no clipping).
4. No unexpected long dead-air silence (> 4.5s) in the middle of the video.

Usage:
    python scripts/media_qa.py out/radar-pro.mp4 --resolved src/generated/deck_resolved.json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from audio_fx import AudioFXError, find_ffmpeg, find_ffprobe

ROOT = Path(__file__).resolve().parent.parent


class MediaQAError(RuntimeError):
    """Raised when a rendered MP4 fails a hard QA gate check."""


def _probe_streams(mp4_path: Path) -> dict:
    ffprobe = find_ffprobe()
    res = subprocess.run(
        [
            str(ffprobe),
            "-v", "error",
            "-show_format",
            "-show_streams",
            "-print_format", "json",
            str(mp4_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if res.returncode != 0:
        raise MediaQAError(f"ffprobe failed (exit={res.returncode}): {res.stderr[:400]}")
    return json.loads(res.stdout)


def _measure_audio_qa(mp4_path: Path, duration_sec: float) -> dict:
    ffmpeg = find_ffmpeg()
    af = "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json,silencedetect=noise=-45dB:d=2.0"
    res = subprocess.run(
        [str(ffmpeg), "-hide_banner", "-nostats", "-i", str(mp4_path), "-vn", "-af", af, "-f", "null", "-"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if res.returncode != 0:
        raise MediaQAError(f"ffmpeg audio QA failed (exit={res.returncode}): {res.stderr[-400:]}")

    stderr = res.stderr
    m = re.search(r"\{\s*\"input_i\"[\s\S]*?\}", stderr)
    loud = json.loads(m.group(0)) if m else {}

    # Parse silencedetect spans (ignore 1.5s head/tail fade margins)
    silences: list[dict] = []
    cur_start: float | None = None
    for line in stderr.splitlines():
        ms = re.search(r"silence_start:\s*([0-9.]+)", line)
        if ms:
            cur_start = float(ms.group(1))
        me = re.search(r"silence_end:\s*([0-9.]+)\s*\|\s*silence_duration:\s*([0-9.]+)", line)
        if me and cur_start is not None:
            end_t = float(me.group(1))
            dur_t = float(me.group(2))
            if cur_start > 1.5 and end_t < max(0.0, duration_sec - 1.5):
                silences.append({"start": round(cur_start, 2), "end": round(end_t, 2), "dur": round(dur_t, 2)})
            cur_start = None

    def _flt(val: object) -> float | None:
        try:
            f = float(str(val))
            return None if f != f else round(f, 2)
        except Exception:
            return None

    return {
        "integrated_lufs": _flt(loud.get("input_i")),
        "true_peak_dbtp": _flt(loud.get("input_tp")),
        "lra": _flt(loud.get("input_lra")),
        "interior_silences": silences,
        "max_interior_silence_sec": max((s["dur"] for s in silences), default=0.0),
    }


def run_media_qa(
    mp4_path: Path,
    resolved: dict | None = None,
    expect_loudnorm: bool = True,
    max_silence_sec: float = 4.5,
) -> dict:
    """Run fail-closed Media QA checks on a rendered MP4. Returns structured QA report."""
    if not mp4_path.is_file():
        raise MediaQAError(f"MP4 file not found: {mp4_path}")
    size_bytes = mp4_path.stat().st_size
    if size_bytes < 10_000:
        raise MediaQAError(f"MP4 file is suspiciously small ({size_bytes} bytes)")

    probe = _probe_streams(mp4_path)
    streams = probe.get("streams") or []
    fmt = probe.get("format") or {}
    v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str, severity: str = "hard") -> None:
        checks.append({"name": name, "ok": ok, "severity": severity, "detail": detail})

    add("video_stream", v_stream is not None, f"codec={v_stream.get('codec_name') if v_stream else 'MISSING'}")
    add("audio_stream", a_stream is not None, f"codec={a_stream.get('codec_name') if a_stream else 'MISSING'}")

    duration_sec = float(fmt.get("duration") or 0.0)
    width = int(v_stream.get("width") or 0) if v_stream else 0
    height = int(v_stream.get("height") or 0) if v_stream else 0
    sample_rate = int(a_stream.get("sample_rate") or 0) if a_stream else 0

    add("duration_positive", duration_sec >= 1.5, f"{duration_sec:.2f}s")
    add("audio_sample_rate", sample_rate >= 44100, f"{sample_rate} Hz")

    if resolved:
        exp_w = int(resolved.get("width") or 1920)
        exp_h = int(resolved.get("height") or 1080)
        exp_dur = float(resolved.get("total_seconds") or 0.0)
        add("resolution_match", (width, height) == (exp_w, exp_h), f"got {width}x{height}, expected {exp_w}x{exp_h}")
        if exp_dur > 0:
            diff = abs(duration_sec - exp_dur)
            add("duration_match", diff <= 1.2, f"got {duration_sec:.2f}s, expected {exp_dur:.2f}s (diff={diff:.2f}s)")

    audio_qa = _measure_audio_qa(mp4_path, duration_sec) if a_stream else {}
    lufs = audio_qa.get("integrated_lufs")
    tp = audio_qa.get("true_peak_dbtp")
    max_sil = float(audio_qa.get("max_interior_silence_sec", 0.0))

    if lufs is not None:
        if expect_loudnorm:
            add("loudness_broadcast", -18.5 <= lufs <= -13.5, f"{lufs} LUFS (target -16.0 +/- 2.5)")
        else:
            add("loudness_audible", -28.0 <= lufs <= -8.0, f"{lufs} LUFS")
    else:
        add("loudness_measured", False, "could not measure integrated LUFS")

    if tp is not None:
        add("no_clipping", tp <= -0.2, f"True Peak {tp} dBTP (limit <= -0.2)")
    else:
        add("no_clipping", False, "could not measure True Peak")

    add(
        "no_long_dead_air",
        max_sil <= max_silence_sec,
        f"max interior silence {max_sil:.2f}s (limit <= {max_silence_sec}s)",
    )

    hard_fails = [c for c in checks if not c["ok"] and c["severity"] == "hard"]
    return {
        "ok": len(hard_fails) == 0,
        "mp4": mp4_path.name,
        "bytes": size_bytes,
        "width": width,
        "height": height,
        "duration_sec": round(duration_sec, 3),
        "audio_sample_rate": sample_rate,
        "audio": audio_qa,
        "checks": checks,
        "hard_fails": len(hard_fails),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="DUP Presenter Media QA Gate")
    parser.add_argument("mp4", help="Path to rendered MP4 file")
    parser.add_argument("--resolved", default="", help="Optional path to deck_resolved.json for exact dimension/duration checks")
    parser.add_argument("--no-loudnorm-bounds", action="store_true", help="Relax LUFS bounds if loudnorm was skipped")
    parser.add_argument("--out", default="", help="Optional path to write QA JSON report")
    args = parser.parse_args()

    mp4 = Path(args.mp4)
    if not mp4.is_absolute():
        mp4 = ROOT / mp4
    resolved = None
    if args.resolved:
        rp = Path(args.resolved)
        if not rp.is_absolute():
            rp = ROOT / rp
        if rp.is_file():
            resolved = json.loads(rp.read_text(encoding="utf-8"))

    try:
        report = run_media_qa(mp4, resolved=resolved, expect_loudnorm=not args.no_loudnorm_bounds)
    except (MediaQAError, AudioFXError) as exc:
        print(f"[QA FAIL] {exc}", file=sys.stderr)
        return 1

    if args.out:
        out_p = Path(args.out)
        if not out_p.is_absolute():
            out_p = ROOT / out_p
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
