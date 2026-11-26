"""Fail-closed tests for the `deepseek` / `cloud` LLM mode of the Idea Engine.

The network is replaced with a fake `urllib.request.urlopen`, so these tests never
reach a real provider and never need a real API key.
"""

from __future__ import annotations

import io
import json
import os
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from idea_engine import IdeaEngineError, _angle_blueprints, generate_ideas  # noqa: E402

_LLM_ENV_KEYS = (
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODEL",
    "DUP_LLM_API_KEY",
    "DUP_LLM_BASE_URL",
    "DUP_LLM_MODEL",
    "OPENAI_API_KEY",
)


def _clean_env(**extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in _LLM_ENV_KEYS}
    env.update(extra)
    return env


class _FakeResponse(io.BytesIO):
    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc: Any) -> None:
        return None


def _chat_response(content: str) -> _FakeResponse:
    body = {"choices": [{"message": {"role": "assistant", "content": content}}]}
    return _FakeResponse(json.dumps(body, ensure_ascii=False).encode("utf-8"))


def _ideas_json(n: int = 2) -> str:
    # Use the same well-formed idea shape the validator expects (slides included),
    # built from the offline blueprints so the fixture is never hand-rolled and drifting.
    ideas = _angle_blueprints("Тема", "ru", "all")[:n]
    return json.dumps({"ideas": ideas}, ensure_ascii=False)


class DeepSeekModeTests(unittest.TestCase):
    def test_deepseek_mode_calls_deepseek_endpoint_and_returns_llm_source(self) -> None:
        captured: dict[str, Any] = {}

        def fake_urlopen(req: Any, timeout: float = 0) -> _FakeResponse:
            captured["url"] = req.full_url
            captured["method"] = req.get_method()
            captured["auth"] = req.get_header("Authorization")
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return _chat_response(_ideas_json(2))

        with mock.patch.dict(os.environ, _clean_env(DEEPSEEK_API_KEY="sk-test-deepseek"), clear=True), mock.patch(
            "idea_engine.urllib.request.urlopen", side_effect=fake_urlopen
        ):
            res = generate_ideas("Большой взрыв", lang="ru", count=2, mode="deepseek")

        self.assertTrue(res["ok"])
        self.assertEqual(res["source"], "deepseek")
        self.assertEqual(len(res["ideas"]), 2)
        self.assertEqual(captured["url"], "https://api.deepseek.com/v1/chat/completions")
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["auth"], "Bearer sk-test-deepseek")
        self.assertEqual(captured["body"]["model"], "deepseek-chat")
        self.assertEqual(captured["body"]["response_format"], {"type": "json_object"})

    def test_deepseek_model_and_base_url_can_be_overridden_by_env(self) -> None:
        captured: dict[str, Any] = {}

        def fake_urlopen(req: Any, timeout: float = 0) -> _FakeResponse:
            captured["url"] = req.full_url
            captured["model"] = json.loads(req.data.decode("utf-8"))["model"]
            return _chat_response(_ideas_json(1))

        env = _clean_env(
            DEEPSEEK_API_KEY="sk-x",
            DEEPSEEK_BASE_URL="https://proxy.example.test/v1/",
            DEEPSEEK_MODEL="deepseek-reasoner",
        )
        with mock.patch.dict(os.environ, env, clear=True), mock.patch(
            "idea_engine.urllib.request.urlopen", side_effect=fake_urlopen
        ):
            generate_ideas("Тема", lang="ru", count=1, mode="deepseek")

        self.assertEqual(captured["url"], "https://proxy.example.test/v1/chat/completions")
        self.assertEqual(captured["model"], "deepseek-reasoner")

    def test_deepseek_mode_without_key_fails_closed(self) -> None:
        with mock.patch.dict(os.environ, _clean_env(), clear=True):
            with self.assertRaisesRegex(IdeaEngineError, "requires DEEPSEEK_API_KEY"):
                generate_ideas("Тема", lang="ru", count=1, mode="deepseek")

    def test_deepseek_network_error_never_falls_back_to_template(self) -> None:
        def boom(req: Any, timeout: float = 0) -> None:
            raise OSError("network unreachable")

        with mock.patch.dict(os.environ, _clean_env(DEEPSEEK_API_KEY="sk-x"), clear=True), mock.patch(
            "idea_engine.urllib.request.urlopen", side_effect=boom
        ):
            with self.assertRaisesRegex(IdeaEngineError, "DeepSeek request failed"):
                generate_ideas("Тема", lang="ru", count=1, mode="deepseek")

    def test_deepseek_non_json_content_fails_closed(self) -> None:
        with mock.patch.dict(os.environ, _clean_env(DEEPSEEK_API_KEY="sk-x"), clear=True), mock.patch(
            "idea_engine.urllib.request.urlopen",
            side_effect=lambda req, timeout=0: _chat_response("this is not json at all"),
        ):
            with self.assertRaises(IdeaEngineError):
                generate_ideas("Тема", lang="ru", count=1, mode="deepseek")

    def test_cloud_mode_prefers_deepseek_key_when_only_deepseek_is_set(self) -> None:
        captured: dict[str, Any] = {}

        def fake_urlopen(req: Any, timeout: float = 0) -> _FakeResponse:
            captured["url"] = req.full_url
            return _chat_response(_ideas_json(1))

        with mock.patch.dict(os.environ, _clean_env(DEEPSEEK_API_KEY="sk-x"), clear=True), mock.patch(
            "idea_engine.urllib.request.urlopen", side_effect=fake_urlopen
        ):
            generate_ideas("Тема", lang="ru", count=1, mode="cloud")

        self.assertEqual(captured["url"], "https://api.deepseek.com/v1/chat/completions")

    def test_cloud_mode_with_openai_key_keeps_openai_default(self) -> None:
        captured: dict[str, Any] = {}

        def fake_urlopen(req: Any, timeout: float = 0) -> _FakeResponse:
            captured["url"] = req.full_url
            captured["model"] = json.loads(req.data.decode("utf-8"))["model"]
            return _chat_response(_ideas_json(1))

        with mock.patch.dict(os.environ, _clean_env(OPENAI_API_KEY="sk-openai"), clear=True), mock.patch(
            "idea_engine.urllib.request.urlopen", side_effect=fake_urlopen
        ):
            generate_ideas("Тема", lang="ru", count=1, mode="cloud")

        self.assertEqual(captured["url"], "https://api.openai.com/v1/chat/completions")
        self.assertEqual(captured["model"], "gpt-4o-mini")

    def test_unknown_mode_is_rejected(self) -> None:
        with self.assertRaisesRegex(IdeaEngineError, "deepseek"):
            generate_ideas("Тема", lang="ru", count=1, mode="anthropic")


if __name__ == "__main__":
    unittest.main()
