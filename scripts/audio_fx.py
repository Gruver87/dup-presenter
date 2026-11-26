"""Studio audio helpers for DUP Presenter:
- Offline procedural SFX synthesis (transition whoosh + soft UI pop)
- Speech-activity window detection for dynamic music ducking (engine-agnostic)
- Sentence + word-level karaoke caption alignment
- Bundled/system ffmpeg & ffprobe discovery
- Broadcast loudness normalization (-16 LUFS / -1.5 dBTP) via two-pass ffmpeg loudnorm
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
PUBLIC_SFX_DIR = ROOT / "public" / "sfx"
SR = 48000


class AudioFXError(RuntimeError):
    """Fail-closed error for audio FX / ffmpeg loudness processing."""


def _find_remotion_binary(name: str) -> Path | None:
    """Locate ffmpeg/ffprobe bundled inside @remotion/compositor-* if not on PATH."""
    exe = f"{name}.exe" if os.name == "nt" else name
    found = shutil.which(name) or shutil.which(exe)
    if found:
        return Path(found)
    remotion_dir = ROOT / "node_modules" / "@remotion"
    if remotion_dir.is_dir():
        for cand in sorted(remotion_dir.glob(f"compositor-*/{exe}")):
            if cand.is_file():
                return cand
    return None


def find_ffmpeg() -> Path:
    path = _find_remotion_binary("ffmpeg")
    if path is None:
        raise AudioFXError("ffmpeg not found on PATH or inside node_modules/@remotion/compositor-*")
    return path


def find_ffprobe() -> Path:
    path = _find_remotion_binary("ffprobe")
    if path is None:
        raise AudioFXError("ffprobe not found on PATH or inside node_modules/@remotion/compositor-*")
    return path


def _write_wav_mono(path: Path, samples: np.ndarray, sr: int = SR) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm)


def _synth_whoosh(sr: int = SR, duration_sec: float = 0.38) -> np.ndarray:
    """Subtle, warm bandpass-swept transition whoosh (deterministic seed, peak ~ -10 dBFS)."""
    from scipy.signal import butter, sosfilt

    n = int(sr * duration_sec)
    rng = np.random.default_rng(778888)
    noise = rng.standard_normal(n).astype(np.float64)
    t = np.linspace(0.0, 1.0, n, endpoint=False)

    # Blend two filtered bands (low warmth + airy mid sweep) so it feels polished, not harsh.
    sos_low = butter(2, [180.0, 900.0], btype="bandpass", fs=sr, output="sos")
    sos_air = butter(2, [900.0, 3200.0], btype="bandpass", fs=sr, output="sos")
    low = sosfilt(sos_low, noise)
    air = sosfilt(sos_air, noise)

    # Smooth bell envelope with gentle lead-in and tail
    env_low = np.sin(np.pi * (t ** 0.85)) ** 1.6
    env_air = np.sin(np.pi * (t ** 1.25)) ** 2.2
    # Subtle resonant pitch glide underneath
    f0, f1 = 160.0, 340.0
    phase = 2.0 * np.pi * duration_sec * (f0 * t + 0.5 * (f1 - f0) * (t ** 2))
    glide = np.sin(phase) * (np.sin(np.pi * t) ** 2.0) * 0.16

    mix = low * env_low * 0.72 + air * env_air * 0.48 + glide
    peak = float(np.max(np.abs(mix))) + 1e-12
    target_peak = 10.0 ** (-10.0 / 20.0)
    return (mix * (target_peak / peak)).astype(np.float32)


def _synth_ui_pop(sr: int = SR, duration_sec: float = 0.13) -> np.ndarray:
    """Soft harmonic UI tick/pop for slide / KPI reveal (peak ~ -12 dBFS)."""
    n = int(sr * duration_sec)
    t = np.linspace(0.0, duration_sec, n, endpoint=False)
    # Two-tone soft marimba-like click (pitch bends slightly up then decays)
    freq = 640.0 + 180.0 * np.exp(-t / 0.018)
    phase = 2.0 * np.pi * np.cumsum(freq) / sr
    tone = np.sin(phase) + 0.35 * np.sin(2.0 * phase)
    attack = np.minimum(1.0, t / 0.004)
    decay = np.exp(-t / 0.028)
    sig = tone * attack * decay
    peak = float(np.max(np.abs(sig))) + 1e-12
    target_peak = 10.0 ** (-12.0 / 20.0)
    return (sig * (target_peak / peak)).astype(np.float32)


def ensure_sfx_files(sr: int = SR) -> dict[str, str]:
    """Generate offline procedural SFX files in public/sfx/ if missing; return relative public paths."""
    PUBLIC_SFX_DIR.mkdir(parents=True, exist_ok=True)
    whoosh_path = PUBLIC_SFX_DIR / "transition_whoosh.wav"
    pop_path = PUBLIC_SFX_DIR / "ui_pop.wav"
    if not whoosh_path.is_file():
        _write_wav_mono(whoosh_path, _synth_whoosh(sr), sr)
    if not pop_path.is_file():
        _write_wav_mono(pop_path, _synth_ui_pop(sr), sr)
    return {
        "transition": "sfx/transition_whoosh.wav",
        "pop": "sfx/ui_pop.wav",
    }


def detect_speech_windows(
    audio: np.ndarray,
    sr: int = SR,
    offset_sec: float = 0.0,
    frame_ms: float = 25.0,
    threshold_db: float = -38.0,
    min_gap_sec: float = 0.35,
) -> list[list[float]]:
    """Detect [start_sec, end_sec] active speech intervals from mono float32 audio for music ducking."""
    if audio.size == 0:
        return []
    frame_len = max(1, int(sr * frame_ms / 1000.0))
    n_frames = len(audio) // frame_len
    if n_frames == 0:
        return [[round(offset_sec, 3), round(offset_sec + len(audio) / float(sr), 3)]]
    trimmed = audio[: n_frames * frame_len].reshape(n_frames, frame_len).astype(np.float64)
    rms = np.sqrt(np.mean(trimmed ** 2, axis=1) + 1e-12)
    thresh = 10.0 ** (threshold_db / 20.0)
    active = rms >= thresh

    windows: list[list[float]] = []
    in_seg = False
    seg_start = 0.0
    step = frame_len / float(sr)
    for i, flag in enumerate(active):
        t = i * step
        if flag and not in_seg:
            seg_start = t
            in_seg = True
        elif not flag and in_seg:
            windows.append([seg_start, t])
            in_seg = False
    if in_seg:
        windows.append([seg_start, n_frames * step])

    if not windows:
        return [[round(offset_sec, 3), round(offset_sec + len(audio) / float(sr), 3)]]

    # Merge short pauses so music doesn't pump between words.
    merged: list[list[float]] = [windows[0]]
    for s, e in windows[1:]:
        if s - merged[-1][1] <= min_gap_sec:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    return [[round(offset_sec + s, 3), round(offset_sec + e, 3)] for s, e in merged]


def _word_weight(word: str) -> float:
    """Estimate relative spoken weight of a token (letters + digits + small pause on punctuation)."""
    core = re.sub(r"[^\wА-Яа-яЁё]", "", word)
    w = float(max(2, len(core)))
    if word.endswith((",", ";", ":")):
        w += 1.6
    elif word.endswith((".", "!", "?", "—", "–")):
        w += 2.2
    return w


def _build_words_in_span(text: str, start_sec: float, end_sec: float) -> list[dict]:
    tokens = [t for t in text.split() if t]
    if not tokens:
        return []
    span = max(0.05, end_sec - start_sec)
    weights = [_word_weight(t) for t in tokens]
    total_w = float(sum(weights)) or 1.0
    out: list[dict] = []
    cur = start_sec
    for tok, w in zip(tokens, weights):
        seg = span * (w / total_w)
        out.append({
            "w": tok,
            "start": round(cur, 3),
            "end": round(cur + seg, 3),
        })
        cur += seg
    return out


def _split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text) if p.strip()]
    return parts or ([text] if text else [])


def build_word_captions(
    plain: str,
    total_dur: float,
    boundaries: list[dict] | None = None,
    offset_sec: float = 0.0,
    speaker: str | None = None,
    spoken: str | None = None,
) -> list[dict]:
    """Build sentence CaptionCues with word-level timings.

    ``spoken`` is the text the TTS actually voiced (e.g. Latin brand names respelled for a Cyrillic voice). It is
    used only for alignment; it must have the same whitespace token count as ``plain`` or it is ignored.

    Timing sources, strongest first:
    - ``boundaries`` are real TTS word events ({start_sec, end_sec, text}); each display token is aligned to its
      event, so word highlight follows the voice. Tokens the TTS did not voice as one word are interpolated.
    - Without usable events (Kokoro/Silero return none, or alignment is below WORD_ALIGN_MIN_RATIO), sentence
      spans are split proportionally across the clip and words are spaced by length (estimate).
    Every non-empty sentence gets words either way, so karaoke never silently falls back to box.
    """
    sentences = _split_sentences(plain)
    if not sentences:
        return []

    tokens_per_sentence = [s.split() for s in sentences]
    flat_tokens = [t for toks in tokens_per_sentence for t in toks]

    aligned: list[tuple[float, float]] | None = None
    if boundaries:
        align_tokens = flat_tokens
        if spoken is not None and len(spoken.split()) == len(flat_tokens):
            align_tokens = spoken.split()
        # Alignment compares spoken tokens with events; spans are returned per display token (same count).
        spans_by_token, ratio = align_word_events(align_tokens, boundaries)
        if ratio >= WORD_ALIGN_MIN_RATIO:
            aligned = spans_by_token
            print(f"[captions] word timing from word events: {ratio:.0%} of words matched")
        else:
            print(f"[captions] word alignment {ratio:.0%} below {WORD_ALIGN_MIN_RATIO:.0%}; using estimated word timing")

    cues: list[dict] = []
    if aligned is not None:
        pos = 0
        for sent, toks in zip(sentences, tokens_per_sentence):
            token_spans = aligned[pos: pos + len(toks)]
            pos += len(toks)
            words = [
                {"w": tok, "start": round(offset_sec + s0, 3), "end": round(offset_sec + s1, 3)}
                for tok, (s0, s1) in zip(toks, token_spans)
            ]
            cue: dict = {
                "start_sec": words[0]["start"],
                "end_sec": words[-1]["end"],
                "text": sent,
                "words": words,
            }
            if speaker:
                cue["speaker"] = speaker
            cues.append(cue)
        return cues

    if not boundaries:
        print("[captions] word timing estimated (engine gives no word events)")
    weights = [max(4, len(s)) for s in sentences]
    total_w = float(sum(weights))
    cur = 0.0
    for sent, w in zip(sentences, weights):
        seg = total_dur * (w / total_w)
        s0, s1 = cur, cur + seg
        cur += seg
        st = round(offset_sec + s0, 3)
        en = round(offset_sec + s1, 3)
        cue = {
            "start_sec": st,
            "end_sec": en,
            "text": sent,
            "words": _build_words_in_span(sent, st, en),
        }
        if speaker:
            cue["speaker"] = speaker
        cues.append(cue)
    return cues


WORD_ALIGN_MIN_RATIO = 0.75
_NON_WORD_RE = re.compile(r"[\W_]+")
ASR_MODEL = "base.en"
_ASR_MODEL_OBJ: object | None = None


class WordTimingUnavailable(AudioFXError):
    """Word timing from local ASR is not available (package missing or model failed). Caller labels the estimate."""


def transcribe_word_events(audio: np.ndarray, sr: int) -> list[dict]:
    """Word timestamps for a clip via faster-whisper (local CPU, English model). Same event shape as Edge.

    The clip must be the exact audio written to the voice file, so timings match playback.
    Raises WordTimingUnavailable when faster-whisper or its model cannot be loaded.
    """
    global _ASR_MODEL_OBJ
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise WordTimingUnavailable("faster-whisper is not installed (pip install faster-whisper)") from exc
    from scipy.signal import resample_poly

    if _ASR_MODEL_OBJ is None:
        try:
            _ASR_MODEL_OBJ = WhisperModel(ASR_MODEL, device="cpu", compute_type="int8")
        except Exception as exc:  # model download/load failure: report, never guess timings
            raise WordTimingUnavailable(f"faster-whisper model {ASR_MODEL!r} failed to load: {exc}") from exc
    audio16 = resample_poly(audio.astype(np.float32), 16000, sr).astype(np.float32)
    segments, _info = _ASR_MODEL_OBJ.transcribe(audio16, language="en", word_timestamps=True, vad_filter=False)
    events: list[dict] = []
    for seg in segments:
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                events.append({"start_sec": round(float(w.start), 3), "end_sec": round(float(w.end), 3), "text": text})
    return events



def _word_core(text: str) -> str:
    """Alphanumeric core of a token, lowercased: 'spoken.' -> 'spoken', '5%' -> '5', '-' -> ''."""
    return _NON_WORD_RE.sub("", text).lower()


def _fill_word_times(
    tokens: list[str], times: list[tuple[float, float] | None], last_end: float
) -> list[tuple[float, float]]:
    """Give unmatched tokens times between their matched neighbours, spaced by spoken weight."""
    out = list(times)
    n = len(tokens)
    prev_idx = -1
    prev_end = 0.0
    for i in range(n + 1):
        if i < n and out[i] is None:
            continue
        gap = list(range(prev_idx + 1, i))
        if gap:
            start = prev_end
            stop = out[i][0] if i < n else max(prev_end, last_end)
            span = max(0.0, stop - start)
            weights = [_word_weight(tokens[j]) for j in gap]
            total_w = sum(weights) or 1.0
            cur = start
            for j, w in zip(gap, weights):
                seg = span * (w / total_w)
                out[j] = (cur, cur + seg)
                cur += seg
        if i < n:
            prev_idx = i
            prev_end = out[i][1]
    return [t if t is not None else (0.0, 0.0) for t in out]


def align_word_events(
    tokens: list[str], events: list[dict]
) -> tuple[list[tuple[float, float]], float]:
    """Align display tokens to TTS word events. Returns (start, end) per token in seconds and the match ratio.

    Matching uses alphanumeric cores (case-insensitive) with an order-preserving sequence alignment, so
    punctuation attached to a word ('spoken.') and TTS-dropped symbols ('-') do not break it. A token the TTS
    split or merged ('BTC/ETH' -> 'BTC', '/', 'ETH') is not matched and gets an interpolated time.
    Ratio = matched content tokens / content tokens; callers decide whether it is good enough.
    """
    from difflib import SequenceMatcher

    tok_idx = [i for i, t in enumerate(tokens) if _word_core(t)]
    ev_idx = [i for i, e in enumerate(events) if _word_core(str(e.get("text", "")))]
    if not tok_idx or not ev_idx:
        return [(0.0, 0.0)] * len(tokens), 0.0

    tok_cores = [_word_core(tokens[i]) for i in tok_idx]
    ev_cores = [_word_core(str(events[i].get("text", ""))) for i in ev_idx]
    times: list[tuple[float, float] | None] = [None] * len(tokens)
    matched = 0
    for block in SequenceMatcher(None, tok_cores, ev_cores, autojunk=False).get_matching_blocks():
        for k in range(block.size):
            ev = events[ev_idx[block.b + k]]
            times[tok_idx[block.a + k]] = (
                max(0.0, float(ev["start_sec"])),
                max(0.0, float(ev["end_sec"])),
            )
            matched += 1
    last_end = max(float(events[i]["end_sec"]) for i in ev_idx)
    return _fill_word_times(tokens, times, last_end), matched / len(tok_idx)


def normalize_mp4_loudness(
    mp4_path: Path,
    target_lufs: float = -16.0,
    true_peak: float = -1.5,
    lra: float = 11.0,
) -> dict:
    """Two-pass EBU R128 loudness normalization in-place (copies video stream, re-encodes AAC 320k)."""
    if not mp4_path.is_file():
        raise AudioFXError(f"MP4 not found for loudness normalization: {mp4_path}")
    ffmpeg = find_ffmpeg()

    # Pass 1: measure integrated loudness, true peak, LRA, threshold
    af_pass1 = f"loudnorm=I={target_lufs}:TP={true_peak}:LRA={lra}:print_format=json"
    p1 = subprocess.run(
        [str(ffmpeg), "-hide_banner", "-nostats", "-i", str(mp4_path), "-vn", "-af", af_pass1, "-f", "null", "-"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if p1.returncode != 0:
        raise AudioFXError(f"ffmpeg loudnorm pass 1 failed (exit={p1.returncode}): {p1.stderr[-400:]}")

    # Extract JSON block printed by loudnorm filter from stderr
    m = re.search(r"\{\s*\"input_i\"[\s\S]*?\}", p1.stderr)
    if not m:
        raise AudioFXError(f"Could not parse loudnorm measurement JSON from ffmpeg stderr: {p1.stderr[-300:]}")
    measured = json.loads(m.group(0))

    in_i = float(measured["input_i"])
    in_tp = float(measured["input_tp"])
    in_lra = float(measured["input_lra"])
    in_thresh = float(measured["input_thresh"])
    target_offset = float(measured["target_offset"])

    # Pass 2: linear normalization with exact measured parameters, video stream untouched (-c:v copy)
    af_pass2 = (
        f"loudnorm=I={target_lufs}:TP={true_peak}:LRA={lra}:"
        f"measured_I={in_i}:measured_TP={in_tp}:measured_LRA={in_lra}:"
        f"measured_thresh={in_thresh}:offset={target_offset}:linear=true:print_format=json"
    )
    fd, tmp_name = tempfile.mkstemp(prefix=f"{mp4_path.stem}_norm_", suffix=".mp4", dir=str(mp4_path.parent))
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        p2 = subprocess.run(
            [
                str(ffmpeg), "-y", "-hide_banner", "-nostats",
                "-i", str(mp4_path),
                "-c:v", "copy",
                "-af", af_pass2,
                "-c:a", "aac", "-b:a", "320k", "-ar", str(SR),
                "-movflags", "+faststart",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if p2.returncode != 0 or not tmp_path.is_file() or tmp_path.stat().st_size == 0:
            raise AudioFXError(f"ffmpeg loudnorm pass 2 failed (exit={p2.returncode}): {p2.stderr[-400:]}")
        m2 = re.search(r"\{\s*\"input_i\"[\s\S]*?\}", p2.stderr)
        out_stats = json.loads(m2.group(0)) if m2 else {}
        os.replace(str(tmp_path), str(mp4_path))
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    return {
        "input_lufs": round(in_i, 2),
        "input_tp_db": round(in_tp, 2),
        "output_lufs": round(float(out_stats.get("output_i", target_lufs)), 2),
        "output_tp_db": round(float(out_stats.get("output_tp", true_peak)), 2),
        "target_lufs": target_lufs,
    }
