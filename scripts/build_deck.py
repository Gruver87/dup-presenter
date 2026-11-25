"""DUP Presenter — fail-closed deck validator, local Silero TTS builder (RU v5 / EN v3),
SRT/VTT caption generator, podcast 2-voice mixer, thumbnail & MP4 renderer.

Usage:
    python scripts/build_deck.py decks/dup_labs.json
    python scripts/build_deck.py decks/dup_labs.json --render
"""

from __future__ import annotations

import argparse
import html
import json
import math
import re
import subprocess
import sys
import time
import urllib.request
import wave
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np
import torch

ROOT = Path(__file__).resolve().parent.parent
SILERO_MODELS = {
    "ru": ("https://models.silero.ai/models/tts/ru/v5_ru.pt", ROOT / "models" / "silero" / "v5_ru.pt"),
    "en": ("https://models.silero.ai/models/tts/en/v3_en.pt", ROOT / "models" / "silero" / "v3_en.pt"),
}
VOICE_PEAK_CEILING_DBFS = -1.0
VOICE_TARGET_RMS_DBFS = -18.0
VOICE_HIGHPASS_HZ = 70.0
PUBLIC_DIR = ROOT / "public"
VOICE_DIR = PUBLIC_DIR / "voice"
RESOLVED_JSON = ROOT / "src" / "generated" / "deck_resolved.json"
SR = 48000

ALLOWED_TYPES = {"hero_3d", "code_split", "screen_split", "arch_flow", "outro_3d", "timeline", "terminal", "kpi"}
from theme_catalog import THEME_IDS  # noqa: E402
from edge_engine import EDGE_RU_VOICES, EdgeEngineError, edge_available, synth_edge  # noqa: E402
from voice_clean import deess  # noqa: E402
from ru_speech import normalize_ru_ssml  # noqa: E402
from tts_engines import (  # noqa: E402
    KOKORO_DEFAULT,
    KOKORO_PARTNERS,
    KOKORO_VOICE_IDS,
    SILERO_EN_VOICE_IDS,
    KokoroEngine,
    TTSEngineError,
    speaker_engine,
    speaker_lang,
)

ALLOWED_THEMES = set(THEME_IDS)
ASPECT_DIMS = {"16:9": (1920, 1080), "9:16": (1080, 1920)}
ALLOWED_SPEAKERS_BY_LANG = {
    "ru": {"xenia", "eugene", "aidar", "baya", "kseniya"} | set(EDGE_RU_VOICES),
    "en": set(SILERO_EN_VOICE_IDS) | set(KOKORO_VOICE_IDS),
}
ALLOWED_SPEAKERS = ALLOWED_SPEAKERS_BY_LANG["ru"] | ALLOWED_SPEAKERS_BY_LANG["en"]
DEFAULT_PARTNER = {
    "eugene": "xenia", "xenia": "eugene", "aidar": "xenia", "baya": "eugene", "kseniya": "eugene",
    "dmitry": "eugene", "svetlana": "eugene",
    "en_1": "en_0", "en_0": "en_1", "en_5": "en_2", "en_2": "en_5", "en_10": "en_21", "en_21": "en_10",
    **KOKORO_PARTNERS,
}
DEFAULT_SPEAKER_BY_LANG = {"ru": "dmitry", "en": KOKORO_DEFAULT}
# Offline voice used for the whole deck when the online voice is unavailable (no internet / Edge error).
OFFLINE_FALLBACK_BY_LANG = {"ru": "eugene"}
EDGE_DECK_RETRY_PAUSE_SEC = 20


class DeckValidationError(RuntimeError):
    """Raised when a presentation deck fails fail-closed validation."""


def deck_lang(deck: dict) -> str:
    voice = deck.get("voice") or {}
    return voice.get("lang") or deck.get("lang") or speaker_lang(voice.get("speaker", ""))


