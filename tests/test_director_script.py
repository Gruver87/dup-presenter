"""Fail-closed tests for the Stage 2 Director Script engine (DeepSeek, no network)."""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import director_script as ds  # noqa: E402
from build_deck import validate_deck  # noqa: E402

FAKE_KEY = "TEST_PLACEHOLDER_NOT_A_KEY"

# Sized for a 12 s scene at ~2.3 words/sec (32 words / 12 s = 2.67, within 1.8..3.0).
EN_VOICE = (
    "Energy erupted from a point far smaller than an atom, and within a fraction of a second space itself "
    "began to stretch outward, carrying matter and light in every direction at once."
)
RU_VOICE = (
    "Из точки, меньше атома, вырвалась невероятная энергия, и за долю секунды само пространство начало "
    "растягиваться во все стороны, унося материю и свет в самом начале времени."
)


def _scene(**overrides) -> dict:
    base = {
        "voice_text": EN_VOICE,
        "target_sec": 12,
        "visual_type": "cinema_clip",
        "headline": "First Instant",
        "caption": "13.8 billion years ago",
        "visual_prompt_en": "Slow push into a blinding point of light in deep black space",
        "stock_queries_en": ["cosmic explosion"],
    }
    base.update(overrides)
    return base


def _act1_payload(scenes: list[dict], title: str = "Big Bang") -> dict:
    return {
        "title": title,
        "style_bible": {
            "palette": "deep blues, gold highlights",
            "lens": "35mm anamorphic",
            "lighting": "volumetric, high contrast",
            "mood": "awe",
        },
        "scenes": scenes,
    }


def _one_minute_scenes() -> list[dict]:
    return [_scene() for _ in range(5)]  # 5 x 12 s = 60 s


class _FakeLLM:
    """Records calls and returns scripted act payloads in order."""

    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = list(payloads)
        self.calls = 0

    def __call__(self, messages: list[dict[str, str]]) -> dict:
        self.calls += 1
        if len(self.payloads) > 1:
            return self.payloads.pop(0)
        return self.payloads[0]  # keep returning the last scripted answer (e.g. a persistently bad one)


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        return False


def _chat_body(content: str, finish_reason: str = "stop") -> bytes:
    return json.dumps(
        {"choices": [{"finish_reason": finish_reason, "message": {"content": content}}]}
    ).encode("utf-8")


