"""Video-level QA gates in media_qa: black-in-the-middle must fail, opening fade-in must pass."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import media_qa  # noqa: E402


def _ffmpeg_or_none() -> Path | None:
    try:
        return media_qa._find_video_qa_ffmpeg()
    except media_qa.MediaQAError:
        return None


def _make_clip(ffmpeg: Path, out: Path, segments: list[tuple[str, float]]) -> None:
    """Build a 30 fps 320x180 clip from (color, seconds) segments via concat of lavfi color sources."""
    inputs: list[str] = []
    labels: list[str] = []
    for i, (color, sec) in enumerate(segments):
        inputs += ["-f", "lavfi", "-t", str(sec), "-i", f"color=c={color}:s=320x180:r=30"]
        labels.append(f"[{i}:v]")
    fc = "".join(labels) + f"concat=n={len(segments)}:v=1:a=0[v]"
    cmd = [str(ffmpeg), "-y", "-hide_banner", "-loglevel", "error", *inputs,
           "-filter_complex", fc, "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)]
    subprocess.run(cmd, check=True, capture_output=True)


@unittest.skipIf(_ffmpeg_or_none() is None, "no ffmpeg with blackdetect/freezedetect available")
class VideoQAGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ffmpeg = _ffmpeg_or_none()
        cls.tmp = Path(tempfile.mkdtemp(prefix="media_qa_video_"))

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _clip(self, name: str, segments: list[tuple[str, float]]) -> Path:
        out = self.tmp / f"{name}.mp4"
        _make_clip(self.ffmpeg, out, segments)
        return out

    def test_black_in_middle_is_a_defect(self) -> None:
        clip = self._clip("black_mid", [("white", 2.0), ("black", 2.0), ("white", 2.0)])
        qa = media_qa._measure_video_qa(clip, 6.0)
        self.assertTrue(qa["black_defects"], f"expected a mid-film black defect, got {qa}")
        self.assertGreater(max(b["dur"] for b in qa["black_defects"]), media_qa.BLACK_MAX_SEC)

    def test_clean_clip_has_no_black_defects(self) -> None:
        clip = self._clip("clean", [("white", 3.0), ("gray", 3.0)])
        qa = media_qa._measure_video_qa(clip, 6.0)
        self.assertEqual(qa["black_defects"], [])

    def test_opening_fade_in_is_allowed(self) -> None:
        clip = self._clip("fade_in", [("black", 0.5), ("white", 3.0)])
        qa = media_qa._measure_video_qa(clip, 3.5)
        self.assertEqual(qa["black_defects"], [], f"opening black should be a legitimate fade-in: {qa}")


class VideoQAFfmpegSelectionTests(unittest.TestCase):
    def test_fail_closed_when_no_candidate_has_filters(self) -> None:
        # Point the only candidate at a file that is not ffmpeg-with-filters: must raise, not pass.
        from unittest import mock

        bogus = Path(tempfile.gettempdir()) / "definitely_not_ffmpeg_for_tests.exe"
        with mock.patch.object(media_qa, "find_ffmpeg", return_value=bogus), \
                mock.patch.dict(sys.modules, {"imageio_ffmpeg": None}):
            with self.assertRaises(media_qa.MediaQAError):
                media_qa._find_video_qa_ffmpeg()


if __name__ == "__main__":
    unittest.main()