def validate_deck(deck: dict) -> None:
    if not isinstance(deck.get("slug"), str) or not deck["slug"].strip():
        raise DeckValidationError("deck.slug must be a non-empty string")
    slides = deck.get("slides")
    if not isinstance(slides, list) or not slides:
        raise DeckValidationError("deck.slides must be a non-empty list")

    theme = deck.get("theme", "neon_cyber")
    if theme not in ALLOWED_THEMES:
        raise DeckValidationError(f"Unsupported theme {theme!r}; allowed: {sorted(ALLOWED_THEMES)}")

    aspect = deck.get("aspect", "16:9")
    if aspect not in ASPECT_DIMS:
        raise DeckValidationError(f"Unsupported aspect {aspect!r}; allowed: {sorted(ASPECT_DIMS)}")

    bg = deck.get("background") or {}
    if bg.get("enabled"):
        if bg.get("provider", "pixabay") not in {"pexels", "pixabay"}:
            raise DeckValidationError(f"background.provider must be pexels or pixabay, got {bg.get('provider')!r}")
    music = deck.get("music") or {}
    if music.get("enabled"):
        vol = float(music.get("volume", 0.12))
        if not 0.0 < vol <= 0.3:
            raise DeckValidationError(f"music.volume must be in (0, 0.3], got {vol}")
        if music.get("file") and Path(str(music["file"])).name != str(music["file"]):
            raise DeckValidationError("music.file must be a plain file name inside assets/music")

    voice = deck.get("voice") or {}
    lang = deck_lang(deck)
    if lang not in ALLOWED_SPEAKERS_BY_LANG:
        raise DeckValidationError(f"Unsupported language {lang!r}; allowed: {sorted(ALLOWED_SPEAKERS_BY_LANG)}")
    default_speaker = DEFAULT_SPEAKER_BY_LANG[lang]
    speaker = voice.get("speaker", default_speaker)
    if speaker not in ALLOWED_SPEAKERS_BY_LANG[lang]:
        raise DeckValidationError(
            f"Unsupported speaker {speaker!r} for lang={lang!r}; allowed: {sorted(ALLOWED_SPEAKERS_BY_LANG[lang])}"
        )
    if voice.get("mode") == "podcast":
        sp_b = voice.get("speaker_b") or DEFAULT_PARTNER.get(speaker, default_speaker)
        if sp_b not in ALLOWED_SPEAKERS_BY_LANG[lang]:
            raise DeckValidationError(f"Unsupported podcast speaker_b {sp_b!r} for lang={lang!r}")
    fallback = voice.get("fallback_speaker")
    if fallback is not None:
        # The fallback must be an offline voice: otherwise "offline" would still need the network.
        if fallback not in ALLOWED_SPEAKERS_BY_LANG[lang] or fallback in EDGE_RU_VOICES:
            raise DeckValidationError(
                f"fallback_speaker {fallback!r} must be an offline {lang!r} voice (e.g. eugene)"
            )

    seen_ids: set[str] = set()
    for idx, slide in enumerate(slides):
        sid = slide.get("id")
        stype = slide.get("type")
        if not isinstance(sid, str) or not sid or sid in seen_ids:
            raise DeckValidationError(f"Slide #{idx} has missing or duplicate id: {sid!r}")
        seen_ids.add(sid)
        if slide.get("background_query") is not None:
            from stock_media import StockMediaError, validate_query  # noqa: E402

            try:
                validate_query(str(slide["background_query"]))
            except StockMediaError as exc:
                raise DeckValidationError(f"Slide {sid}: {exc}") from exc
        if stype not in ALLOWED_TYPES:
            raise DeckValidationError(f"Slide {sid}: unsupported type {stype!r}")
        if not slide.get("voice_ssml") and not slide.get("voice_text") and not slide.get("dialogue"):
            raise DeckValidationError(f"Slide {sid}: missing voice_ssml, voice_text, or dialogue")
        if stype == "screen_split":
            screens = slide.get("screens") or []
            if not screens:
                raise DeckValidationError(f"Slide {sid}: screen_split requires at least one screen")
            for sc in screens:
                rel = sc.get("src", "")
                full = PUBLIC_DIR / rel
                if not full.is_file():
                    raise DeckValidationError(f"Slide {sid}: missing screen file {full}")
        if stype == "arch_flow":
            arch = slide.get("arch") or {}
            nodes = arch.get("nodes") or []
            if not nodes:
                raise DeckValidationError(f"Slide {sid}: arch_flow requires arch.nodes")
            node_ids = {n.get("id") for n in nodes if n.get("id")}
            for edge in arch.get("edges") or []:
                if edge.get("from") not in node_ids or edge.get("to") not in node_ids:
                    raise DeckValidationError(f"Slide {sid}: arch edge references unknown node {edge!r}")
        if stype == "timeline":
            steps = slide.get("bullets") or []
            if not (2 <= len(steps) <= 6):
                raise DeckValidationError(f"Slide {sid}: timeline needs 2..6 bullets (steps), got {len(steps)}")
        if stype == "terminal":
            code = slide.get("code") or {}
            if not code.get("lines"):
                raise DeckValidationError(f"Slide {sid}: terminal requires code.lines from a real symbol")
        if stype == "kpi":
            kpis = slide.get("kpis") or []
            if not (1 <= len(kpis) <= 4):
                raise DeckValidationError(f"Slide {sid}: kpi needs 1..4 kpis, got {len(kpis)}")
            for k in kpis:
                if not isinstance(k, dict):
                    raise DeckValidationError(f"Slide {sid}: each kpi must be an object with value and label")
                value = str(k.get("value", "")).strip()
                label = str(k.get("label", "")).strip()
                if not value or len(value) > 12 or not label:
                    raise DeckValidationError(f"Slide {sid}: each kpi needs value (1..12 chars) and label")


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


