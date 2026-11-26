"""Tests for fail-closed web search (Serper / Brave) and Idea Engine --web-search integration."""
from __future__ import annotations

import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import idea_engine  # noqa: E402
import web_search  # noqa: E402


class _FakeResp(io.BytesIO):
    def __enter__(self) -> "_FakeResp":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


class WebSearchTests(unittest.TestCase):
    def test_no_keys_fails_closed(self) -> None:
        env = {k: v for k, v in os.environ.items() if k not in {"SERPER_API_KEY", "BRAVE_API_KEY"}}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertIsNone(web_search.configured_provider())
            with self.assertRaises(web_search.WebSearchError):
                web_search.search_snippets("DUP Protocol latest news")

    def test_serper_parses_organic_results(self) -> None:
        fake_body = json.dumps({
            "organic": [
                {"title": "Result One", "snippet": "Fresh fact 1", "link": "https://example.com/1"},
                {"title": "Result Two", "snippet": "Fresh fact 2", "link": "https://example.com/2"},
            ]
        }).encode("utf-8")
        with mock.patch.dict(os.environ, {"SERPER_API_KEY": "test-marker-only"}, clear=False):
            with mock.patch("urllib.request.urlopen", return_value=_FakeResp(fake_body)):
                res = web_search.search_snippets("quantum ledger", lang="en", provider="serper")
        self.assertEqual(res["provider"], "serper")
        self.assertEqual(len(res["results"]), 2)
        self.assertEqual(res["results"][0]["url"], "https://example.com/1")
        formatted = web_search.format_snippets_for_prompt(res["results"], max_chars=200)
        self.assertIn("Result One", formatted)
        self.assertIn("Fresh fact 1", formatted)

    def test_brave_parses_web_results(self) -> None:
        fake_body = json.dumps({
            "web": {
                "results": [
                    {"title": "Brave Hit", "description": "Recent benchmark", "url": "https://brave.example/a"},
                ]
            }
        }).encode("utf-8")
        with mock.patch.dict(os.environ, {"BRAVE_API_KEY": "test-marker-only"}, clear=False):
            with mock.patch("urllib.request.urlopen", return_value=_FakeResp(fake_body)):
                res = web_search.search_snippets("rust pyo3", lang="ru", provider="brave")
        self.assertEqual(res["provider"], "brave")
        self.assertEqual(res["results"][0]["title"], "Brave Hit")
        self.assertEqual(res["results"][0]["snippet"], "Recent benchmark")

    def test_template_mode_refuses_web_search(self) -> None:
        with self.assertRaises(idea_engine.IdeaEngineError):
            idea_engine.generate_ideas("DUP Protocol", mode="template", web_search=True)

    def test_llm_mode_passes_web_snippets_into_prompt_and_returns_sources(self) -> None:
        fake_ws = {
            "provider": "serper",
            "query": "DUP Protocol",
            "results": [{"title": "DUP Release", "snippet": "v1.3 shipped", "url": "https://example.com/dup"}],
        }
        captured_ctx: list[str] = []

        def fake_llm(topic, lang, genre, count, mode, model, host, *, web_context=""):
            captured_ctx.append(web_context)
            return {
                "ideas": [
                    {
                        "id": "i1",
                        "genre": "tech_explainer",
                        "angle": "fresh release",
                        "title": "DUP v1.3 Overview",
                        "hook": "Fresh look at v1.3",
                        "aspect": "16:9",
                        "theme": "quantum_ledger",
                        "caption_style": "karaoke",
                        "duration_hint_sec": 60,
                        "slides": [
                            {"type": "hero_3d", "tag": "01", "title": "Intro", "voice_text": "Hello world"},
                            {"type": "quote", "tag": "02", "title": "Points", "voice_text": "Point one"},
                            {"type": "outro_3d", "tag": "03", "title": "End", "voice_text": "Thanks"},
                        ],
                    }
                ]
            }

        with mock.patch.object(web_search, "search_snippets", return_value=fake_ws):
            with mock.patch.object(idea_engine, "_call_llm_ideas", side_effect=fake_llm):
                out = idea_engine.generate_ideas("DUP Protocol", mode="deepseek", count=1, web_search=True)

        self.assertTrue(out["ok"])
        self.assertEqual(out["web_search"]["provider"], "serper")
        self.assertEqual(len(captured_ctx), 1)
        self.assertIn("DUP Release", captured_ctx[0])
        self.assertIn("v1.3 shipped", captured_ctx[0])


if __name__ == "__main__":
    unittest.main()
