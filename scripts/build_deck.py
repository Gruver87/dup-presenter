"""DUP Presenter — fail-closed deck validator, local Silero v4 TTS builder, and MP4 renderer.

Usage:
    python scripts/build_deck.py decks/dup_labs.json
    python scripts/build_deck.py decks/dup_labs.json --render
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import urllib.request
import wave
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parent.parent
SILERO_URL = "https://models.silero.ai/models/tts/ru/v4_ru.pt"
SILERO_PATH = ROOT / "models" / "silero" / "v4_ru.pt"
PUBLIC_DIR = ROOT / "public"
VOICE_DIR = PUBLIC_DIR / "voice"
RESOLVED_JSON = ROOT / "src" / "generated" / "deck_resolved.json"
SR = 48000

ALLOWED_TYPES = {"hero_3d", "code_split", "screen_split", "outro_3d"}
ALLOWED_SPEAKERS = {"xenia", "eugene", "aidar", "baya", "kseniya"}


class DeckValidationError(RuntimeError):
    """Raised when a presentation deck fails fail-closed validation."""


def validate_deck(deck: dict) -> None:
    if not isinstance(deck.get("slug"), str) or not deck["slug"].strip():
        raise DeckValidationError("deck.slug must be a non-empty string")
    slides = deck.get("slides")
    if not isinstance(slides, list) or not slides:
        raise DeckValidationError("deck.slides must be a non-empty list")

    speaker = deck.get("voice", {}).get("speaker", "xenia")
    if speaker not in ALLOWED_SPEAKERS:
        raise DeckValidationError(f"Unsupported Silero speaker {speaker!r}; allowed: {sorted(ALLOWED_SPEAKERS)}")

    seen_ids: set[str] = set()
    for idx, slide in enumerate(slides):
        sid = slide.get("id")
        stype = slide.get("type")
        if not isinstance(sid, str) or not sid or sid in seen_ids:
            raise DeckValidationError(f"Slide #{idx} has missing or duplicate id: {sid!r}")
        seen_ids.add(sid)
        if stype not in ALLOWED_TYPES:
            raise DeckValidationError(f"Slide {sid}: unsupported type {stype!r}")
        if not slide.get("voice_ssml") and not slide.get("voice_text"):
            raise DeckValidationError(f"Slide {sid}: missing voice_ssml or voice_text")
        if stype == "screen_split":
            screens = slide.get("screens") or []
            if not screens:
                raise DeckValidationError(f"Slide {sid}: screen_split requires at least one screen")
            for sc in screens:
                rel = sc.get("src", "")
                full = PUBLIC_DIR / rel
                if not full.is_file():
                    raise DeckValidationError(f"Slide {sid}: missing screen file {full}")


def build_ambient_bed(duration_sec: int, sr: int) -> bytes:
    n = duration_sec * sr
    t = np.linspace(0, duration_sec, n, endpoint=False, dtype=np.float32)
    chords = [
        [146.83, 220.00, 261.63, 329.63],
        [116.54, 174.61, 220.00, 293.66],
        [130.81, 196.00, 293.66, 329.63],
        [110.00, 164.81, 220.00, 261.63],
    ]
    pad = np.zeros(n, dtype=np.float32)
    chord_len = 8.0
    for i in range(int(math.ceil(duration_sec / chord_len))):
        s_idx = int(i * chord_len * sr)
        e_idx = int(min((i + 1) * chord_len, float(duration_sec)) * sr)
        seg_t = t[s_idx:e_idx]
        seg_len = e_idx - s_idx
        if seg_len <= 0:
            continue
        env = np.ones(seg_len, dtype=np.float32)
        xf = min(int(1.2 * sr), seg_len // 3)
        if xf > 0:
            env[:xf] = np.linspace(0, 1, xf, dtype=np.float32)
            env[-xf:] = np.linspace(1, 0, xf, dtype=np.float32)
        seg = np.zeros(seg_len, dtype=np.float32)
        for j, f in enumerate(chords[i % len(chords)]):
            lfo = 0.78 + 0.22 * np.sin(2 * np.pi * (0.12 + j * 0.03) * seg_t)
            seg += lfo * (0.55 * np.sin(2 * np.pi * f * seg_t) + 0.2 * np.sin(2 * np.pi * f * 0.5 * seg_t))
        pad[s_idx:e_idx] += seg * env

    pad *= 0.88 + 0.12 * np.sin(2 * np.pi * 1.0 * t)
    pad = pad / (np.max(np.abs(pad)) + 1e-6) * 0.34
    fi, fo = int(1.5 * sr), int(2.5 * sr)
    pad[:fi] *= np.linspace(0, 1, fi, dtype=np.float32)
    pad[-fo:] *= np.linspace(1, 0, fo, dtype=np.float32)
    return (np.clip(pad, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()


def ensure_silero() -> Path:
    if not SILERO_PATH.is_file():
        SILERO_PATH.parent.mkdir(parents=True, exist_ok=True)
        print(f"[tts] downloading Silero v4 Russian model -> {SILERO_PATH}")
        urllib.request.urlretrieve(SILERO_URL, SILERO_PATH)
    return SILERO_PATH


def synthesize_deck(deck: dict) -> dict:
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    RESOLVED_JSON.parent.mkdir(parents=True, exist_ok=True)

    model = torch.package.PackageImporter(str(ensure_silero())).load_pickle("tts_models", "model")
    model.to(torch.device("cpu"))

    speaker = deck.get("voice", {}).get("speaker", "xenia")
    rate = deck.get("voice", {}).get("rate", "95%")

    total_sec = 0
    resolved_slides = []
    total_slides = len(deck["slides"])
    for idx, slide in enumerate(deck["slides"], start=1):
        sid = slide["id"]
        ssml = slide.get("voice_ssml") or f'<speak><prosody rate="{rate}">{slide["voice_text"]}</prosody></speak>'
        audio = model.apply_tts(ssml_text=ssml, speaker=speaker, sample_rate=SR)
        peak = float(audio.abs().max()) or 1.0
        audio = audio / peak * 0.86
        pcm = (audio.clamp(-1.0, 1.0) * 32767.0).short().cpu().numpy().tobytes()
        wav_path = VOICE_DIR / f"{sid}.wav"
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SR)
            wf.writeframes(pcm)
        dur = len(audio) / float(SR)
        scene_s = math.ceil(dur) + 1
        total_sec += scene_s
        print(f"[tts] {sid} ({speaker}): {dur:.2f}s -> slide {scene_s}s")

        item = dict(slide)
        item["duration_sec"] = scene_s
        item["num"] = f"{idx:02d} / {total_slides:02d}"
        item["voice_file"] = f"voice/{sid}.wav"
        resolved_slides.append(item)

    pad_path = VOICE_DIR / "bg_pad.wav"
    with wave.open(str(pad_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(build_ambient_bed(total_sec + 2, SR))

    resolved = dict(deck)
    resolved["slides"] = resolved_slides
    resolved["total_seconds"] = total_sec
    resolved["ambient_file"] = "voice/bg_pad.wav"
    RESOLVED_JSON.write_text(json.dumps(resolved, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[deck] wrote {RESOLVED_JSON} (total={total_sec}s)")
    return resolved


def run_cmd(args: list[str]) -> None:
    print(f"[run] {' '.join(args)}")
    res = subprocess.run(args, cwd=str(ROOT), shell=True)
    if res.returncode != 0:
        raise RuntimeError(f"Command failed (exit={res.returncode}): {' '.join(args)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="DUP Presenter deck builder")
    parser.add_argument("deck", help="Path to deck JSON (e.g. decks/dup_labs.json)")
    parser.add_argument("--render", action="store_true", help="Also type-check and render MP4")
    parser.add_argument("--skip-tts", action="store_true", help="Reuse existing WAV files")
    args = parser.parse_args()

    deck_path = Path(args.deck)
    if not deck_path.is_absolute():
        deck_path = ROOT / deck_path
    if not deck_path.is_file():
        print(f"[ERROR] Deck not found: {deck_path}", file=sys.stderr)
        return 2

    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    validate_deck(deck)
    if not args.skip_tts:
        resolved = synthesize_deck(deck)
    else:
        if not RESOLVED_JSON.is_file():
            print("[ERROR] --skip-tts used but deck_resolved.json does not exist", file=sys.stderr)
            return 2
        resolved = json.loads(RESOLVED_JSON.read_text(encoding="utf-8"))

    if args.render:
        out_mp4 = ROOT / "out" / f"{resolved['slug']}.mp4"
        out_mp4.parent.mkdir(parents=True, exist_ok=True)
        run_cmd(["npx", "tsc", "--noEmit"])
        run_cmd(["npx", "remotion", "render", "DupPresenter", str(out_mp4)])
        print(f"[OK] Rendered: {out_mp4} ({out_mp4.stat().st_size / 1_048_576:.2f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