def postprocess_voice(x: np.ndarray) -> np.ndarray:
    """Clean a Silero clip for production. Float32 in, float32 out, peak <= -1 dBFS."""
    from scipy.signal import butter, sosfiltfilt

    sos = butter(2, VOICE_HIGHPASS_HZ, btype="highpass", fs=SR, output="sos")
    y = x.astype(np.float64)
    y = y - y.mean()
    y = sosfiltfilt(sos, y)
    fade = int(0.02 * SR)
    if len(y) > 2 * fade:
        y[:fade] *= np.linspace(0.0, 1.0, fade)
        y[-fade:] *= np.linspace(1.0, 0.0, fade)
    rms = float(np.sqrt(np.mean(y ** 2))) + 1e-12
    y = y * (10 ** (VOICE_TARGET_RMS_DBFS / 20) / rms)
    ceiling = 10 ** (VOICE_PEAK_CEILING_DBFS / 20)
    peak = float(np.max(np.abs(y))) or 1.0
    if peak > ceiling:
        y = y * (ceiling / peak)
    return y.astype(np.float32)


def ensure_silero(lang: str = "ru") -> Path:
    url, path = SILERO_MODELS[lang]
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        print(f"[tts] downloading Silero ({lang}) model -> {path}")
        urllib.request.urlretrieve(url, path)
    return path


def _plain_spoken_text(slide: dict) -> str:
    raw = slide.get("voice_text") or slide.get("voice_ssml") or ""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text)
    text = text.replace("+", "")
    return " ".join(text.split())


def _split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text) if p.strip()]
    return parts or ([text] if text else [])


def _build_proportional_captions(text: str, total_dur: float) -> list[dict]:
    sentences = _split_sentences(text)
    if not sentences:
        return []
    weights = [max(4, len(s)) for s in sentences]
    total_w = float(sum(weights))
    cues = []
    cur = 0.0
    for s, w in zip(sentences, weights):
        seg = total_dur * (w / total_w)
        cues.append({"start_sec": round(cur, 2), "end_sec": round(cur + seg, 2), "text": s})
        cur += seg
    return cues