class GenerateScriptTests(unittest.TestCase):
    def test_one_minute_script_converts_to_valid_deck(self) -> None:
        llm = _FakeLLM([_act1_payload(_one_minute_scenes())])
        script = ds.generate_script("Big Bang", 1, "en", llm=llm)
        self.assertEqual(llm.calls, 1)
        self.assertEqual(len(script["scenes"]), 5)
        self.assertEqual({s["visual_type"] for s in script["scenes"]}, {"cinema_clip"})

        deck = ds.script_to_deck(script)
        validate_deck(deck, check_assets=False)
        self.assertEqual(deck["voice"]["engine"], "kokoro_v1")
        self.assertEqual(deck["slides"][0]["background_query"], "cosmic explosion")
        self.assertEqual(deck["slides"][0]["id"], "a1s01")

    def test_mixed_visual_types_convert_to_valid_deck(self) -> None:
        scenes = [
            _scene(target_sec=12, visual_type="cinema_clip"),
            _scene(target_sec=12, visual_type="stat_burst", headline="13.8 B", caption="years ago", voice_text=EN_VOICE),
            _scene(target_sec=12, visual_type="broll_cinematic", caption="Expansion begins"),
            _scene(
                target_sec=12,
                visual_type="kpi",
                kpis=[{"value": "3 K", "label": "temperature"}, {"value": "1 ms", "label": "age"}],
            ),
            _scene(target_sec=12, visual_type="cinema_clip"),
        ]  # 5 x 12 s = 60 s
        script = ds.generate_script("Big Bang", 1, "en", llm=_FakeLLM([_act1_payload(scenes)]))
        deck = ds.script_to_deck(script)
        validate_deck(deck, check_assets=False)
        types = [s["type"] for s in deck["slides"]]
        self.assertEqual(types, ["cinema_clip", "stat_burst", "broll_cinematic", "kpi", "cinema_clip"])
        self.assertEqual(script["fact_status"], "unverified_llm_output")

    def test_quote_visual_type_is_refused_for_llm_output(self) -> None:
        scenes = [_scene(visual_type="quote", caption="Someone famous said this.") for _ in range(5)]
        with self.assertRaisesRegex(ds.DirectorScriptError, "visual_type"):
            ds.generate_script("Big Bang", 1, "en", llm=_FakeLLM([_act1_payload(scenes)]))

    def test_prompt_forbids_quotations_and_unverified_numbers(self) -> None:
        captured: list[list[dict[str, str]]] = []

        def llm(messages: list[dict[str, str]]) -> dict:
            captured.append(messages)
            return _act1_payload(_one_minute_scenes())

        ds.generate_script("Big Bang", 1, "en", llm=llm)
        system = captured[0][0]["content"]
        self.assertIn("Never write direct quotations", system)
        self.assertIn("certain of", system)

    def test_russian_script_uses_russian_voice_and_engine(self) -> None:
        scenes = [_scene(voice_text=RU_VOICE) for _ in range(5)]
        script = ds.generate_script("Большой взрыв", 1, "ru", llm=_FakeLLM([_act1_payload(scenes)]))
        deck = ds.script_to_deck(script)
        validate_deck(deck, check_assets=False)
        self.assertEqual(deck["voice"]["engine"], "edge_tts")
        self.assertEqual(deck["voice"]["speaker"], "dmitry")

    def test_multi_act_three_minutes_calls_llm_twice_and_keeps_style_bible(self) -> None:
        act1 = _act1_payload([_scene(target_sec=15) for _ in range(6)])  # 90 s
        act2 = {"scenes": [_scene(target_sec=15) for _ in range(6)]}  # 90 s, no style_bible / title
        llm = _FakeLLM([act1, act2])
        script = ds.generate_script("Big Bang", 3, "en", llm=llm)
        self.assertEqual(llm.calls, 2)
        self.assertEqual({s["act"] for s in script["scenes"]}, {1, 2})
        self.assertEqual([s["id"] for s in script["scenes"]][-1], "a2s06")
        deck = ds.script_to_deck(script)
        validate_deck(deck, check_assets=False)
        self.assertEqual([s["tag"] for s in deck["slides"]][-1], "02")

    def test_dead_air_scene_is_refused(self) -> None:
        scenes = [_scene(voice_text="Short line here.") for _ in range(5)]  # 3 words in 12 s = dead air
        with self.assertRaisesRegex(ds.DirectorScriptError, "dead air"):
            ds.generate_script("Big Bang", 1, "en", llm=_FakeLLM([_act1_payload(scenes)]))

    def test_slides_carry_planned_minimum_duration(self) -> None:
        script = ds.generate_script("Big Bang", 1, "en", llm=_FakeLLM([_act1_payload(_one_minute_scenes())]))
        deck = ds.script_to_deck(script)
        self.assertEqual([s["min_duration_sec"] for s in deck["slides"]], [12] * 5)
        validate_deck(deck, check_assets=False)

    def test_duration_outside_tolerance_fails_closed(self) -> None:
        voice = " ".join(["word"] * 14)  # 14 words / 6 s = 2.33 words/sec, a valid pace
        scenes = [_scene(target_sec=6, voice_text=voice) for _ in range(5)]  # 30 s for a 60 s request
        with self.assertRaisesRegex(ds.DirectorScriptError, "durations sum"):
            ds.generate_script("Big Bang", 1, "en", llm=_FakeLLM([_act1_payload(scenes)]))

    def test_too_many_words_per_second_fails_closed(self) -> None:
        long_text = " ".join(["energy"] * 60)  # 60 words in 12 s = 5 words/sec
        scenes = [_scene(voice_text=long_text) for _ in range(5)]
        with self.assertRaisesRegex(ds.DirectorScriptError, "words/sec"):
            ds.generate_script("Big Bang", 1, "en", llm=_FakeLLM([_act1_payload(scenes)]))

    def test_wrong_language_fails_closed(self) -> None:
        scenes = [_scene(voice_text=EN_VOICE) for _ in range(5)]
        with self.assertRaisesRegex(ds.DirectorScriptError, "must be Russian"):
            ds.generate_script("Большой взрыв", 1, "ru", llm=_FakeLLM([_act1_payload(scenes)]))
        scenes_ru = [_scene(voice_text=RU_VOICE) for _ in range(5)]
        with self.assertRaisesRegex(ds.DirectorScriptError, "must be English"):
            ds.generate_script("Big Bang", 1, "en", llm=_FakeLLM([_act1_payload(scenes_ru)]))

    def test_unsupported_visual_type_fails_closed(self) -> None:
        scenes = [_scene(visual_type="versus_battle") for _ in range(5)]
        with self.assertRaisesRegex(ds.DirectorScriptError, "visual_type"):
            ds.generate_script("Big Bang", 1, "en", llm=_FakeLLM([_act1_payload(scenes)]))

    def test_non_latin_or_bad_stock_query_fails_closed(self) -> None:
        scenes = [_scene(stock_queries_en=["космос"]) for _ in range(5)]
        with self.assertRaisesRegex(ds.DirectorScriptError, "invalid stock query"):
            ds.generate_script("Big Bang", 1, "en", llm=_FakeLLM([_act1_payload(scenes)]))

    def test_cinema_scene_without_stock_query_fails_closed(self) -> None:
        scenes = [_scene(stock_queries_en=[]) for _ in range(5)]
        with self.assertRaisesRegex(ds.DirectorScriptError, "needs at least one stock_queries_en"):
            ds.generate_script("Big Bang", 1, "en", llm=_FakeLLM([_act1_payload(scenes)]))

    def test_kpi_value_too_long_fails_closed(self) -> None:
        scenes = [
            _scene(visual_type="kpi", kpis=[{"value": "x" * 13, "label": "too long value"}]) for _ in range(5)
        ]
        with self.assertRaisesRegex(ds.DirectorScriptError, "value"):
            ds.generate_script("Big Bang", 1, "en", llm=_FakeLLM([_act1_payload(scenes)]))

    def test_headline_longer_than_24_chars_fails_closed(self) -> None:
        scenes = [_scene(headline="h" * 25) for _ in range(5)]
        with self.assertRaisesRegex(ds.DirectorScriptError, "headline"):
            ds.generate_script("Big Bang", 1, "en", llm=_FakeLLM([_act1_payload(scenes)]))

    def test_missing_title_in_first_act_fails_closed(self) -> None:
        payload = _act1_payload(_one_minute_scenes())
        del payload["title"]
        with self.assertRaisesRegex(ds.DirectorScriptError, "title"):
            ds.generate_script("Big Bang", 1, "en", llm=_FakeLLM([payload]))

    def test_non_object_llm_output_fails_closed(self) -> None:
        llm = _FakeLLM(["not a dict"])
        with self.assertRaisesRegex(ds.DirectorScriptError, "JSON object"):
            ds.generate_script("Big Bang", 1, "en", llm=llm)  # type: ignore[arg-type]
        self.assertEqual(llm.calls, ds.MAX_ACT_ATTEMPTS)

    def test_schema_error_is_repaired_by_feedback_retry(self) -> None:
        bad = _act1_payload([_scene(headline="h" * 25) for _ in range(5)])  # headline too long
        good = _act1_payload(_one_minute_scenes())
        captured: list[list[dict[str, str]]] = []
        responses = [bad, good]

        def llm(messages: list[dict[str, str]]) -> dict:
            captured.append(messages)
            return responses.pop(0)

        script = ds.generate_script("Big Bang", 1, "en", llm=llm)
        self.assertEqual(len(captured), 2)
        repair_user_msg = captured[1][-1]["content"]
        self.assertIn("failed validation", repair_user_msg)
        self.assertIn("headline", repair_user_msg)
        self.assertEqual(len(script["scenes"]), 5)

    def test_transport_error_is_not_retried(self) -> None:
        llm_calls = {"n": 0}

        def llm(messages: list[dict[str, str]]) -> dict:
            llm_calls["n"] += 1
            raise ds.DirectorScriptError("DeepSeek HTTP 401")

        with self.assertRaisesRegex(ds.DirectorScriptError, "HTTP 401"):
            ds.generate_script("Big Bang", 1, "en", llm=llm)
        self.assertEqual(llm_calls["n"], 1)

    def test_invalid_request_arguments_fail_closed(self) -> None:
        llm = _FakeLLM([])
        with self.assertRaises(ds.DirectorScriptError):
            ds.generate_script("", 1, "en", llm=llm)
        with self.assertRaises(ds.DirectorScriptError):
            ds.generate_script("Big Bang", 11, "en", llm=llm)
        with self.assertRaises(ds.DirectorScriptError):
            ds.generate_script("Big Bang", 2.5, "en", llm=llm)  # type: ignore[arg-type]
        with self.assertRaises(ds.DirectorScriptError):
            ds.generate_script("Big Bang", 1, "de", llm=llm)
        self.assertEqual(llm.calls, 0)


class ChatTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env = mock.patch.dict(
            os.environ,
            {"DEEPSEEK_API_KEY": FAKE_KEY, "DUP_LLM_API_KEY": "", "DEEPSEEK_BASE_URL": "", "DUP_LLM_BASE_URL": ""},
        )
        self._env.start()

    def tearDown(self) -> None:
        self._env.stop()

    def test_successful_call_parses_json(self) -> None:
        payload = {"title": "x"}
        with mock.patch("director_script.urllib.request.urlopen", return_value=_FakeResponse(_chat_body(json.dumps(payload)))) as up:
            self.assertEqual(ds.chat_json([{"role": "user", "content": "hi"}]), payload)
        req = up.call_args.args[0]
        self.assertTrue(req.full_url.startswith("https://api.deepseek.com/v1/"))
        self.assertEqual(req.get_header("Authorization"), f"Bearer {FAKE_KEY}")

    def test_missing_key_fails_closed_without_network(self) -> None:
        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "", "DUP_LLM_API_KEY": ""}):
            with mock.patch("director_script.urllib.request.urlopen") as up:
                with self.assertRaisesRegex(ds.DirectorScriptError, "key missing"):
                    ds.chat_json([])
                up.assert_not_called()

    def test_http_base_url_is_refused(self) -> None:
        with mock.patch.dict(os.environ, {"DEEPSEEK_BASE_URL": "http://insecure.example/v1"}):
            with self.assertRaisesRegex(ds.DirectorScriptError, "https://"):
                ds.chat_json([])

    def test_http_error_is_fail_closed_and_never_leaks_key(self) -> None:
        err = urllib.error.HTTPError("https://api.deepseek.com/v1/chat/completions", 401, "Unauthorized", None, io.BytesIO(b""))
        with mock.patch("director_script.urllib.request.urlopen", side_effect=err):
            with self.assertRaises(ds.DirectorScriptError) as ctx:
                ds.chat_json([])
        self.assertIn("HTTP 401", str(ctx.exception))
        self.assertNotIn(FAKE_KEY, str(ctx.exception))

    def test_network_error_is_fail_closed(self) -> None:
        with mock.patch("director_script.urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
            with self.assertRaisesRegex(ds.DirectorScriptError, "network error"):
                ds.chat_json([])

    def test_truncated_response_is_refused(self) -> None:
        body = _chat_body('{"scenes": []}', finish_reason="length")
        with mock.patch("director_script.urllib.request.urlopen", return_value=_FakeResponse(body)):
            with self.assertRaisesRegex(ds.DirectorScriptError, "truncated"):
                ds.chat_json([])

    def test_non_json_content_is_refused(self) -> None:
        with mock.patch("director_script.urllib.request.urlopen", return_value=_FakeResponse(_chat_body("Sure! Here is your script"))):
            with self.assertRaisesRegex(ds.DirectorScriptError, "not valid JSON"):
                ds.chat_json([])


class MinDurationFieldTests(unittest.TestCase):
    def _deck(self) -> dict:
        script = ds.generate_script("Big Bang", 1, "en", llm=_FakeLLM([_act1_payload(_one_minute_scenes())]))
        return ds.script_to_deck(script)

    def test_out_of_range_min_duration_is_refused(self) -> None:
        for bad in (0, 0.5, 121, "12", True):
            deck = self._deck()
            deck["slides"][0]["min_duration_sec"] = bad
            with self.assertRaisesRegex(Exception, "min_duration_sec"):
                validate_deck(deck, check_assets=False)

    def test_min_duration_is_optional(self) -> None:
        deck = self._deck()
        del deck["slides"][0]["min_duration_sec"]
        validate_deck(deck, check_assets=False)


class OutputTests(unittest.TestCase):
    def test_overwrite_protection_and_roundtrip(self) -> None:
        script = ds.generate_script("Big Bang", 1, "en", llm=_FakeLLM([_act1_payload(_one_minute_scenes())]))
        deck = ds.script_to_deck(script)
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            deck_p, script_p = ds.write_outputs(
                script, deck, deck_out=tmp_p / "d.json", script_out=tmp_p / "s.json", overwrite=False
            )
            self.assertTrue(deck_p.is_file() and script_p.is_file())
            with self.assertRaisesRegex(ds.DirectorScriptError, "already exists"):
                ds.write_outputs(script, deck, deck_out=tmp_p / "d.json", script_out=tmp_p / "s2.json", overwrite=False)
            ds.write_outputs(script, deck, deck_out=tmp_p / "d.json", script_out=tmp_p / "s.json", overwrite=True)

            stored = json.loads(script_p.read_text(encoding="utf-8"))
            revalidated = ds.revalidate_script(stored)
            self.assertEqual(len(revalidated["scenes"]), 5)

    def test_tampered_stored_script_is_rejected(self) -> None:
        script = ds.generate_script("Big Bang", 1, "en", llm=_FakeLLM([_act1_payload(_one_minute_scenes())]))
        script["scenes"][0]["target_sec"] = 30  # 80 words / 30 s keeps a valid pace; total becomes 78 s (+30%)
        script["scenes"][0]["voice_text"] = " ".join(["word"] * 80)
        with self.assertRaisesRegex(ds.DirectorScriptError, "durations sum"):
            ds.revalidate_script(script)
        script = ds.generate_script("Big Bang", 1, "en", llm=_FakeLLM([_act1_payload(_one_minute_scenes())]))
        script["scenes"][0]["voice_text"] = " ".join(["word"] * 40)  # 40 words in 12 s
        with self.assertRaisesRegex(ds.DirectorScriptError, "words/sec"):
            ds.revalidate_script(script)

    def test_deck_failing_validate_deck_is_refused(self) -> None:
        script = ds.generate_script("Big Bang", 1, "en", llm=_FakeLLM([_act1_payload(_one_minute_scenes())]))
        deck = ds.script_to_deck(script)
        deck["theme"] = "not_a_theme"
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ds.DirectorScriptError, "validate_deck"):
                ds.write_outputs(script, deck, deck_out=Path(tmp) / "x.json", script_out=Path(tmp) / "y.json", overwrite=False)


if __name__ == "__main__":
    unittest.main()
