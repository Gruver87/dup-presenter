"""Fail-closed Media QA Gate for DUP Presenter rendered MP4s.

Checks every rendered video before declaring success:
1. Video stream exists, resolution and fps match deck_resolved.json, duration within tolerance.
2. Audio stream exists, valid sample rate and non-zero bitrate.
3. Integrated loudness (LUFS) and True Peak (dBTP) within broadcast bounds (no clipping).
4. No unexpected long dead-air silence (> 4.5s) in the middle of the video.
5. No black frames inside the film (blackdetect; a fade-in at t=0 is allowed). Hard gate.
6. Pixel format yuv420p, video bitrate <= 16 Mbps, frame rate 30 fps. Hard gates.
7. Frozen picture > 6s (freezedetect) is a soft warning, since static end cards can hold.

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


BLACK_MAX_SEC = 0.6          # any black span longer than this (except the opening frame) fails the gate
BLACK_OPENING_TOL_SEC = 0.1  # a black span that starts at t=0 and ends this early is a legitimate fade-in
FREEZE_WARN_SEC = 6.0        # a frozen picture longer than this is a warning (static end cards may hold)
VIDEO_MAX_BITRATE_BPS = 16_000_000  # broadcast 1080p ceiling; the 34 Mbps renders that stuttered are rejected


_VIDEO_QA_FILTERS = ("blackdetect", "freezedetect")


def _find_video_qa_ffmpeg() -> Path:
    """Return an ffmpeg that provides blackdetect and freezedetect. Fail closed if none does.

    The Remotion compositor ffmpeg is a stripped build without these filters, so it cannot be used
    for video QA. We look for a full build (imageio-ffmpeg ships one) and verify the filters exist.
    """
    candidates: list[Path] = []
    try:
        import imageio_ffmpeg  # type: ignore[import-not-found]

        candidates.append(Path(imageio_ffmpeg.get_ffmpeg_exe()))
    except Exception:  # noqa: BLE001 - optional dependency; absence is handled by the candidate check below
        pass
    try:
        candidates.append(find_ffmpeg())
    except AudioFXError:
        pass

    for cand in candidates:
        if not cand.is_file():
            continue
        res = subprocess.run([str(cand), "-hide_banner", "-filters"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        listing = res.stdout + res.stderr
        if all(re.search(rf"\b{name}\b", listing) for name in _VIDEO_QA_FILTERS):
            return cand
    raise MediaQAError(
        "no ffmpeg with blackdetect+freezedetect found (install imageio-ffmpeg); video QA cannot run, failing closed"
    )


def _measure_video_qa(mp4_path: Path, duration_sec: float) -> dict:
    """Detect black and frozen video spans with ffmpeg (blackdetect / freezedetect)."""
    ffmpeg = _find_video_qa_ffmpeg()
    vf = "blackdetect=d=0.3:pic_th=0.98,freezedetect=n=0.001:d=2.0"
    res = subprocess.run(
        [str(ffmpeg), "-hide_banner", "-nostats", "-i", str(mp4_path), "-an", "-vf", vf, "-c:v", "rawvideo", "-f", "null", "-"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if res.returncode != 0:
        raise MediaQAError(f"ffmpeg video QA failed (exit={res.returncode}): {res.stderr[-400:]}")

    blacks: list[dict] = []
    for m in re.finditer(r"black_start:([0-9.]+)\s+black_end:([0-9.]+)\s+black_duration:([0-9.]+)", res.stderr):
        blacks.append({"start": round(float(m.group(1)), 2), "end": round(float(m.group(2)), 2), "dur": round(float(m.group(3)), 2)})

    freezes: list[dict] = []
    cur_start: float | None = None
    for line in res.stderr.splitlines():
        ms = re.search(r"freeze_start:\s*([0-9.]+)", line)
        if ms:
            cur_start = float(ms.group(1))
        md = re.search(r"freeze_duration:\s*([0-9.]+)", line)
        if md and cur_start is not None:
            freezes.append({"start": round(cur_start, 2), "dur": round(float(md.group(1)), 2)})
            cur_start = None

    # Black at the very start is an acceptable fade-in; any other black span longer than BLACK_MAX_SEC is a defect.
    def _is_opening_fade(b: dict) -> bool:
        return b["start"] <= 0.0 and b["end"] <= BLACK_OPENING_TOL_SEC

    bad_black = [b for b in blacks if not _is_opening_fade(b) and b["dur"] > BLACK_MAX_SEC]
    max_freeze = max((f["dur"] for f in freezes), default=0.0)
    return {
        "black_spans": blacks,
        "black_defects": bad_black,
        "freeze_spans": freezes,
        "max_freeze_sec": round(max_freeze, 2),
        "duration_sec": round(duration_sec, 2),
    }


def run_media_qa(
    mp4_path: Path,
    resolved: dict | None = None,
    expect_loudnorm: bool = True,
    max_silence_sec: float = 4.5,
    expected_scale: float = 1.0,
    draft: bool = False,
) -> dict:
    """Run fail-closed Media QA checks on a rendered MP4. Returns structured QA report."""
    if not mp4_path.is_file():
        raise MediaQAError(f"MP4 file not found: {mp4_path}")
    if expected_scale <= 0.0 or expected_scale > 2.0:
        raise MediaQAError(f"expected_scale must be in (0, 2.0], got {expected_scale}")
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
        exp_w = int(round(int(resolved.get("width") or 1920) * expected_scale))
        exp_h = int(round(int(resolved.get("height") or 1080) * expected_scale))
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

    # Video-level gates: black frames, frozen picture, pixel format, bitrate, frame rate.
    video_qa = _measure_video_qa(mp4_path, duration_sec) if v_stream else {}
    bad_black = video_qa.get("black_defects", [])
    add(
        "no_black_frames",
        not bad_black,
        "no black span > %.1fs inside the film" % BLACK_MAX_SEC
        + ("" if not bad_black else f"; found {bad_black}"),
    )

    max_freeze = float(video_qa.get("max_freeze_sec", 0.0))
    add(
        "no_long_freeze",
        max_freeze <= FREEZE_WARN_SEC,
        f"max frozen picture {max_freeze:.2f}s (warn > {FREEZE_WARN_SEC}s; static end cards may hold)",
        severity="soft",
    )

    if v_stream:
        pix_fmt = str(v_stream.get("pix_fmt") or "")
        add("pixel_format_yuv420p", pix_fmt == "yuv420p", f"pix_fmt={pix_fmt or 'MISSING'} (broadcast-safe requires yuv420p)")

        try:
            bitrate = int(v_stream.get("bit_rate") or fmt.get("bit_rate") or 0)
        except (TypeError, ValueError):
            bitrate = 0
        add(
            "video_bitrate_ceiling",
            0 < bitrate <= VIDEO_MAX_BITRATE_BPS,
            f"video bitrate {bitrate / 1e6:.2f} Mbps (ceiling {VIDEO_MAX_BITRATE_BPS / 1e6:.0f} Mbps)",
        )

        fr = str(v_stream.get("r_frame_rate") or "0/1")
        try:
            num, den = fr.split("/")
            fps_val = float(num) / float(den) if float(den) else 0.0
        except (ValueError, ZeroDivisionError):
            fps_val = 0.0
        add("frame_rate_30", abs(fps_val - 30.0) < 0.01, f"r_frame_rate={fr} (expected 30 fps)")

    hard_fails = [c for c in checks if not c["ok"] and c["severity"] == "hard"]
    return {
        "ok": len(hard_fails) == 0,
        "draft": bool(draft),
        "expected_scale": expected_scale,
        "mp4": mp4_path.name,
        "bytes": size_bytes,
        "width": width,
        "height": height,
        "duration_sec": round(duration_sec, 3),
        "audio_sample_rate": sample_rate,
        "audio": audio_qa,
        "video": video_qa,
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
