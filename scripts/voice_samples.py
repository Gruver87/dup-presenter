"""DUP Presenter - voice quality lab.

Synthesizes the same Russian test phrase with several Silero models/speakers and
writes objective metrics next to each WAV. Used to choose the voice before a
deck is rendered. Nothing here changes the production deck.

Usage:
    python scripts/voice_samples.py --model models/silero/v5_ru.pt --tag v5
"""

from __future__ import annotations

import argparse
import json
import math
import wave
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out" / "voice_samples"
SR = 48000
PHRASE = (
    "DUP Market Radar — это гибридный вотчлист на Python и Rust. "
    "Авто-торговля выключена по умолчанию. "
    "Это не прогноз прибыли и не аудит."
)


def metrics(audio: np.ndarray) -> dict:
    """Objective signal metrics. Noise floor = RMS of the quietest 10% of 20 ms frames."""
    frame = int(0.02 * SR)
    n = len(audio) // frame
    frames = audio[: n * frame].reshape(n, frame)
    rms = np.sqrt((frames ** 2).mean(axis=1) + 1e-12)
    rms_db = 20 * np.log10(rms + 1e-12)
    noise_floor_db = float(np.percentile(rms_db, 10))
    speech_db = float(np.percentile(rms_db, 90))
    peak = float(np.max(np.abs(audio)))
    return {
        "duration_s": round(len(audio) / SR, 2),
        "peak_dbfs": round(20 * math.log10(peak + 1e-12), 2),
        "rms_dbfs": round(20 * math.log10(float(np.sqrt((audio ** 2).mean())) + 1e-12), 2),
        "noise_floor_dbfs": round(noise_floor_db, 2),
        "speech_level_dbfs": round(speech_db, 2),
        "snr_estimate_db": round(speech_db - noise_floor_db, 2),
        "clipped_samples": int((np.abs(audio) >= 0.999).sum()),
    }


def write_wav(path: Path, audio: np.ndarray) -> None:
    pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())


def main() -> int:
    parser = argparse.ArgumentParser(description="Silero voice quality samples")
    parser.add_argument("--model", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--speakers", default="xenia,aidar,baya,kseniya,eugene")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    model = torch.package.PackageImporter(str(ROOT / args.model)).load_pickle("tts_models", "model")
    model.to(torch.device("cpu"))
    available = getattr(model, "speakers", None)
    print(f"[voice] model={args.model} speakers={available}")

    ssml = f'<speak><prosody rate="95%">{PHRASE}</prosody></speak>'
    report = []
    for speaker in [s.strip() for s in args.speakers.split(",") if s.strip()]:
        audio = model.apply_tts(ssml_text=ssml, speaker=speaker, sample_rate=SR)
        audio_np = audio.detach().cpu().numpy().astype(np.float32)
        name = f"{args.tag}_{speaker}"
        write_wav(OUT / f"{name}.wav", audio_np)
        m = metrics(audio_np)
        m["speaker"] = speaker
        m["file"] = f"out/voice_samples/{name}.wav"
        report.append(m)
        print(f"[voice] {name}: {m}")

    (OUT / f"{args.tag}_metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
