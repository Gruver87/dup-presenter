"""Unit tests for scripts/cloud_llm.py (cloud LLM settings from environment)."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import cloud_llm  # noqa: E402

KEYS = ("DUP_LLM_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "DUP_LLM_BASE_URL", "DEEPSEEK_BASE_URL", "DUP_LLM_MODEL", "DEEPSEEK_MODEL")


def _env(**over: str) -> dict[str, str]:
    base = {k: v for k, v in os.environ.items() if k not in KEYS}
    base.update(over)
    return base


class CloudLlmConfigTests(unittest.TestCase):
    def test_no_key_means_no_cloud(self) -> None:
        with mock.patch.dict(os.environ, _env(), clear=True):
            self.assertIsNone(cloud_llm.cloud_llm_config())

    def test_dup_settings_take_precedence(self) -> None:
        env = _env(
            DUP_LLM_API_KEY="test-marker-a",
            DEEPSEEK_API_KEY="test-marker-b",
            DUP_LLM_BASE_URL="https://api.deepseek.com/v1/",
            DUP_LLM_MODEL="deepseek-chat",
        )
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(
                cloud_llm.cloud_llm_config(),
                ("test-marker-a", "https://api.deepseek.com/v1", "deepseek-chat"),
            )

    def test_defaults_when_only_key_is_set(self) -> None:
        with mock.patch.dict(os.environ, _env(OPENAI_API_KEY="test-marker-c"), clear=True):
            self.assertEqual(
                cloud_llm.cloud_llm_config(),
                ("test-marker-c", "https://api.openai.com/v1", "gpt-4o-mini"),
            )


if __name__ == "__main__":
    unittest.main()
