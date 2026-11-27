"""Fail-closed validation tests for the `cinema_clip` full-screen slide type."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_deck  # noqa: E402
from build_deck import DeckValidationError, validate_deck  # noqa: E402


def _deck(slide: dict) -> dict:
    return {
        "slug": "cinema-test",
        "lang": "en",
        "theme": "quantum_ledger",
        "aspect": "16:9",
        "brand": "DUP LABS",
        "background": {"enabled": False},
        "voice": {"engine": "kokoro_v1", "lang": "en", "speaker": "am_michael"},
        "slides": [slide],
    }


def _cinema_slide(**overrides) -> dict:
    slide = {
        "id": "c1",
        "tag": "01",
        "type": "cinema_clip",
        "title": "Big Bang",
        "voice_text": "The universe began in a single point of light.",
        "cinema": {"src": "cinema/test_clip.mp4", "badge": "13.8 BILLION YEARS AGO", "loop": True},
    }
    slide.update(overrides)
    return slide


class CinemaClipValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.public = Path(self._tmp.name)
        (self.public / "cinema").mkdir()
        (self.public / "cinema" / "test_clip.mp4").write_bytes(b"not-a-real-mp4-but-exists")
        (self.public / "cinema" / "clip2.mp4").write_bytes(b"clip2")
        (self.public / "cinema" / "still.png").write_bytes(b"png-bytes")
        (self.public / "sfx").mkdir()
        (self.public / "sfx" / "boom.wav").write_bytes(b"wav-bytes")
        self._patches = [
            mock.patch.object(build_deck, "PUBLIC_DIR", self.public),
            mock.patch.object(build_deck, "_media_duration_sec", return_value=12.04),
            mock.patch.object(build_deck, "_media_has_audio", return_value=True),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self) -> None:
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    def test_type_is_registered_as_allowed(self) -> None:
        self.assertIn("cinema_clip", build_deck.ALLOWED_TYPES)

    def test_valid_src_passes_and_records_probed_duration(self) -> None:
        deck = _deck(_cinema_slide())
        validate_deck(deck)
        # Validation is pure (item 4): annotations come from prepare_deck, on a copy.
        self.assertNotIn("clip_duration_sec", deck["slides"][0]["cinema"])
        deck = build_deck.prepare_deck(deck)
        self.assertEqual(deck["slides"][0]["cinema"]["clip_duration_sec"], 12.04)

    def test_background_query_without_src_is_accepted(self) -> None:
        slide = _cinema_slide(background_query="cosmos stars")
        slide["cinema"] = {"badge": "NO SRC"}
        validate_deck(_deck(slide))

    def test_missing_cinema_object_fails(self) -> None:
        slide = _cinema_slide()
        del slide["cinema"]
        with self.assertRaisesRegex(DeckValidationError, "requires a cinema object"):
            validate_deck(_deck(slide))

    def test_neither_src_nor_background_query_fails(self) -> None:
        slide = _cinema_slide()
        slide["cinema"] = {"badge": "EMPTY"}
        with self.assertRaisesRegex(DeckValidationError, "requires cinema.src or background_query"):
            validate_deck(_deck(slide))

    def test_path_traversal_is_rejected(self) -> None:
        slide = _cinema_slide()
        slide["cinema"]["src"] = "../secrets/key.mp4"
        with self.assertRaisesRegex(DeckValidationError, "safe relative path"):
            validate_deck(_deck(slide))

    def test_absolute_path_is_rejected(self) -> None:
        for bad in ("/etc/passwd.mp4", "\\Windows\\x.mp4"):
            with self.subTest(src=bad):
                slide = _cinema_slide()
                slide["cinema"]["src"] = bad
                with self.assertRaisesRegex(DeckValidationError, "safe relative path"):
                    validate_deck(_deck(slide))

    def test_missing_file_fails_closed(self) -> None:
        slide = _cinema_slide()
        slide["cinema"]["src"] = "cinema/does_not_exist.mp4"
        with self.assertRaisesRegex(DeckValidationError, "cinema.src file not found"):
            validate_deck(_deck(slide))

    def test_multi_shot_video_and_image_passes_and_infers_kinds(self) -> None:
        slide = _cinema_slide()
        slide["cinema"] = {
            "badge": "MULTI SHOT",
            "crossfade_frames": 15,
            "grade": "cinema_warm",
            "letterbox": True,
            "shots": [
                {
                    "src": "cinema/test_clip.mp4",
                    "duration_sec": 6.0,
                    "start_sec": 1.0,
                    "end_sec": 9.0,
                    "playback_rate": 0.75,
                    "audio_volume": 0.35,
                    "zoom": 1.08,
                },
                {
                    "src": "cinema/still.png",
                    "duration_sec": 5.0,
                    "zoom": 1.14,
                    "pan_x": -30,
                    "pan_y": 12,
                },
                {"src": "cinema/clip2.mp4"},
            ],
        }
        deck = build_deck.prepare_deck(_deck(slide))
        shots = deck["slides"][0]["cinema"]["shots"]
        self.assertEqual([s["kind"] for s in shots], ["video", "image", "video"])
        self.assertEqual(shots[0]["clip_duration_sec"], 12.04)
        self.assertNotIn("clip_duration_sec", shots[1])
        self.assertEqual(shots[2]["clip_duration_sec"], 12.04)

    def test_both_src_and_shots_is_rejected(self) -> None:
        slide = _cinema_slide()
        slide["cinema"]["shots"] = [{"src": "cinema/clip2.mp4"}]
        with self.assertRaisesRegex(DeckValidationError, "cannot set both"):
            validate_deck(_deck(slide))

    def test_trim_and_rate_bounds_fail_closed(self) -> None:
        cases = [
            ({"start_sec": 15.0}, "start_sec"),
            ({"start_sec": 5.0, "end_sec": 4.0}, "end_sec"),
            ({"start_sec": 1.0, "end_sec": 20.0}, "exceeds clip duration"),
            ({"playback_rate": 0.1}, "playback_rate"),
            ({"playback_rate": 3.0}, "playback_rate"),
            ({"zoom": 2.0}, "zoom"),
        ]
        for extra, err_re in cases:
            with self.subTest(extra=extra):
                slide = _cinema_slide()
                slide["cinema"].update(extra)
                with self.assertRaisesRegex(DeckValidationError, err_re):
                    validate_deck(_deck(slide))

    def test_image_shot_rejects_video_only_fields(self) -> None:
        for bad in ({"start_sec": 1.0}, {"playback_rate": 0.8}, {"audio_volume": 0.2}):
            with self.subTest(bad=bad):
                slide = _cinema_slide()
                slide["cinema"] = {"shots": [{"src": "cinema/still.png", **bad}]}
                with self.assertRaises(DeckValidationError):
                    validate_deck(_deck(slide))

    def test_audio_volume_on_silent_clip_fails_closed(self) -> None:
        slide = _cinema_slide()
        slide["cinema"]["audio_volume"] = 0.4
        with mock.patch.object(build_deck, "_media_has_audio", return_value=False):
            with self.assertRaisesRegex(DeckValidationError, "no audio stream"):
                validate_deck(_deck(slide))

    def test_grade_crossfade_letterbox_validation(self) -> None:
        for bad, err_re in (
            ({"grade": "sepia_fake"}, "cinema.grade"),
            ({"crossfade_frames": 45}, "crossfade_frames"),
            ({"crossfade_frames": -1}, "crossfade_frames"),
            ({"letterbox": "yes"}, "letterbox"),
        ):
            with self.subTest(bad=bad):
                slide = _cinema_slide()
                slide["cinema"].update(bad)
                with self.assertRaisesRegex(DeckValidationError, err_re):
                    validate_deck(_deck(slide))

    def test_slide_sfx_cues_valid_and_fail_closed(self) -> None:
        slide = _cinema_slide()
        slide["sfx"] = [{"src": "sfx/boom.wav", "at_sec": 0.5, "volume": 0.5, "duration_sec": 3.0}]
        validate_deck(_deck(slide))

        bad_cues = [
            ([{"src": "sfx/missing.wav", "at_sec": 0.0}], "file not found"),
            ([{"src": "../secrets/x.wav", "at_sec": 0.0}], "safe relative path"),
            ([{"src": "cinema/test_clip.mp4", "at_sec": 0.0}], "unsupported audio extension"),
            ([{"src": "sfx/boom.wav", "at_sec": -0.5}], "at_sec"),
            ([{"src": "sfx/boom.wav", "at_sec": 0.0, "volume": 1.5}], "volume"),
        ]
        for cues, err_re in bad_cues:
            with self.subTest(cues=cues):
                s = _cinema_slide()
                s["sfx"] = cues
                with self.assertRaisesRegex(DeckValidationError, err_re):
                    validate_deck(_deck(s))

    def test_draft_mode_doctor_does_not_block_on_existing_master_mp4(self) -> None:
        import deck_doctor

        with tempfile.TemporaryDirectory() as out_tmp:
            out_dir = Path(out_tmp)
            (out_dir / "cinema-test.mp4").write_bytes(b"master")
            with mock.patch.object(deck_doctor, "OUT_DIR", out_dir):
                master_rep = deck_doctor.diagnose_deck(_deck(_cinema_slide()), overwrite=False, draft=False)
                draft_rep = deck_doctor.diagnose_deck(_deck(_cinema_slide()), overwrite=False, draft=True)
            self.assertFalse(master_rep["ok"])
            self.assertTrue(draft_rep["ok"])

    def test_media_qa_expected_scale_marks_draft(self) -> None:
        import media_qa

        with tempfile.TemporaryDirectory() as tmp:
            fake_mp4 = Path(tmp) / "cinema-test_draft.mp4"
            fake_mp4.write_bytes(b"0" * 20_000)
            probe = {
                "format": {"duration": "10.0"},
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "h264",
                        "width": 960,
                        "height": 540,
                        "pix_fmt": "yuv420p",
                        "r_frame_rate": "30/1",
                        "bit_rate": "3000000",
                    },
                    {"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000"},
                ],
            }
            audio_qa = {
                "integrated_lufs": -16.0,
                "true_peak_dbtp": -1.6,
                "lra": 4.0,
                "interior_silences": [],
                "max_interior_silence_sec": 0.0,
            }
            video_qa = {
                "black_spans": [],
                "black_defects": [],
                "freeze_spans": [],
                "max_freeze_sec": 0.0,
                "duration_sec": 10.0,
            }
            resolved = {"width": 1920, "height": 1080, "total_seconds": 10.0}
            with mock.patch.object(media_qa, "_probe_streams", return_value=probe), mock.patch.object(
                media_qa, "_measure_audio_qa", return_value=audio_qa
            ), mock.patch.object(media_qa, "_measure_video_qa", return_value=video_qa):
                rep = media_qa.run_media_qa(fake_mp4, resolved=resolved, expected_scale=0.5, draft=True)
            self.assertTrue(rep["ok"])
            self.assertTrue(rep["draft"])
            self.assertEqual(rep["expected_scale"], 0.5)

    def test_cli_rejects_out_of_range_crf(self) -> None:
        with mock.patch.object(sys, "argv", ["build_deck.py", "decks/studio-universal-demo-v2.json", "--crf", "99"]):
            rc = build_deck.main()
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