def _fmt_ts(sec: float, sep: str) -> str:
    ms = int(round(max(0.0, sec) * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def write_subtitles(resolved: dict) -> tuple[Path, Path]:
    out_dir = ROOT / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = resolved["slug"]
    srt_path = out_dir / f"{slug}.srt"
    vtt_path = out_dir / f"{slug}.vtt"

    srt_lines: list[str] = []
    vtt_lines: list[str] = ["WEBVTT", ""]
    idx = 1
    offset = 0.0
    for slide in resolved["slides"]:
        for cue in slide.get("captions") or []:
            start = offset + float(cue["start_sec"])
            end = offset + float(cue["end_sec"])
            prefix = f"[{cue['speaker']}] " if cue.get("speaker") else ""
            text = prefix + cue["text"]
            srt_lines += [str(idx), f"{_fmt_ts(start, ',')} --> {_fmt_ts(end, ',')}", text, ""]
            vtt_lines += [f"{_fmt_ts(start, '.')} --> {_fmt_ts(end, '.')}", text, ""]
            idx += 1
        offset += float(slide["duration_sec"])

    srt_path.write_text("\n".join(srt_lines), encoding="utf-8")
    vtt_path.write_text("\n".join(vtt_lines), encoding="utf-8")
    print(f"[subs] wrote {srt_path.name} & {vtt_path.name} ({idx - 1} cues)")
    return srt_path, vtt_path


MUSIC_DIR = ROOT / "assets" / "music"
MUSIC_EXTS = {".mp3", ".wav", ".m4a", ".ogg"}


def attach_stock_media(deck: dict, resolved_slides: list[dict]) -> list[dict]:
    """Fetch a free stock clip for each slide that has background_query (only when background.enabled)."""
    bg = deck.get("background") or {}
    if not bg.get("enabled"):
        return []
    from stock_media import StockMediaError, fetch_background  # noqa: E402

    provider = bg.get("provider", "pixabay")
    aspect = deck.get("aspect", "16:9")
    credits: list[dict] = []
    for s in resolved_slides:
        query = s.get("background_query")
        if not query:
            continue
        try:
            media = fetch_background(provider, str(query), aspect, deck["slug"], s["id"])
        except StockMediaError as exc:
            raise DeckValidationError(f"Slide {s['id']}: {exc}") from exc
        s["media"] = media
        credits.append({"slide": s["id"], "credit": media["credit"], "credit_url": media["credit_url"]})
        print(f"[media] {s['id']}: {media['credit']} ({provider}, query={media['query']!r})")
    return credits


def attach_music(deck: dict, resolved: dict) -> None:
    """Copy one royalty-free track from assets/music into public/music; fail if enabled but missing."""
    import shutil

    m = deck.get("music") or {}
    if not m.get("enabled"):
        return
    files = sorted(p for p in MUSIC_DIR.glob("*") if p.is_file() and p.suffix.lower() in MUSIC_EXTS)
    if m.get("file"):
        chosen = MUSIC_DIR / Path(str(m["file"])).name
        if not chosen.is_file():
            raise DeckValidationError(f"music.file {m['file']!r} not found in assets/music")
    else:
        if not files:
            raise DeckValidationError("music.enabled is true but assets/music has no audio files (mp3/wav/m4a/ogg)")
        chosen = files[0]
    dest_dir = PUBLIC_DIR / "music"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{deck['slug']}{chosen.suffix.lower()}"
    shutil.copyfile(chosen, dest)
    resolved["music_file"] = f"music/{dest.name}"
    resolved["music_volume"] = float(m.get("volume", 0.12))
    print(f"[music] {chosen.name} -> {dest.name} (volume={resolved['music_volume']})")


class VoiceSynth:
    """Routes each speaker to its engine (Silero RU/EN or Kokoro EN). Engines load lazily; no fallback."""

    def __init__(self, rate: str) -> None:
        self.rate = rate
        self._silero: dict[str, object] = {}
        self._kokoro: KokoroEngine | None = None

    def _silero_model(self, lang: str):
        if lang not in self._silero:
            model = torch.package.PackageImporter(str(ensure_silero(lang))).load_pickle("tts_models", "model")
            model.to(torch.device("cpu"))
            self._silero[lang] = model
        return self._silero[lang]

    def synth(self, speaker: str, plain: str, ssml: str | None = None) -> np.ndarray:
        """Return mono float32 audio at SR for one utterance."""
        if speaker in EDGE_RU_VOICES:
            # Edge reads plain text; apply the same Latin->Cyrillic respelling as Silero so brand names are voiced.
            audio = synth_edge(speaker, normalize_ru_ssml(plain), SR, rate=self.rate)
            # Edge voices measured -10..-13 dB sibilance/speech (Silero -19..-20 dB). Gentle de-essing:
            # only peaks above the file's 75th percentile are reduced, by at most 4 dB; loudness unchanged.
            return deess(audio, SR, max_cut_db=4.0, over_db=3.0, ratio=2.0)
        engine = speaker_engine(speaker)
        if engine == "kokoro_v1":
            if self._kokoro is None:
                self._kokoro = KokoroEngine()
            return self._kokoro.synth(plain, speaker, self.rate, SR)
        model = self._silero_model("en" if engine == "silero_v3_en" else "ru")
        payload = ssml or f'<speak><prosody rate="{self.rate}">{escape(plain)}</prosody></speak>'
        if engine == "silero_v5_ru":
            # Silero v5 RU cannot voice Latin letters; respell them (tags and entities untouched).
            payload = normalize_ru_ssml(payload)
        raw = model.apply_tts(ssml_text=payload, speaker=speaker, sample_rate=SR).detach().cpu().numpy()
        return raw.astype(np.float32)


def synthesize_deck(deck: dict) -> dict:
    """Synthesize with the deck's online voice when Edge TTS is reachable; otherwise the offline fallback.

    The engine is chosen once for the WHOLE deck (never mixes voices). If Edge fails mid-deck, the deck is
    re-synthesized with the fallback. The voice actually used is recorded as resolved["voice_used"].
    """
    voice = deck.get("voice") or {}
    lang = deck_lang(deck)
    default_speaker = DEFAULT_SPEAKER_BY_LANG[lang]
    speaker_a = voice.get("speaker", default_speaker)
    speaker_b = voice.get("speaker_b") or DEFAULT_PARTNER.get(speaker_a, default_speaker)
    fallback = voice.get("fallback_speaker") or OFFLINE_FALLBACK_BY_LANG.get(lang, speaker_a)
    online = speaker_a in EDGE_RU_VOICES or speaker_b in EDGE_RU_VOICES
    if not online:
        return _synthesize_deck_with(deck, speaker_a, speaker_b, voice_used=speaker_a)
    if not edge_available():
        print(f"[voice] no connection to Edge TTS -> offline fallback '{fallback}' for the whole deck")
        return _synthesize_deck_with(deck, fallback, fallback, voice_used=fallback)
    try:
        return _synthesize_deck_with(deck, speaker_a, speaker_b, voice_used=speaker_a)
    except EdgeEngineError as exc:
        # Edge is intermittently unavailable: give the online voice one more full pass before falling back.
        print(f"[voice] Edge TTS failed ({exc}); pausing {EDGE_DECK_RETRY_PAUSE_SEC}s, then one more full pass")
        time.sleep(EDGE_DECK_RETRY_PAUSE_SEC)
    try:
        return _synthesize_deck_with(deck, speaker_a, speaker_b, voice_used=speaker_a)
    except EdgeEngineError as exc:
        print(f"[voice] Edge TTS failed again ({exc}) -> offline fallback '{fallback}' for the whole deck")
        return _synthesize_deck_with(deck, fallback, fallback, voice_used=fallback)


def _synthesize_deck_with(deck: dict, speaker_a: str, speaker_b: str, voice_used: str) -> dict:
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    RESOLVED_JSON.parent.mkdir(parents=True, exist_ok=True)

    voice = deck.get("voice") or {}
    mode = voice.get("mode", "single")
    rate = voice.get("rate", "95%")
    synther = VoiceSynth(rate)

    total_sec = 0
    resolved_slides = []
    total_slides = len(deck["slides"])
    gap = np.zeros(int(0.18 * SR), dtype=np.float32)

    for idx, slide in enumerate(deck["slides"], start=1):
        sid = slide["id"]
        plain = _plain_spoken_text(slide)

        if mode == "podcast":
            turns = slide.get("dialogue") or [
                {"speaker": "A" if i % 2 == 0 else "B", "text": s}
                for i, s in enumerate(_split_sentences(plain))
            ]
            chunks: list[np.ndarray] = []
            captions: list[dict] = []
            cur_t = 0.0
            for t_i, turn in enumerate(turns):
                sp_tag = "B" if str(turn.get("speaker", "A")).upper() == "B" else "A"
                sp_id = speaker_b if sp_tag == "B" else speaker_a
                txt = " ".join(str(turn.get("text", "")).split())
                if not txt:
                    continue
                clip = postprocess_voice(synther.synth(sp_id, txt))
                seg_dur = len(clip) / float(SR)
                if seg_dur < 0.4 and len(txt) > 30:
                    raise DeckValidationError(f"Slide {sid}: TTS produced {seg_dur:.2f}s for {len(txt)} chars ({sp_id})")
                captions.append({"start_sec": round(cur_t, 2), "end_sec": round(cur_t + seg_dur, 2), "text": txt, "speaker": sp_tag})
                chunks.append(clip)
                cur_t += seg_dur
                if t_i + 1 < len(turns):
                    chunks.append(gap)
                    cur_t += len(gap) / float(SR)
            audio = np.concatenate(chunks) if chunks else np.zeros(SR, dtype=np.float32)
            dur = len(audio) / float(SR)
            print(f"[tts] {sid} (podcast {speaker_a}+{speaker_b}): {dur:.2f}s -> slide {math.ceil(dur) + 1}s")
        else:
            audio = postprocess_voice(synther.synth(speaker_a, plain, slide.get("voice_ssml") or None))
            dur = len(audio) / float(SR)
            if dur < 1.0 and len(plain) > 40:
                raise DeckValidationError(
                    f"Slide {sid}: TTS produced {dur:.2f}s for {len(plain)} chars; text is not voiceable by {speaker_a}"
                )
            captions = _build_proportional_captions(plain, dur)
            print(f"[tts] {sid} ({speaker_a}): {dur:.2f}s -> slide {math.ceil(dur) + 1}s")

        pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()
        wav_name = f"{deck['slug']}_{sid}.wav"
        wav_path = VOICE_DIR / wav_name
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SR)
            wf.writeframes(pcm)

        scene_s = math.ceil(dur) + 1
        total_sec += scene_s

        item = dict(slide)
        item["duration_sec"] = scene_s
        item["num"] = f"{idx:02d} / {total_slides:02d}"
        item["voice_file"] = f"voice/{wav_name}"
        item["captions"] = captions
        resolved_slides.append(item)

    pad_name = f"{deck['slug']}_bg_pad.wav"
    pad_path = VOICE_DIR / pad_name
    with wave.open(str(pad_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(build_ambient_bed(total_sec + 2, SR))

    aspect = deck.get("aspect", "16:9")
    w, h = ASPECT_DIMS[aspect]
    resolved = dict(deck)
    resolved["aspect"] = aspect
    resolved["width"] = w
    resolved["height"] = h
    resolved["theme"] = deck.get("theme", "neon_cyber")
    resolved["burn_captions"] = deck.get("burn_captions", True)
    resolved["slides"] = resolved_slides
    resolved["total_seconds"] = total_sec
    resolved["ambient_file"] = f"voice/{pad_name}"
    resolved["voice_used"] = voice_used
    print(f"[voice] deck voiced by '{voice_used}'")
    credits = attach_stock_media(deck, resolved_slides)
    attach_music(deck, resolved)
    if credits:
        from stock_media import write_credits  # noqa: E402

        cpath = write_credits(deck["slug"], credits)
        print(f"[media] credits -> {cpath}")
    RESOLVED_JSON.write_text(json.dumps(resolved, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[deck] wrote {RESOLVED_JSON} (total={total_sec}s, {w}x{h}, theme={resolved['theme']})")
    write_subtitles(resolved)
    return resolved


def run_cmd(args: list[str]) -> None:
    print(f"[run] {' '.join(args)}")
    res = subprocess.run(args, cwd=str(ROOT), shell=True)
    if res.returncode != 0:
        raise RuntimeError(f"Command failed (exit={res.returncode}): {' '.join(args)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="DUP Presenter deck builder")
    parser.add_argument("deck", help="Path to deck JSON (e.g. decks/dup_labs.json)")
    parser.add_argument("--render", action="store_true", help="Also type-check, render MP4 & thumbnail")
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
        # Apply theme/aspect/caption switches from deck even on --skip-tts
        aspect = deck.get("aspect", resolved.get("aspect", "16:9"))
        resolved["aspect"] = aspect
        resolved["width"], resolved["height"] = ASPECT_DIMS[aspect]
        resolved["theme"] = deck.get("theme", resolved.get("theme", "neon_cyber"))
        resolved["burn_captions"] = deck.get("burn_captions", resolved.get("burn_captions", True))
        RESOLVED_JSON.write_text(json.dumps(resolved, ensure_ascii=False, indent=2), encoding="utf-8")
        write_subtitles(resolved)

    if args.render:
        out_mp4 = ROOT / "out" / f"{resolved['slug']}.mp4"
        out_thumb = ROOT / "out" / f"{resolved['slug']}_thumb.png"
        out_mp4.parent.mkdir(parents=True, exist_ok=True)
        run_cmd(["npx", "tsc", "--noEmit"])
        run_cmd([
            "npx", "remotion", "render", "DupPresenter", str(out_mp4),
            "--audio-codec=aac", "--audio-bitrate=320K",
        ])
        thumb_frame = min(45, max(0, resolved["total_seconds"] * resolved.get("fps", 30) - 1))
        run_cmd(["npx", "remotion", "still", "DupPresenter", str(out_thumb), f"--frame={thumb_frame}"])
        print(f"[OK] Rendered: {out_mp4} ({out_mp4.stat().st_size / 1_048_576:.2f} MB) + {out_thumb.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
