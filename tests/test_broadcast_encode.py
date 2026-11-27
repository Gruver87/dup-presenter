"""Item 3: the broadcast encode pass produces the profile media_qa enforces, and copies audio untouched."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import broadcast_encode as be  # noqa: E402
import media_qa  # noqa: E402


def _probe_video_audio(path: Path) -> tuple[dict, dict]:
    streams = media_qa._probe_streams(path)["streams"]
    v = next(s for s in streams if s.get("codec_type") == "video")
    a = next(s for s in streams if s.get("codec_type") == "audio")
    return v, a


class BroadcastEncodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.ffmpeg = be._find_encoder_ffmpeg()
        except be.BroadcastEncodeError as exc:
            raise unittest.SkipTest(str(exc))
        cls.tmp = Path(tempfile.mkdtemp(prefix="bcast_"))

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _source(self, name: str) -> Path:
        out = self.tmp / f"{name}.mp4"
        # 25 fps, full-range yuvj420p, AAC audio: the kind of raw output that stuttered.
        cmd = [
            str(self.ffmpeg), "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25:duration=3",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=3",
            "-c:v", "mpeg4", "-pix_fmt", "yuvj420p", "-q:v", "2",
            "-c:a", "aac", "-b:a", "192k", str(out),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return out

    def test_output_matches_broadcast_profile_and_keeps_audio(self) -> None:
        src = self._source("raw")
        _, a_before = _probe_video_audio(src)
        res = be.broadcast_encode(src, maxrate="4M", bufsize="8M")
        v, a_after = _probe_video_audio(src)
        self.assertEqual(v["pix_fmt"], "yuv420p")
        self.assertEqual(v["r_frame_rate"], "30/1")
        self.assertEqual(v["codec_name"], "h264")
        self.assertEqual(a_after["codec_name"], a_before["codec_name"], "audio must be copied, not re-encoded")
        self.assertEqual(res["maxrate"], "4M")
        self.assertFalse((self.tmp / "raw_bcast_tmp.mp4").exists(), "temp file must not be left behind")

    def test_missing_file_fails_closed(self) -> None:
        with self.assertRaises(be.BroadcastEncodeError):
            be.broadcast_encode(self.tmp / "nope.mp4")

    def test_profile_args_are_the_documented_profile(self) -> None:
        args = be.broadcast_video_args(crf=19, maxrate="12M", bufsize="24M")
        joined = " ".join(args)
        for needle in ("libx264", "-profile:v high", "-level:v 4.1", "yuv420p", "bt709", "-g 60", "-r 30", "-maxrate 12M"):
            self.assertIn(needle, joined)


if __name__ == "__main__":
    unittest.main()
