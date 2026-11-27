"""Broadcast-safe H.264 encode pass (pipeline item 3).

Remotion's raw output is yuvj420p at a high bitrate. The 34 Mbps renders of the Russian Director's Cut
stuttered on playback; the fix was a re-encode to H.264 High@4.1, yuv420p, BT.709 tags, a capped maxrate,
a fixed GOP and 30 fps with faststart. That pass used to be a manual step. It now runs inside the
pipeline after every render, before loudness normalization and Media QA.

The video stream is re-encoded; the audio stream is copied as-is (loudness is handled afterwards).
Media QA then checks the hard limits (pixel format, bitrate ceiling, frame rate), so the pass is verified
on the output, not assumed.

Fail-closed: no libx264 encoder -> BroadcastEncodeError. No silent fallback to the unencoded file.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from audio_fx import AudioFXError, find_ffmpeg

GOP_FRAMES = 60
TIMELINE_FPS = 30
DEFAULT_CRF = 19
DEFAULT_MAXRATE = "12M"  # 1080p master ceiling; media_qa VIDEO_MAX_BITRATE_BPS is 16 Mbps
DEFAULT_BUFSIZE = "24M"


class BroadcastEncodeError(RuntimeError):
    """Raised when the broadcast encode cannot run or produces no output."""


def broadcast_video_args(*, crf: int, maxrate: str, bufsize: str) -> list[str]:
    """ffmpeg video arguments for the broadcast profile (single source of truth)."""
    return [
        "-c:v", "libx264", "-preset", "medium",
        "-profile:v", "high", "-level:v", "4.1",
        "-pix_fmt", "yuv420p",
        "-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
        "-crf", str(crf), "-maxrate", maxrate, "-bufsize", bufsize,
        "-g", str(GOP_FRAMES), "-r", str(TIMELINE_FPS),
    ]


def _find_encoder_ffmpeg() -> Path:
    """Return an ffmpeg that has libx264. Prefers the imageio-ffmpeg full build, then the Remotion one."""
    candidates: list[Path] = []
    try:
        import imageio_ffmpeg  # type: ignore[import-not-found]

        candidates.append(Path(imageio_ffmpeg.get_ffmpeg_exe()))
    except Exception:  # noqa: BLE001 - optional dependency; the candidate check below decides
        pass
    try:
        candidates.append(find_ffmpeg())
    except AudioFXError:
        pass
    for cand in candidates:
        if not cand.is_file():
            continue
        res = subprocess.run([str(cand), "-hide_banner", "-encoders"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
        if "libx264" in (res.stdout + res.stderr):
            return cand
    raise BroadcastEncodeError("no ffmpeg with libx264 found; broadcast encode cannot run (fail-closed)")


def broadcast_encode(
    mp4_path: Path,
    *,
    crf: int = DEFAULT_CRF,
    maxrate: str = DEFAULT_MAXRATE,
    bufsize: str = DEFAULT_BUFSIZE,
) -> dict:
    """Re-encode the video stream of `mp4_path` in place to the broadcast profile. Audio is copied."""
    if not mp4_path.is_file():
        raise BroadcastEncodeError(f"MP4 not found for broadcast encode: {mp4_path}")
    if not (0 <= crf <= 51):
        raise BroadcastEncodeError(f"crf must be in 0..51, got {crf}")
    ffmpeg = _find_encoder_ffmpeg()
    before = mp4_path.stat().st_size
    tmp = mp4_path.with_name(mp4_path.stem + "_bcast_tmp.mp4")
    cmd = [
        str(ffmpeg), "-y", "-hide_banner", "-loglevel", "error", "-i", str(mp4_path),
        *broadcast_video_args(crf=crf, maxrate=maxrate, bufsize=bufsize),
        "-c:a", "copy", "-movflags", "+faststart", str(tmp),
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if res.returncode != 0 or not tmp.is_file() or tmp.stat().st_size == 0:
            raise BroadcastEncodeError(f"broadcast encode failed (exit={res.returncode}): {res.stderr[-400:]}")
        os.replace(tmp, mp4_path)
    finally:
        tmp.unlink(missing_ok=True)
    after = mp4_path.stat().st_size
    return {"bytes_before": before, "bytes_after": after, "maxrate": maxrate, "crf": crf}
