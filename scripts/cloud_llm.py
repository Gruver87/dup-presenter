"""OpenAI-compatible cloud LLM settings shared by the console (archive query translation, internet status)."""

from __future__ import annotations

import os


def cloud_llm_config() -> tuple[str, str, str] | None:
    """Return (api_key, base_url, model) for configured OpenAI-compatible cloud LLM, or None."""
    api_key = (
        os.environ.get("DUP_LLM_API_KEY", "").strip()
        or os.environ.get("DEEPSEEK_API_KEY", "").strip()
        or os.environ.get("OPENAI_API_KEY", "").strip()
    )
    if not api_key:
        return None
    base_url = (
        os.environ.get("DUP_LLM_BASE_URL", "").strip()
        or os.environ.get("DEEPSEEK_BASE_URL", "").strip()
        or "https://api.openai.com/v1"
    ).rstrip("/")
    model = (
        os.environ.get("DUP_LLM_MODEL", "").strip()
        or os.environ.get("DEEPSEEK_MODEL", "").strip()
        or "gpt-4o-mini"
    )
    return api_key, base_url, model
