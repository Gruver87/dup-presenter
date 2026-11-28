"""Tests for phrase-level voice assembly (scripts/speech_phrasing.py)."""

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from speech_phrasing import PAUSE_SEC, assemble, pause_profile, split_phrases  # noqa: E402

SR = 16000


def test_split_keeps_text_and_marks_pauses():
    phrases = split_phrases("Первая фраза. Вторая, третья; четвёртая? Конец!")
    texts = [t for t, _ in phrases]
    pauses = [p for _, p in phrases]
    assert texts == ["Первая фраза", "Вторая", "третья", "четвёртая", "Конец"]
    assert pauses == [PAUSE_SEC["."], PAUSE_SEC[","], PAUSE_SEC[";"], PAUSE_SEC["?"], PAUSE_SEC["!"]]


def test_split_drops_empty_and_refuses_empty_text():
    assert split_phrases("  Текст.  ")[0][0] == "Текст"
    with pytest.raises(ValueError):
        split_phrases(" .,; ")


def test_terminal_mark_absent_uses_default_pause():
    phrases = split_phrases("Фраза без знака")
    assert phrases == [("Фраза без знака", 0.3)]


def test_assemble_inserts_measured_silence_between_phrases():
    phrases = [("а", 0.5), ("б", 0.2)]
    tone = lambda _text: np.ones(SR // 10, dtype=np.float32)  # 100 ms of signal per phrase
    audio = assemble(phrases, tone, SR, lead_sec=0.0, tail_sec=0.0)
    # 100ms speech + 500ms pause + 100ms speech + 0 tail
    assert len(audio) == int(SR * 0.7)
    profile = pause_profile(audio, SR)
    assert profile == [0.5]


def test_assemble_refuses_empty_synthesis():
    with pytest.raises(RuntimeError):
        assemble([("x", 0.1)], lambda _t: np.zeros(0, dtype=np.float32), SR)


def test_pause_profile_detects_only_long_silences():
    audio = np.concatenate([
        np.ones(SR // 5, dtype=np.float32),
        np.zeros(int(SR * 0.05), dtype=np.float32),  # 50 ms: below threshold
        np.ones(SR // 5, dtype=np.float32),
        np.zeros(int(SR * 0.4), dtype=np.float32),  # 400 ms: counted
    ])
    profile = pause_profile(audio, SR)
    # 20 ms frames: a frame straddling a boundary is non-silent, so a run may be under-counted by <= 2 frames.
    assert len(profile) == 1
    assert 0.4 - 0.04 <= profile[0] <= 0.4


def test_horizon_deck_uses_phrasing_and_story_validates():
    import json

    import build_deck as bd

    deck_path = ROOT / "decks" / "dup-market-radar-horizon-3026.json"
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    assert all(s.get("phrasing") is True for s in deck["slides"])
    assert all("voice_text" in s and "voice_ssml" not in s for s in deck["slides"])
    for s in deck["slides"]:
        assert split_phrases(s["voice_text"]), s["id"]
    bd.validate_deck(deck, check_assets=True)
