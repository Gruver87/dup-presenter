"""DUP Presenter — fail-closed deck validator, local Silero TTS builder (RU v5 / EN v3),
SRT/VTT caption generator, podcast 2-voice mixer, thumbnail & MP4 renderer.

Usage:
    python scripts/build_deck.py decks/dup_labs.json
    python scripts/build_deck.py decks/dup_labs.json --render
"""

from __future__ import annotations

import argparse
import copy
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

ALLOWED_TYPES = {
    "hero_3d",
    "code_split",
    "screen_split",
    "ui_recording",
    "arch_flow",
    "outro_3d",
    "timeline",
    "terminal",
    "kpi",
    "quote",
    "ledger_layers",
    "tx_journey",
    "mesh_network",
    "protocol_cosmos",
    "versus_split",
    "chart_story",
    "stat_burst",
    "broll_cinematic",
    "cinema_clip",
    "radar_arena",
    "radar_heart_3d",
}
ALLOWED_RADAR_ARENA_MODES = frozenset({"core_army", "live_candles", "trap_gauntlet", "integer_vault"})
ALLOWED_RADAR_HEART_SCENES = frozenset({
    "core_birth",
    "emblem_ingest",
    "emblem_mtf_score",
    "emblem_runners",
    "emblem_stop_cut",
    "emblem_traps",
    "emblem_integer",
    "emblem_recovery",
    "constellation_radar",
    "presenter_core",
})
QUOTE_MAX_CHARS = 220
# ui_recording clips come from scripts/record_ui.py and live in public/ui_recordings/ (gitignored).
UI_RECORDING_SRC_RE = re.compile(r"ui_recordings/[a-z0-9][a-z0-9_-]{0,60}\.mp4")

ALLOWED_CINEMA_VIDEO_EXTS = frozenset({".mp4", ".webm", ".mov"})
ALLOWED_CINEMA_IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".webp"})
ALLOWED_SFX_EXTS = frozenset({".wav", ".mp3", ".ogg", ".m4a", ".flac"})
ALLOWED_CINEMA_GRADES = frozenset({"none", "cinema_warm", "cinema_cold", "noir", "vivid"})
DEFAULT_RENDER_CRF = 20
DRAFT_RENDER_CRF = 26
DRAFT_RENDER_SCALE = 0.5
CRF_MIN = 14
CRF_MAX = 32


def _media_duration_sec(path: Path) -> float:
    """Duration of a media file via ffprobe. Fail-closed: a missing file or unreadable duration raises."""
    from audio_fx import find_ffprobe

    if not path.is_file():
        raise DeckValidationError(f"media file not found: {path}")
    cmd = [str(find_ffprobe()), "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        duration = float(proc.stdout.strip())
    except ValueError as exc:
        raise DeckValidationError(f"ffprobe could not read duration of {path}: {proc.stderr[-300:]}") from exc
    if proc.returncode != 0 or duration <= 0:
        raise DeckValidationError(f"ffprobe failed on {path} (exit {proc.returncode})")
    return duration


def _media_has_audio(path: Path) -> bool:
    """Check via ffprobe whether a media file contains at least one audio stream (fail-closed on unreadable file)."""
    from audio_fx import find_ffprobe

    if not path.is_file():
        raise DeckValidationError(f"media file not found: {path}")
    cmd = [
        str(find_ffprobe()),
        "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=codec_type",
        "-of", "default=nw=1:nk=1",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise DeckValidationError(f"ffprobe failed checking audio stream on {path} (exit {proc.returncode})")
    return bool(proc.stdout.strip())


def _is_number(val: object) -> bool:
    return isinstance(val, (int, float)) and not isinstance(val, bool)


def _validate_safe_public_rel(value: object, field: str, sid: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or ".." in value
        or ":" in value
        or value.startswith(("/", "\\"))
    ):
        raise DeckValidationError(f"Slide {sid}: {field} must be a safe relative path under public/")
    return value.strip()


def _validate_cinema_media_params(
    obj: dict,
    field_prefix: str,
    sid: str,
    *,
    kind: str,
    clip_dur: float | None,
    clip_path: Path | None,
    check_assets: bool,
) -> None:
    if "zoom" in obj and obj["zoom"] is not None:
        z = obj["zoom"]
        if not _is_number(z) or not (1.0 <= float(z) <= 1.5):
            raise DeckValidationError(f"Slide {sid}: {field_prefix}.zoom must be in [1.0, 1.5]")
    for pan_key in ("pan_x", "pan_y"):
        if pan_key in obj and obj[pan_key] is not None:
            pv = obj[pan_key]
            if not _is_number(pv) or not (-160.0 <= float(pv) <= 160.0):
                raise DeckValidationError(f"Slide {sid}: {field_prefix}.{pan_key} must be in [-160, 160]")

    if kind == "image":
        for bad_k in ("start_sec", "end_sec", "playback_rate"):
            if obj.get(bad_k) is not None:
                raise DeckValidationError(f"Slide {sid}: {field_prefix}.{bad_k} is only valid for video shots")
        av = obj.get("audio_volume")
        if av is not None and (not _is_number(av) or float(av) != 0.0):
            raise DeckValidationError(f"Slide {sid}: {field_prefix}.audio_volume cannot be non-zero for an image shot")
        return

    start_sec = 0.0
    if obj.get("start_sec") is not None:
        if not _is_number(obj["start_sec"]) or float(obj["start_sec"]) < 0.0:
            raise DeckValidationError(f"Slide {sid}: {field_prefix}.start_sec must be >= 0")
        start_sec = float(obj["start_sec"])
        if clip_dur is not None and start_sec >= clip_dur:
            raise DeckValidationError(
                f"Slide {sid}: {field_prefix}.start_sec ({start_sec}s) must be < clip duration ({clip_dur}s)"
            )
    if obj.get("end_sec") is not None:
        if not _is_number(obj["end_sec"]) or float(obj["end_sec"]) <= start_sec:
            raise DeckValidationError(f"Slide {sid}: {field_prefix}.end_sec must be > start_sec ({start_sec})")
        end_sec = float(obj["end_sec"])
        if clip_dur is not None and end_sec > clip_dur + 0.15:
            raise DeckValidationError(
                f"Slide {sid}: {field_prefix}.end_sec ({end_sec}s) exceeds clip duration ({clip_dur}s)"
            )
    if obj.get("playback_rate") is not None:
        pr = obj["playback_rate"]
        if not _is_number(pr) or not (0.25 <= float(pr) <= 2.0):
            raise DeckValidationError(f"Slide {sid}: {field_prefix}.playback_rate must be in [0.25, 2.0]")
    if obj.get("audio_volume") is not None:
        av = obj["audio_volume"]
        if not _is_number(av) or not (0.0 <= float(av) <= 1.0):
            raise DeckValidationError(f"Slide {sid}: {field_prefix}.audio_volume must be in [0.0, 1.0]")
        if float(av) > 0.0 and check_assets and clip_path is not None:
            if not _media_has_audio(clip_path):
                raise DeckValidationError(
                    f"Slide {sid}: {field_prefix}.audio_volume={av} requested, but clip has no audio stream: {clip_path}"
                )
from theme_catalog import THEME_IDS  # noqa: E402
from edge_engine import EDGE_RU_VOICES, EdgeEngineError, edge_allowed, edge_available, synth_edge_with_timings  # noqa: E402
from audio_fx import (  # noqa: E402
    WordTimingUnavailable,
    build_word_captions,
    transcribe_word_events,
    detect_speech_windows,
    ensure_sfx_files,
    normalize_mp4_loudness,
)
from sfx_library import LIBRARY_NAMES as SFX_LIBRARY_NAMES, SfxLibraryError, resolve_deck_sfx  # noqa: E402
from voice_clean import deess  # noqa: E402
from ru_speech import normalize_ru_ssml  # noqa: E402
from speech_phrasing import assemble, split_phrases  # noqa: E402
from pacing import (  # noqa: E402
    MAX_PASSES,
    PacingError,
    PacingSpec,
    format_rate,
    next_rate,
    parse_pacing,
    rate_pct,
    words_per_minute,
)
from tts_engines import (  # noqa: E402
    KOKORO_DEFAULT,
    KOKORO_PARTNERS,
    KOKORO_VOICE_IDS,
    SILERO_EN_VOICE_IDS,
    KokoroEngine,
    speaker_engine,
    speaker_lang,
)

ALLOWED_THEMES = set(THEME_IDS)
ALLOWED_TRANSITIONS = {"fade", "slide", "wipe", "none"}
# box: current boxed cue (default, unchanged output). karaoke: word-by-word highlight from word timings.
# bold: large text without a box, for short-form/vertical videos.
ALLOWED_CAPTION_STYLES = {"box", "karaoke", "bold"}
ALLOWED_MEDIA_ENGINES = frozenset({"offthread", "media"})
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


def validate_deck(deck: dict, *, check_assets: bool = True) -> None:
    """Fail-closed schema validation. Pure: never mutates `deck`.

    Writers (console save, asset binding, plan/idea generators) validate then persist the deck, so this
    function must not add derived fields (kind, clip_duration_sec) that would leak into source decks.
    Use `prepare_deck` for the build pipeline, which needs those annotations in its resolved copy.
    """
    prepare_deck(deck, check_assets=check_assets)


def prepare_deck(deck: dict, *, check_assets: bool = True) -> dict:
    """Validate and annotate a COPY of the deck (inferred shot kind, probed clip durations).

    The input is never modified. The returned copy is what the build pipeline renders from; the source
    file under decks/ stays exactly as the author (or console) saved it.
    """
    work = copy.deepcopy(deck)
    _validate_and_annotate(work, check_assets=check_assets)
    return work


def _validate_and_annotate(deck: dict, *, check_assets: bool = True) -> None:
    """Fail-closed schema validation that also annotates `deck` in place. Internal: use prepare_deck/validate_deck."""
    if not isinstance(deck.get("slug"), str) or not deck["slug"].strip():
        raise DeckValidationError("deck.slug must be a non-empty string")
    slides = deck.get("slides")
    if not isinstance(slides, list) or not slides:
        raise DeckValidationError("deck.slides must be a non-empty list")

    theme = deck.get("theme", "neon_cyber")
    if theme not in ALLOWED_THEMES:
        raise DeckValidationError(f"Unsupported theme {theme!r}; allowed: {sorted(ALLOWED_THEMES)}")

    caption_style = deck.get("caption_style", "box")
    if not isinstance(caption_style, str) or caption_style not in ALLOWED_CAPTION_STYLES:
        raise DeckValidationError(
            f"Unsupported caption_style {caption_style!r}; allowed: {sorted(ALLOWED_CAPTION_STYLES)}"
        )

    aspect = deck.get("aspect", "16:9")
    if aspect not in ASPECT_DIMS:
        raise DeckValidationError(f"Unsupported aspect {aspect!r}; allowed: {sorted(ASPECT_DIMS)}")

    try:
        parse_pacing(deck.get("pacing"))
    except PacingError as exc:
        raise DeckValidationError(f"pacing: {exc}") from exc

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
    if "duck_db" in music:
        duck_db = float(music["duck_db"])
        if not -24.0 <= duck_db <= 0.0:
            raise DeckValidationError(f"music.duck_db must be in [-24, 0], got {duck_db}")

    if "director_preset" in deck and deck["director_preset"] is not None:
        from director_presets import DIRECTOR_PRESETS

        dp_id = str(deck["director_preset"]).strip()
        if dp_id not in DIRECTOR_PRESETS:
            raise DeckValidationError(
                f"Unsupported director_preset {dp_id!r}; allowed: {sorted(DIRECTOR_PRESETS)}"
            )

    transition = deck.get("transition") or {}
    tr_style = str(transition.get("style", "fade"))
    if tr_style not in ALLOWED_TRANSITIONS:
        raise DeckValidationError(f"Unsupported transition.style {tr_style!r}; allowed: {sorted(ALLOWED_TRANSITIONS)}")
    tr_frames = int(transition.get("frames", 12))
    if tr_style != "none" and not (6 <= tr_frames <= 24):
        raise DeckValidationError(f"transition.frames must be in [6, 24], got {tr_frames}")

    sfx = deck.get("sfx") or {}
    if "volume" in sfx:
        sv = float(sfx["volume"])
        if not 0.0 <= sv <= 0.5:
            raise DeckValidationError(f"sfx.volume must be in [0, 0.5], got {sv}")

    # Video engine for cinema clips. "offthread" (default, unchanged) or "media" (@remotion/media, opt-in).
    media_engine = deck.get("media_engine")
    if media_engine is not None and media_engine not in ALLOWED_MEDIA_ENGINES:
        raise DeckValidationError(f"media_engine must be one of {sorted(ALLOWED_MEDIA_ENGINES)}, got {media_engine!r}")

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
        if slide.get("min_duration_sec") is not None:
            md = slide["min_duration_sec"]
            if not _is_number(md) or not (1 <= float(md) <= 120):
                raise DeckValidationError(f"Slide {sid}: min_duration_sec must be a number in 1..120")
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
                if check_assets and not full.is_file():
                    raise DeckValidationError(f"Slide {sid}: missing screen file {full}")
        if stype == "ui_recording":
            rec = slide.get("recording")
            if not isinstance(rec, dict):
                raise DeckValidationError(f"Slide {sid}: ui_recording requires a recording object")
            src = rec.get("src")
            # Strict shape: only ui_recordings/<slug>.mp4 under public/ (no traversal, no absolute paths).
            if not isinstance(src, str) or not UI_RECORDING_SRC_RE.fullmatch(src):
                raise DeckValidationError(
                    f"Slide {sid}: recording.src must match ui_recordings/<slug>.mp4, got {src!r}"
                )
            if "caption" in rec and not isinstance(rec["caption"], str):
                raise DeckValidationError(f"Slide {sid}: recording.caption must be a string")
            if check_assets and not (PUBLIC_DIR / src).is_file():
                raise DeckValidationError(f"Slide {sid}: missing recording file public/{src}")
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
        if stype == "quote":
            quote = str(slide.get("title", "")).strip()
            if not quote or len(quote) > QUOTE_MAX_CHARS:
                raise DeckValidationError(f"Slide {sid}: quote title must be 1..{QUOTE_MAX_CHARS} chars")
            if "subtitle" in slide and not isinstance(slide["subtitle"], str):
                raise DeckValidationError(f"Slide {sid}: quote subtitle (attribution) must be a string")
        if stype == "ledger_layers":
            layers = slide.get("layers")
            if not isinstance(layers, list) or not (3 <= len(layers) <= 6):
                raise DeckValidationError(f"Slide {sid}: ledger_layers requires 3..6 layer objects")
            layer_ids: set[str] = set()
            for l_idx, layer in enumerate(layers):
                if not isinstance(layer, dict):
                    raise DeckValidationError(f"Slide {sid}: layer #{l_idx} must be an object")
                lid = layer.get("id")
                if not isinstance(lid, str) or not lid.strip() or lid in layer_ids:
                    raise DeckValidationError(f"Slide {sid}: layer #{l_idx} has missing or duplicate id {lid!r}")
                layer_ids.add(lid)
                for req in ("name", "tech", "desc", "guarantee"):
                    if not isinstance(layer.get(req), str) or not layer[req].strip():
                        raise DeckValidationError(f"Slide {sid}: layer {lid!r} missing non-empty string {req!r}")
        if stype == "tx_journey":
            journey = slide.get("journey")
            if not isinstance(journey, dict):
                raise DeckValidationError(f"Slide {sid}: tx_journey requires a journey object")
            for req in ("tx_label", "amount_label", "signature_label"):
                if not isinstance(journey.get(req), str) or not journey[req].strip():
                    raise DeckValidationError(f"Slide {sid}: journey missing non-empty string {req!r}")
            blocks = journey.get("blocks")
            if not isinstance(blocks, list) or not (3 <= len(blocks) <= 5):
                raise DeckValidationError(f"Slide {sid}: journey.blocks must have 3..5 items")
            for b_idx, blk in enumerate(blocks):
                if not isinstance(blk, dict):
                    raise DeckValidationError(f"Slide {sid}: journey.blocks[{b_idx}] must be an object")
                for req in ("height", "hash", "tx_count"):
                    if not isinstance(blk.get(req), str) or not blk[req].strip():
                        raise DeckValidationError(f"Slide {sid}: journey.blocks[{b_idx}] missing {req!r}")
            j_steps = journey.get("steps")
            if not isinstance(j_steps, list) or not (3 <= len(j_steps) <= 5):
                raise DeckValidationError(f"Slide {sid}: journey.steps must have 3..5 items")
            for s_idx, st in enumerate(j_steps):
                if not isinstance(st, dict):
                    raise DeckValidationError(f"Slide {sid}: journey.steps[{s_idx}] must be an object")
                for req in ("title", "badge", "detail"):
                    if not isinstance(st.get(req), str) or not st[req].strip():
                        raise DeckValidationError(f"Slide {sid}: journey.steps[{s_idx}] missing {req!r}")
            leaves = journey.get("merkle_leaves")
            if leaves is not None:
                if not isinstance(leaves, list) or not (2 <= len(leaves) <= 4) or not all(
                    isinstance(x, str) and x.strip() for x in leaves
                ):
                    raise DeckValidationError(f"Slide {sid}: journey.merkle_leaves must be 2..4 non-empty strings")
        if stype == "mesh_network":
            mesh = slide.get("mesh")
            if not isinstance(mesh, dict):
                raise DeckValidationError(f"Slide {sid}: mesh_network requires a mesh object")
            for req in ("protocol_label", "chain_id", "probe_label"):
                if not isinstance(mesh.get(req), str) or not mesh[req].strip():
                    raise DeckValidationError(f"Slide {sid}: mesh missing non-empty string {req!r}")
            m_nodes = mesh.get("nodes")
            if not isinstance(m_nodes, list) or not (3 <= len(m_nodes) <= 4):
                raise DeckValidationError(f"Slide {sid}: mesh.nodes must have 3..4 items")
            m_ids: set[str] = set()
            for n_idx, node in enumerate(m_nodes):
                if not isinstance(node, dict):
                    raise DeckValidationError(f"Slide {sid}: mesh.nodes[{n_idx}] must be an object")
                nid = node.get("id")
                if not isinstance(nid, str) or not nid.strip() or nid in m_ids:
                    raise DeckValidationError(f"Slide {sid}: mesh.nodes[{n_idx}] missing or duplicate id {nid!r}")
                m_ids.add(nid)
                for req in ("role", "endpoint", "status"):
                    if not isinstance(node.get(req), str) or not node[req].strip():
                        raise DeckValidationError(f"Slide {sid}: mesh node {nid!r} missing {req!r}")
            rec_steps = mesh.get("recovery_steps")
            if not isinstance(rec_steps, list) or not (2 <= len(rec_steps) <= 3):
                raise DeckValidationError(f"Slide {sid}: mesh.recovery_steps must have 2..3 items")
            for r_idx, rs in enumerate(rec_steps):
                if not isinstance(rs, dict) or not str(rs.get("title", "")).strip() or not str(rs.get("desc", "")).strip():
                    raise DeckValidationError(f"Slide {sid}: mesh.recovery_steps[{r_idx}] needs title and desc")
        if stype == "protocol_cosmos":
            cosmos = slide.get("cosmos")
            if not isinstance(cosmos, dict):
                raise DeckValidationError(f"Slide {sid}: protocol_cosmos requires a cosmos object")
            for req in ("core_title", "core_subtitle"):
                if not isinstance(cosmos.get(req), str) or not cosmos[req].strip():
                    raise DeckValidationError(f"Slide {sid}: cosmos missing non-empty string {req!r}")
            c_badges = cosmos.get("core_badges")
            if not isinstance(c_badges, list) or not (2 <= len(c_badges) <= 4) or not all(
                isinstance(b, str) and b.strip() for b in c_badges
            ):
                raise DeckValidationError(f"Slide {sid}: cosmos.core_badges must be 2..4 non-empty strings")
            stations = cosmos.get("stations")
            if not isinstance(stations, list) or len(stations) != 6:
                raise DeckValidationError(f"Slide {sid}: cosmos.stations must have exactly 6 items (3 left, 3 right)")
            left_n = sum(1 for st in stations if isinstance(st, dict) and st.get("side") == "left")
            right_n = sum(1 for st in stations if isinstance(st, dict) and st.get("side") == "right")
            if left_n != 3 or right_n != 3:
                raise DeckValidationError(f"Slide {sid}: cosmos.stations must have 3 'left' and 3 'right' items")
            st_ids: set[str] = set()
            for st_idx, st in enumerate(stations):
                if not isinstance(st, dict):
                    raise DeckValidationError(f"Slide {sid}: cosmos.stations[{st_idx}] must be an object")
                stid = st.get("id")
                if not isinstance(stid, str) or not stid.strip() or stid in st_ids:
                    raise DeckValidationError(f"Slide {sid}: cosmos station #{st_idx} missing or duplicate id {stid!r}")
                st_ids.add(stid)
                for req in ("badge", "title", "detail", "metric", "color"):
                    if not isinstance(st.get(req), str) or not st[req].strip():
                        raise DeckValidationError(f"Slide {sid}: cosmos station {stid!r} missing {req!r}")
        if stype == "versus_split":
            vs = slide.get("versus")
            if not isinstance(vs, dict):
                raise DeckValidationError(f"Slide {sid}: versus_split requires a versus object")
            for side_key in ("left", "right"):
                side = vs.get(side_key)
                if not isinstance(side, dict):
                    raise DeckValidationError(f"Slide {sid}: versus.{side_key} must be an object")
                if not isinstance(side.get("label"), str) or not side["label"].strip():
                    raise DeckValidationError(f"Slide {sid}: versus.{side_key}.label must be a non-empty string")
                pts = side.get("points")
                if not isinstance(pts, list) or not (2 <= len(pts) <= 5) or not all(
                    isinstance(p, str) and p.strip() for p in pts
                ):
                    raise DeckValidationError(f"Slide {sid}: versus.{side_key}.points must be 2..5 non-empty strings")
        if stype == "chart_story":
            ch = slide.get("chart")
            if not isinstance(ch, dict):
                raise DeckValidationError(f"Slide {sid}: chart_story requires a chart object")
            if ch.get("kind") not in {"bar", "line", "donut"}:
                raise DeckValidationError(f"Slide {sid}: chart.kind must be 'bar', 'line', or 'donut'")
            series = ch.get("series")
            if not isinstance(series, list) or not (2 <= len(series) <= 8):
                raise DeckValidationError(f"Slide {sid}: chart.series must contain 2..8 items")
            for c_idx, pt in enumerate(series):
                if not isinstance(pt, dict) or not isinstance(pt.get("label"), str) or not pt["label"].strip():
                    raise DeckValidationError(f"Slide {sid}: chart.series[{c_idx}] requires a non-empty label")
                val = pt.get("value")
                if isinstance(val, bool) or not isinstance(val, (int, float)) or val < 0:
                    raise DeckValidationError(f"Slide {sid}: chart.series[{c_idx}].value must be a non-negative number")
        if stype == "stat_burst":
            sb = slide.get("stat_burst")
            if not isinstance(sb, dict):
                raise DeckValidationError(f"Slide {sid}: stat_burst requires a stat_burst object")
            if not isinstance(sb.get("headline"), str) or not (1 <= len(sb["headline"].strip()) <= 24):
                raise DeckValidationError(f"Slide {sid}: stat_burst.headline must be 1..24 chars")
            if not isinstance(sb.get("caption"), str) or not sb["caption"].strip():
                raise DeckValidationError(f"Slide {sid}: stat_burst.caption must be a non-empty string")
            chips = sb.get("chips")
            if chips is not None:
                if not isinstance(chips, list) or len(chips) > 3:
                    raise DeckValidationError(f"Slide {sid}: stat_burst.chips must have at most 3 items")
        if stype == "broll_cinematic":
            br = slide.get("broll")
            if not isinstance(br, dict):
                raise DeckValidationError(f"Slide {sid}: broll_cinematic requires a broll object")
            img = br.get("image")
            if img is not None:
                if not isinstance(img, str) or not img.strip() or ".." in img:
                    raise DeckValidationError(f"Slide {sid}: broll.image must be a safe relative path")
            callouts = br.get("callouts")
            if callouts is not None:
                if not isinstance(callouts, list) or len(callouts) > 3 or not all(
                    isinstance(c, str) and c.strip() for c in callouts
                ):
                    raise DeckValidationError(f"Slide {sid}: broll.callouts must be 0..3 non-empty strings")
        if stype == "cinema_clip":
            cc = slide.get("cinema")
            if not isinstance(cc, dict):
                raise DeckValidationError(f"Slide {sid}: cinema_clip requires a cinema object")
            grade = cc.get("grade")
            if grade is not None and grade not in ALLOWED_CINEMA_GRADES:
                raise DeckValidationError(
                    f"Slide {sid}: cinema.grade {grade!r} unsupported; allowed: {sorted(ALLOWED_CINEMA_GRADES)}"
                )
            if cc.get("crossfade_frames") is not None:
                cf = cc["crossfade_frames"]
                if isinstance(cf, bool) or not isinstance(cf, int) or not (0 <= cf <= 30):
                    raise DeckValidationError(f"Slide {sid}: cinema.crossfade_frames must be an int in [0, 30]")
            if cc.get("letterbox") is not None and not isinstance(cc["letterbox"], bool):
                raise DeckValidationError(f"Slide {sid}: cinema.letterbox must be a boolean")

            src = cc.get("src")
            shots = cc.get("shots")
            if src is not None and shots is not None:
                raise DeckValidationError(f"Slide {sid}: cinema_clip cannot set both cinema.src and cinema.shots")

            if shots is not None:
                if not isinstance(shots, list) or not (1 <= len(shots) <= 8):
                    raise DeckValidationError(f"Slide {sid}: cinema.shots must contain 1..8 shot objects")
                for sh_idx, sh in enumerate(shots):
                    if not isinstance(sh, dict):
                        raise DeckValidationError(f"Slide {sid}: cinema.shots[{sh_idx}] must be an object")
                    sh_src = _validate_safe_public_rel(sh.get("src"), f"cinema.shots[{sh_idx}].src", sid)
                    ext = Path(sh_src).suffix.lower()
                    if ext in ALLOWED_CINEMA_VIDEO_EXTS:
                        inferred_kind = "video"
                    elif ext in ALLOWED_CINEMA_IMAGE_EXTS:
                        inferred_kind = "image"
                    else:
                        raise DeckValidationError(
                            f"Slide {sid}: cinema.shots[{sh_idx}].src unsupported extension {ext!r}"
                        )
                    if sh.get("kind") is not None and sh["kind"] != inferred_kind:
                        raise DeckValidationError(
                            f"Slide {sid}: cinema.shots[{sh_idx}].kind={sh['kind']!r} conflicts with extension {ext!r}"
                        )
                    sh["kind"] = inferred_kind
                    if sh.get("duration_sec") is not None:
                        if not _is_number(sh["duration_sec"]) or float(sh["duration_sec"]) < 0.5:
                            raise DeckValidationError(f"Slide {sid}: cinema.shots[{sh_idx}].duration_sec must be >= 0.5")
                    clip_path = PUBLIC_DIR / sh_src
                    clip_dur: float | None = None
                    if check_assets:
                        if not clip_path.is_file():
                            raise DeckValidationError(f"Slide {sid}: cinema.shots[{sh_idx}].src file not found: {clip_path}")
                        if inferred_kind == "video":
                            clip_dur = round(_media_duration_sec(clip_path), 2)
                            sh["clip_duration_sec"] = clip_dur
                    _validate_cinema_media_params(
                        sh,
                        f"cinema.shots[{sh_idx}]",
                        sid,
                        kind=inferred_kind,
                        clip_dur=clip_dur,
                        clip_path=clip_path if check_assets else None,
                        check_assets=check_assets,
                    )
            elif src is not None:
                clean_src = _validate_safe_public_rel(src, "cinema.src", sid)
                ext = Path(clean_src).suffix.lower()
                if ext in ALLOWED_CINEMA_IMAGE_EXTS:
                    inferred_kind = "image"
                elif ext in ALLOWED_CINEMA_VIDEO_EXTS:
                    inferred_kind = "video"
                else:
                    raise DeckValidationError(f"Slide {sid}: cinema.src unsupported extension {ext!r}")
                clip_path = PUBLIC_DIR / clean_src
                clip_dur = None
                if check_assets:
                    if not clip_path.is_file():
                        raise DeckValidationError(f"Slide {sid}: cinema.src file not found: {clip_path}")
                    if inferred_kind == "video":
                        clip_dur = round(_media_duration_sec(clip_path), 2)
                        cc["clip_duration_sec"] = clip_dur
                _validate_cinema_media_params(
                    cc,
                    "cinema",
                    sid,
                    kind=inferred_kind,
                    clip_dur=clip_dur,
                    clip_path=clip_path if check_assets else None,
                    check_assets=check_assets,
                )
            elif not slide.get("background_query"):
                raise DeckValidationError(f"Slide {sid}: cinema_clip requires cinema.src or background_query (or cinema.shots)")

        if stype == "radar_arena":
            ar = slide.get("arena")
            if not isinstance(ar, dict):
                raise DeckValidationError(f"Slide {sid}: radar_arena requires an arena object")
            mode = ar.get("mode")
            if mode not in ALLOWED_RADAR_ARENA_MODES:
                raise DeckValidationError(
                    f"Slide {sid}: arena.mode must be one of {sorted(ALLOWED_RADAR_ARENA_MODES)}"
                )
            for opt_key in ("badge", "headline", "subline", "footer_note"):
                val = ar.get(opt_key)
                if val is not None and (not isinstance(val, str) or not val.strip()):
                    raise DeckValidationError(f"Slide {sid}: arena.{opt_key} must be a non-empty string")

        if stype == "radar_heart_3d":
            h3 = slide.get("heart3d")
            if not isinstance(h3, dict):
                raise DeckValidationError(f"Slide {sid}: radar_heart_3d requires a heart3d object")
            scene = h3.get("scene")
            if scene not in ALLOWED_RADAR_HEART_SCENES:
                raise DeckValidationError(
                    f"Slide {sid}: heart3d.scene must be one of {sorted(ALLOWED_RADAR_HEART_SCENES)}"
                )
            for opt_key in ("emblem_label", "headline", "repo_url", "repo_caption", "disclaimer", "bg_tint", "world_title"):
                val = h3.get(opt_key)
                if val is not None and (not isinstance(val, str) or not val.strip()):
                    raise DeckValidationError(f"Slide {sid}: heart3d.{opt_key} must be a non-empty string")
            bg_video = h3.get("bg_video")
            if bg_video is not None:
                if not isinstance(bg_video, str) or not bg_video.strip():
                    raise DeckValidationError(f"Slide {sid}: heart3d.bg_video must be a non-empty string")
                if bg_video.startswith("/") or bg_video.startswith("\\") or ".." in Path(bg_video).parts:
                    raise DeckValidationError(f"Slide {sid}: heart3d.bg_video must be a safe relative path under public/")
                if check_assets and not (PUBLIC_DIR / bg_video).is_file():
                    raise DeckValidationError(f"Slide {sid}: heart3d.bg_video asset not found: {PUBLIC_DIR / bg_video}")
            bg_opacity = h3.get("bg_opacity")
            if bg_opacity is not None:
                if not isinstance(bg_opacity, (int, float)) or isinstance(bg_opacity, bool) or not (0.1 <= float(bg_opacity) <= 1.0):
                    raise DeckValidationError(f"Slide {sid}: heart3d.bg_opacity must be a number between 0.1 and 1.0")
            chips = h3.get("chips")
            if chips is not None:
                if not isinstance(chips, list) or len(chips) > 4 or not all(isinstance(c, str) and c.strip() for c in chips):
                    raise DeckValidationError(f"Slide {sid}: heart3d.chips must be 0..4 non-empty strings")

        if slide.get("sfx") is not None:
            slide_sfx = slide["sfx"]
            if not isinstance(slide_sfx, list) or len(slide_sfx) > 8:
                raise DeckValidationError(f"Slide {sid}: sfx must be a list of 0..8 cues")
            for q_idx, cue in enumerate(slide_sfx):
                if not isinstance(cue, dict):
                    raise DeckValidationError(f"Slide {sid}: sfx[{q_idx}] must be an object")
                has_src = cue.get("src") is not None
                has_name = cue.get("name") is not None
                if has_src == has_name:
                    raise DeckValidationError(f"Slide {sid}: sfx[{q_idx}] needs exactly one of src (file) or name (library)")
                if has_name:
                    if cue["name"] not in SFX_LIBRARY_NAMES:
                        raise DeckValidationError(
                            f"Slide {sid}: sfx[{q_idx}].name {cue['name']!r} is not in the SFX library: {sorted(SFX_LIBRARY_NAMES)}"
                        )
                    # Library files are generated by resolve_deck_sfx() before rendering (not checked here).
                    cue_src = f"sfx/library/{cue['name']}.wav"
                else:
                    cue_src = _validate_safe_public_rel(cue.get("src"), f"sfx[{q_idx}].src", sid)
                ext = Path(cue_src).suffix.lower()
                if ext not in ALLOWED_SFX_EXTS:
                    raise DeckValidationError(
                        f"Slide {sid}: sfx[{q_idx}].src unsupported audio extension {ext!r}; allowed: {sorted(ALLOWED_SFX_EXTS)}"
                    )
                if check_assets and has_src:
                    cue_path = PUBLIC_DIR / cue_src
                    if not cue_path.is_file():
                        raise DeckValidationError(f"Slide {sid}: sfx[{q_idx}].src file not found: {cue_path}")
                at_sec = cue.get("at_sec")
                if not _is_number(at_sec) or float(at_sec) < 0.0:
                    raise DeckValidationError(f"Slide {sid}: sfx[{q_idx}].at_sec must be a number >= 0")
                if cue.get("volume") is not None:
                    cv = cue["volume"]
                    if not _is_number(cv) or not (0.0 < float(cv) <= 1.0):
                        raise DeckValidationError(f"Slide {sid}: sfx[{q_idx}].volume must be in (0, 1.0]")
                if cue.get("duration_sec") is not None:
                    cd = cue["duration_sec"]
                    if not _is_number(cd) or float(cd) <= 0.0:
                        raise DeckValidationError(f"Slide {sid}: sfx[{q_idx}].duration_sec must be > 0")
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
    running_offset = 0.0
    for slide in resolved["slides"]:
        offset = float(slide.get("start_sec", running_offset))
        for cue in slide.get("captions") or []:
            start = offset + float(cue["start_sec"])
            end = offset + float(cue["end_sec"])
            prefix = f"[{cue['speaker']}] " if cue.get("speaker") else ""
            text = prefix + cue["text"]
            srt_lines += [str(idx), f"{_fmt_ts(start, ',')} --> {_fmt_ts(end, ',')}", text, ""]
            vtt_lines += [f"{_fmt_ts(start, '.')} --> {_fmt_ts(end, '.')}", text, ""]
            idx += 1
        running_offset = offset + float(slide["duration_sec"])

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
            # torch is imported lazily: only the offline Silero fallback needs it, and importing it at
            # module level made every deck/MCP/gate test (and CI without torch) fail at import time.
            import torch

            model = torch.package.PackageImporter(str(ensure_silero(lang))).load_pickle("tts_models", "model")
            model.to(torch.device("cpu"))
            self._silero[lang] = model
        return self._silero[lang]

    def synth_with_timings(
        self, speaker: str, plain: str, ssml: str | None = None
    ) -> tuple[np.ndarray, list[dict]]:
        """Return (mono float32 audio at SR, word timing events) for one utterance. Events are empty when the engine gives none."""
        if speaker in EDGE_RU_VOICES:
            # Edge reads plain text; apply the same Latin->Cyrillic respelling as Silero so brand names are voiced.
            audio, boundaries = synth_edge_with_timings(speaker, normalize_ru_ssml(plain), SR, rate=self.rate)
            # Edge voices measured -10..-13 dB sibilance/speech (Silero -19..-20 dB). Gentle de-essing:
            # only peaks above the file's 75th percentile are reduced, by at most 4 dB; loudness unchanged.
            return deess(audio, SR, max_cut_db=4.0, over_db=3.0, ratio=2.0), boundaries
        engine = speaker_engine(speaker)
        if engine == "kokoro_v1":
            if self._kokoro is None:
                self._kokoro = KokoroEngine()
            return self._kokoro.synth(plain, speaker, self.rate, SR), []
        model = self._silero_model("en" if engine == "silero_v3_en" else "ru")
        payload = ssml or f'<speak><prosody rate="{self.rate}">{escape(plain)}</prosody></speak>'
        if engine == "silero_v5_ru":
            # Silero v5 RU cannot voice Latin letters; respell them (tags and entities untouched).
            payload = normalize_ru_ssml(payload)
        raw = model.apply_tts(ssml_text=payload, speaker=speaker, sample_rate=SR).detach().cpu().numpy()
        return raw.astype(np.float32), []

    def synth(self, speaker: str, plain: str, ssml: str | None = None) -> np.ndarray:
        """Return mono float32 audio at SR for one utterance."""
        audio, _ = self.synth_with_timings(speaker, plain, ssml)
        return audio


def _paced_synth(
    synther: "VoiceSynth",
    speaker: str,
    plain: str,
    slide: dict,
    spec: "PacingSpec | None",
    base_rate: str,
    sid: str,
) -> tuple[np.ndarray, list[dict], str, float | None]:
    """Synthesize one single-speaker slide; with a pacing spec, correct the rate in bounded passes (item 5).

    Returns (audio, bounds, rate_used, measured_wpm). Slides with voice_ssml keep their own prosody rate.
    The synther rate is restored to the deck base rate on return, so other slides are unaffected.
    """
    synther.rate = base_rate
    if slide.get("phrasing"):
        # Explicit phrase-level synthesis with measured silences (see scripts/speech_phrasing.py).
        # SSML <break> is not used here: the measured Silero effect on pauses was negligible.
        phrases = split_phrases(plain)
        raw = assemble(phrases, lambda t: synther.synth(speaker, t, None), SR)
        print(f"[phrasing] {sid}: {len(phrases)} phrases, {len(raw) / float(SR):.2f}s")
        return raw, [], base_rate, None
    raw, bounds = synther.synth_with_timings(speaker, plain, slide.get("voice_ssml") or None)
    if spec is None:
        return raw, bounds, base_rate, None
    if slide.get("voice_ssml"):
        print(f"[pacing] {sid}: voice_ssml fixes its own prosody rate; automatic pacing not applied")
        return raw, bounds, base_rate, None
    cur = rate_pct(base_rate)
    wpm = words_per_minute(plain, len(raw) / float(SR))
    print(f"[pacing] {sid}: {wpm:.0f} wpm at rate {format_rate(cur)} (target {spec.target_wpm:g})")
    for pass_no in range(1, MAX_PASSES + 1):
        new_pct = next_rate(cur, wpm, spec)
        if new_pct is None:
            break
        synther.rate = format_rate(new_pct)
        raw, bounds = synther.synth_with_timings(speaker, plain)
        cur = float(round(new_pct))
        wpm = words_per_minute(plain, len(raw) / float(SR))
        print(f"[pacing] {sid}: pass {pass_no} -> rate {format_rate(cur)}, {wpm:.0f} wpm")
    synther.rate = base_rate
    return raw, bounds, format_rate(cur), wpm


def _word_events_for_clip(audio: np.ndarray, lang: str, tag: str, engine_events: list[dict]) -> list[dict]:
    """Word timing events for one voiced clip.

    Engine events win (Edge WordBoundary). English clips without engine events get local ASR word timestamps
    (faster-whisper) on the exact audio written to disk. If ASR is unavailable, returns [] and the caption
    builder uses the length-based estimate; the build log says which source was used.
    """
    if engine_events:
        return engine_events
    if lang != "en":
        return []
    try:
        events = transcribe_word_events(audio, SR)
    except WordTimingUnavailable as exc:
        print(f"[captions] {tag}: ASR word timing unavailable ({exc}); estimated timing used")
        return []
    print(f"[captions] {tag}: ASR word timing, {len(events)} words")
    return events


def skip_tts_source_error(resolved: dict, raw_deck_sha: str) -> str | None:
    """Return why --skip-tts must not reuse the shared deck_resolved.json, or None when it may.

    --skip-tts reuses one shared file for every deck, so its timeline, voice and text can belong to another
    deck (a Russian timeline was once rendered under the English slug). It is allowed only when that file
    records the fingerprint of this exact deck, which a full synthesis run writes.
    """
    recorded = resolved.get("source_deck_sha256")
    if not recorded:
        return ("deck_resolved.json does not record its source deck (source_deck_sha256 missing); "
                "run without --skip-tts so the narration is synthesized for this deck")
    if recorded != raw_deck_sha:
        return ("deck_resolved.json was synthesized from a different deck; "
                "run without --skip-tts so the narration is synthesized for this deck")
    return None


def bind_resolved_to_deck(resolved: dict, raw_deck_sha: str, *, only_slide: str) -> None:
    """Record (or clear) the deck fingerprint on a timeline before it is written to the shared file.

    A full-deck timeline records raw_deck_sha. A --only-slide timeline covers one slide, so it records nothing
    and cannot later be reused as the full deck by --skip-tts.
    """
    if only_slide.strip():
        resolved.pop("source_deck_sha256", None)
    else:
        resolved["source_deck_sha256"] = raw_deck_sha


def synthesize_deck(deck: dict, offline_only: bool = False) -> dict:
    """Synthesize with the deck's online voice when Edge TTS is reachable; otherwise the offline fallback.

    The engine is chosen once for the WHOLE deck (never mixes voices). If Edge fails mid-deck, the deck is
    re-synthesized with the fallback. When offline_only=True, no network calls are made (Privacy Lock).
    The voice actually used is recorded as resolved["voice_used"].
    """
    voice = deck.get("voice") or {}
    lang = deck_lang(deck)
    default_speaker = DEFAULT_SPEAKER_BY_LANG[lang]
    speaker_a = voice.get("speaker", default_speaker)
    speaker_b = voice.get("speaker_b") or DEFAULT_PARTNER.get(speaker_a, default_speaker)
    fallback = voice.get("fallback_speaker") or OFFLINE_FALLBACK_BY_LANG.get(lang, speaker_a)
    online = speaker_a in EDGE_RU_VOICES or speaker_b in EDGE_RU_VOICES
    if offline_only:
        if (deck.get("background") or {}).get("enabled"):
            raise DeckValidationError("--offline-only forbids online stock background downloads (background.enabled=true)")
        if online:
            print(f"[offline-only] skipping online Edge TTS -> local offline voice '{fallback}'")
            return _synthesize_deck_with(deck, fallback, fallback, voice_used=fallback)
        return _synthesize_deck_with(deck, speaker_a, speaker_b, voice_used=speaker_a)
    if not online:
        return _synthesize_deck_with(deck, speaker_a, speaker_b, voice_used=speaker_a)
    if not edge_allowed():
        print(f"[voice] no egress grant for Edge TTS (internet off or not approved) -> offline fallback '{fallback}' for the whole deck")
        return _synthesize_deck_with(deck, fallback, fallback, voice_used=fallback)
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
    lang = deck_lang(deck)  # the fallback voice always shares the deck language

    voice = deck.get("voice") or {}
    mode = voice.get("mode", "single")
    rate = voice.get("rate", "95%")
    try:
        pacing_spec = parse_pacing(deck.get("pacing"))
        if pacing_spec is not None:
            rate_pct(rate)  # pacing starts from a percent base rate such as '86%'
    except PacingError as exc:
        raise DeckValidationError(f"pacing: {exc}") from exc
    if pacing_spec is not None and mode == "podcast":
        print("[pacing] podcast mode: automatic pacing is not applied (per-turn rates are not measured)")
        pacing_spec = None
    fps = int(deck.get("fps", 30))
    transition = deck.get("transition") or {}
    tr_style = str(transition.get("style", "fade"))
    total_slides = len(deck["slides"])
    tr_frames = 0 if (tr_style == "none" or total_slides < 2) else int(transition.get("frames", 12))
    sfx_cfg = deck.get("sfx") or {}
    sfx_enabled = bool(sfx_cfg.get("enabled", True))
    sfx_volume = float(sfx_cfg.get("volume", 0.22))
    sfx_files = ensure_sfx_files(SR) if sfx_enabled else {}

    synther = VoiceSynth(rate)

    cursor_frames = 0
    resolved_slides = []
    gap = np.zeros(int(0.18 * SR), dtype=np.float32)

    for idx, slide in enumerate(deck["slides"], start=1):
        sid = slide["id"]
        plain = _plain_spoken_text(slide)
        voice_delay_sec = round((tr_frames / float(fps)) * 0.55, 3) if (idx > 1 and tr_frames > 0) else 0.0
        slide_rate_used, slide_wpm = rate, None  # podcast slides keep the deck rate; single slides may be paced

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
                raw_clip, bounds = synther.synth_with_timings(sp_id, txt)
                clip = postprocess_voice(raw_clip)
                seg_dur = len(clip) / float(SR)
                if seg_dur < 0.4 and len(txt) > 30:
                    raise DeckValidationError(f"Slide {sid}: TTS produced {seg_dur:.2f}s for {len(txt)} chars ({sp_id})")
                turn_events = _word_events_for_clip(clip, lang, f"{sid} turn {t_i + 1}", bounds)
                captions.extend(
                    build_word_captions(
                        txt, seg_dur, boundaries=turn_events, offset_sec=voice_delay_sec + cur_t, speaker=sp_tag,
                        spoken=normalize_ru_ssml(txt) if bounds else None,
                    )
                )
                chunks.append(clip)
                cur_t += seg_dur
                if t_i + 1 < len(turns):
                    chunks.append(gap)
                    cur_t += len(gap) / float(SR)
            audio = np.concatenate(chunks) if chunks else np.zeros(SR, dtype=np.float32)
            dur = len(audio) / float(SR)
            scene_s = max(2, math.ceil(voice_delay_sec + dur) + 1)
            print(f"[tts] {sid} (podcast {speaker_a}+{speaker_b}): {dur:.2f}s -> slide {scene_s}s")
        else:
            raw_audio, bounds, slide_rate_used, slide_wpm = _paced_synth(
                synther, speaker_a, plain, slide, pacing_spec, rate, sid
            )
            audio = postprocess_voice(raw_audio)
            dur = len(audio) / float(SR)
            if dur < 1.0 and len(plain) > 40:
                raise DeckValidationError(
                    f"Slide {sid}: TTS produced {dur:.2f}s for {len(plain)} chars; text is not voiceable by {speaker_a}"
                )
            events = _word_events_for_clip(audio, lang, sid, bounds)
            captions = build_word_captions(
                plain, dur, boundaries=events, offset_sec=voice_delay_sec,
                spoken=normalize_ru_ssml(plain) if bounds else None,
            )
            scene_s = max(2, math.ceil(voice_delay_sec + dur) + 1)
            b_tag = f" ({len(bounds)} real bounds)" if bounds else ""
            print(f"[tts] {sid} ({speaker_a}): {dur:.2f}s{b_tag} -> slide {scene_s}s")

        speech_windows = detect_speech_windows(audio, SR, offset_sec=voice_delay_sec)
        pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()
        wav_name = f"{deck['slug']}_{sid}.wav"
        wav_path = VOICE_DIR / wav_name
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SR)
            wf.writeframes(pcm)

        if slide.get("type") == "ui_recording":
            # The clip must fit in the slide: never cut the recording, extend the slide to its length (+1 s).
            rec_sec = _media_duration_sec(PUBLIC_DIR / slide["recording"]["src"])
            if math.ceil(rec_sec) + 1 > scene_s:
                print(f"[ui] {sid}: recording {rec_sec:.2f}s is longer than narration -> slide {math.ceil(rec_sec) + 1}s")
            scene_s = max(scene_s, math.ceil(rec_sec) + 1)
            # Renderer needs the clip length to freeze its last frame after the clip ends.
            slide = {**slide, "recording": {**slide["recording"], "duration_sec": round(rec_sec, 3)}}

        # Optional floor from the storyboard: a scene keeps its planned length even if narration is shorter.
        if slide.get("min_duration_sec") is not None:
            scene_s = max(scene_s, int(math.ceil(float(slide["min_duration_sec"]))))

        start_sec = round(cursor_frames / float(fps), 3)
        slide_frames = max(tr_frames * 2 + 1, int(round(scene_s * fps)))
        cursor_frames += slide_frames - (tr_frames if idx < total_slides else 0)

        item = dict(slide)
        item["duration_sec"] = scene_s
        item["start_sec"] = start_sec
        item["voice_delay_sec"] = voice_delay_sec
        item["voice_rate_used"] = slide_rate_used  # audit trail for automatic pacing (item 5)
        item["measured_wpm"] = round(slide_wpm, 1) if slide_wpm is not None else None
        item["speech_windows"] = speech_windows
        item["num"] = slide.get("_override_num") or f"{idx:02d} / {total_slides:02d}"
        item.pop("_override_num", None)
        item["voice_file"] = f"voice/{wav_name}"
        item["captions"] = captions
        resolved_slides.append(item)

    # Pre-render heuristic on REAL slide lengths (narration-derived scene_s). It is a warning, not a gate:
    # the authoritative black-tail gate is media_qa `no_black_frames` on the rendered MP4 (blackdetect).
    # Coverage is only a proxy: the approved universe-imax film has 0.5-1.5 s of shot-coverage deficit on
    # some slides but no black in the output, so a hard error here would reject a valid film.
    from deck_doctor import cinema_coverage_errors  # noqa: E402  (lazy: deck_doctor imports this module)

    for msg in cinema_coverage_errors(
        resolved_slides, [float(it["duration_sec"]) for it in resolved_slides], _media_duration_sec
    ):
        print(f"[coverage] WARN {msg}")

    total_frames = max(1, cursor_frames)
    total_sec = round(total_frames / float(fps), 3)
    pad_sec = int(math.ceil(total_sec)) + 2

    pad_name = f"{deck['slug']}_bg_pad.wav"
    pad_path = VOICE_DIR / pad_name
    with wave.open(str(pad_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(build_ambient_bed(pad_sec, SR))

    aspect = deck.get("aspect", "16:9")
    w, h = ASPECT_DIMS[aspect]
    music_cfg = deck.get("music") or {}
    duck_db = float(music_cfg.get("duck_db", -9.0))
    resolved = dict(deck)
    resolved["aspect"] = aspect
    resolved["fps"] = fps
    resolved["width"] = w
    resolved["height"] = h
    resolved["theme"] = deck.get("theme", "neon_cyber")
    resolved["burn_captions"] = deck.get("burn_captions", True)
    resolved["caption_style"] = deck.get("caption_style", "box")
    resolved["media_engine"] = deck.get("media_engine", "offthread")
    resolved["transition_style"] = tr_style
    resolved["transition_frames"] = tr_frames
    resolved["sfx_enabled"] = sfx_enabled
    resolved["sfx_volume"] = sfx_volume
    if sfx_files:
        resolved["sfx_transition_file"] = sfx_files["transition"]
        resolved["sfx_pop_file"] = sfx_files["pop"]
    resolved["music_duck_ratio"] = round(10.0 ** (duck_db / 20.0), 4)
    resolved["slides"] = resolved_slides
    resolved["total_frames"] = total_frames
    resolved["total_seconds"] = total_sec
    resolved["ambient_file"] = f"voice/{pad_name}"
    resolved["voice_used"] = voice_used
    print(
        f"[voice] deck voiced by '{voice_used}' | transition={tr_style}({tr_frames}f) "
        f"| sfx={'on' if sfx_enabled else 'off'} | duck={duck_db:+.1f}dB"
    )
    credits = attach_stock_media(deck, resolved_slides)
    attach_music(deck, resolved)
    if credits:
        from stock_media import write_credits  # noqa: E402

        cpath = write_credits(deck["slug"], credits)
        print(f"[media] credits -> {cpath}")
    RESOLVED_JSON.write_text(json.dumps(resolved, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[deck] wrote {RESOLVED_JSON} (total={total_sec:.2f}s / {total_frames}f, {w}x{h}, theme={resolved['theme']})")
    write_subtitles(resolved)
    return resolved


def run_cmd(args: list[str]) -> None:
    print(f"[run] {' '.join(args)}")
    res = subprocess.run(args, cwd=str(ROOT), shell=True)
    if res.returncode != 0:
        raise RuntimeError(f"Command failed (exit={res.returncode}): {' '.join(args)}")


def resolve_director_preset(deck: dict) -> dict:
    """If deck declares `director_preset`, apply its defaults without overwriting explicit keys."""
    dp_id = deck.get("director_preset")
    if dp_id is None or not str(dp_id).strip():
        return deck
    from director_presets import DirectorPresetError, apply_director_preset

    try:
        return apply_director_preset(deck, str(dp_id).strip(), override_existing=False)
    except DirectorPresetError as exc:
        raise DeckValidationError(str(exc)) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="DUP Presenter deck builder")
    parser.add_argument("deck", help="Path to deck JSON (e.g. decks/dup_labs.json)")
    parser.add_argument("--render", action="store_true", help="Also type-check, render MP4, QA & publish pack")
    parser.add_argument("--skip-tts", action="store_true", help="Reuse existing WAV files")
    parser.add_argument("--only-slide", default="", help="Fast preview: build/render only this slide id (e.g. s5)")
    parser.add_argument("--preview-stills", action="store_true", help="Render 1 PNG frame per slide to out/<slug>_stills/")
    parser.add_argument("--no-loudnorm", action="store_true", help="Skip -16 LUFS broadcast loudness normalization")
    parser.add_argument("--no-qa", action="store_true", help="Skip post-render Media QA Gate")
    parser.add_argument("--offline-only", action="store_true", help="Privacy Lock: block all network TTS/stock calls")
    parser.add_argument("--audit-repo", default="", help="Run Claim Audit against this source repo before build")
    parser.add_argument("--strict-audit", action="store_true", help="Fail build on any unverified number in Claim Audit")
    parser.add_argument("--overwrite", action="store_true", help="Allow --render to replace an existing out/<slug>.mp4")
    parser.add_argument("--crf", type=int, default=None, help=f"H.264 CRF quality ({CRF_MIN}..{CRF_MAX}, default {DEFAULT_RENDER_CRF}; draft default {DRAFT_RENDER_CRF})")
    parser.add_argument("--draft", action="store_true", help="Fast 0.5x draft preview -> out/<slug>_draft.mp4 (never overwrites master MP4)")
    parser.add_argument(
        "--require-storyboard",
        action="store_true",
        help="Master render (no --draft) only if the storyboard is approved for this exact deck + draft (fail-closed)",
    )
    args = parser.parse_args()

    effective_crf = args.crf if args.crf is not None else (DRAFT_RENDER_CRF if args.draft else DEFAULT_RENDER_CRF)
    if not (CRF_MIN <= effective_crf <= CRF_MAX):
        print(f"[ERROR] --crf must be in [{CRF_MIN}, {CRF_MAX}], got {effective_crf}", file=sys.stderr)
        return 2

    deck_path = Path(args.deck)
    if not deck_path.is_absolute():
        deck_path = ROOT / deck_path
    if not deck_path.is_file():
        print(f"[ERROR] Deck not found: {deck_path}", file=sys.stderr)
        return 2

    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    from storyboard_gate import (  # noqa: E402  (storyboard_gate has no build_deck dependency)
        StoryboardGateError,
        assert_master_allowed,
        deck_fingerprint,
        record_draft_build,
    )

    raw_deck_sha = deck_fingerprint(deck)
    # Only decks stored under decks/<slug>.json are gated/recorded: the console and the storyboard
    # reader both address the deck by slug. A deck file elsewhere cannot satisfy the gate.
    # --skip-tts reuses the shared src/generated/deck_resolved.json (not necessarily this deck), so such
    # a render cannot be bound to the deck content: it is never recorded and never gated-through.
    storyboard_target = (
        deck_path.resolve() == (ROOT / "decks" / f"{deck.get('slug')}.json").resolve()
        and not args.only_slide.strip()
        and not args.skip_tts
    )
    if args.render and not args.draft and args.require_storyboard:
        if not storyboard_target:
            print(
                "[ERROR] storyboard gate: master render requires decks/<slug>.json, no --only-slide and no --skip-tts; refusing",
                file=sys.stderr,
            )
            return 2
        try:
            assert_master_allowed(str(deck.get("slug")), deck_sha256=raw_deck_sha)
        except StoryboardGateError as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            return 2
    deck = resolve_director_preset(deck)
    try:
        resolve_deck_sfx(deck)  # named SFX cues -> src (generates public/sfx/library/ if needed)
    except SfxLibraryError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2
    # Annotated COPY: the source file on disk is never written by the build (pipeline item 4).
    deck = prepare_deck(deck)

    if args.render:
        from deck_doctor import diagnose_deck  # noqa: E402  (lazy import: deck_doctor imports this module)

        report = diagnose_deck(deck, overwrite=args.overwrite, draft=args.draft)
        for w in report["warnings"]:
            print(f"[doctor:warn] {w}")
        if not report["ok"]:
            for e in report["errors"]:
                print(f"[doctor:error] {e}", file=sys.stderr)
            print("[ERROR] deck doctor refused to render; fix the errors above", file=sys.stderr)
            return 2
        print(f"[doctor] ok | ~{report['estimates']['estimated_length_sec']:.0f}s video, "
              f"~{report['estimates']['estimated_render_sec']/60:.1f} min render estimate")

    if args.audit_repo:
        from claim_audit import audit_deck  # noqa: E402

        audit = audit_deck(deck, repo_root=Path(args.audit_repo))
        print(
            f"[audit] verified={audit['verified_hits']} "
            f"evidence_err={len(audit['evidence_errors'])} "
            f"safety_warn={len(audit['safety_warnings'])} "
            f"unverified_sym={len(audit['unverified_symbols'])} "
            f"unverified_num={len(audit['unverified_numbers'])}"
        )
        passed = audit["ok"] if args.strict_audit else audit["hard_ok"]
        if not passed:
            print(json.dumps(audit, ensure_ascii=False, indent=2), file=sys.stderr)
            print("[ERROR] Claim Audit failed — fix unverified claims before rendering", file=sys.stderr)
            return 3

    only_sid = args.only_slide.strip()
    if only_sid:
        all_slides = deck["slides"]
        match_idx = next((i for i, s in enumerate(all_slides, start=1) if s.get("id") == only_sid), None)
        if match_idx is None:
            ids = [s.get("id") for s in all_slides]
            print(f"[ERROR] --only-slide {only_sid!r} not found; available: {ids}", file=sys.stderr)
            return 2
        slide_copy = dict(all_slides[match_idx - 1])
        slide_copy["_override_num"] = f"{match_idx:02d} / {len(all_slides):02d}"
        deck = dict(deck)
        deck["slug"] = f"{deck['slug']}_{only_sid}"
        deck["slides"] = [slide_copy]
        deck["transition"] = {"style": "none", "frames": 0}
        print(f"[only-slide] isolated slide {only_sid!r} ({slide_copy['_override_num']}) -> slug={deck['slug']}")

    if not args.skip_tts:
        resolved = synthesize_deck(deck, offline_only=args.offline_only)
        bind_resolved_to_deck(resolved, raw_deck_sha, only_slide=args.only_slide)
        RESOLVED_JSON.write_text(json.dumps(resolved, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        if not RESOLVED_JSON.is_file():
            print("[ERROR] --skip-tts used but deck_resolved.json does not exist", file=sys.stderr)
            return 2
        resolved = json.loads(RESOLVED_JSON.read_text(encoding="utf-8"))
        # Fail closed: refuse a timeline that was synthesized from another deck, before anything is overwritten.
        skip_err = skip_tts_source_error(resolved, raw_deck_sha)
        if skip_err:
            print(f"[ERROR] --skip-tts refused: {skip_err}", file=sys.stderr)
            return 2
        # Apply slug/theme/aspect/caption/transition/sfx switches from deck even on --skip-tts.
        # slug must come from the deck: it names the output MP4/SRT/pack, and a stale cached slug
        # silently overwrote a previous render.
        resolved["slug"] = deck["slug"]
        aspect = deck.get("aspect", resolved.get("aspect", "16:9"))
        resolved["aspect"] = aspect
        resolved["width"], resolved["height"] = ASPECT_DIMS[aspect]
        resolved["theme"] = deck.get("theme", resolved.get("theme", "neon_cyber"))
        resolved["burn_captions"] = deck.get("burn_captions", resolved.get("burn_captions", True))
        resolved["caption_style"] = deck.get("caption_style", "box")
        resolved["media_engine"] = deck.get("media_engine", "offthread")
        tr = deck.get("transition") or {}
        if tr:
            resolved["transition_style"] = tr.get("style", resolved.get("transition_style", "fade"))
            resolved["transition_frames"] = 0 if resolved["transition_style"] == "none" else int(tr.get("frames", 12))
        sfx_cfg = deck.get("sfx") or {}
        if sfx_cfg:
            resolved["sfx_enabled"] = bool(sfx_cfg.get("enabled", True))
            resolved["sfx_volume"] = float(sfx_cfg.get("volume", 0.22))
            if resolved["sfx_enabled"]:
                sf = ensure_sfx_files(SR)
                resolved["sfx_transition_file"] = sf["transition"]
                resolved["sfx_pop_file"] = sf["pop"]
        music_cfg = deck.get("music") or {}
        if music_cfg.get("enabled"):
            attach_music(deck, resolved)
        else:
            resolved.pop("music_file", None)
        bind_resolved_to_deck(resolved, raw_deck_sha, only_slide=args.only_slide)
        RESOLVED_JSON.write_text(json.dumps(resolved, ensure_ascii=False, indent=2), encoding="utf-8")
        write_subtitles(resolved)

    if args.preview_stills:
        stills_dir = ROOT / "out" / f"{resolved['slug']}_stills"
        stills_dir.mkdir(parents=True, exist_ok=True)
        run_cmd(["npx", "tsc", "--noEmit"])
        fps = int(resolved.get("fps", 30))
        total_frames = int(resolved.get("total_frames") or round(resolved["total_seconds"] * fps))
        for s in resolved["slides"]:
            mid_sec = float(s.get("start_sec", 0.0)) + min(2.5, float(s["duration_sec"]) * 0.4)
            frame = min(max(0, total_frames - 1), max(0, int(round(mid_sec * fps))))
            out_png = stills_dir / f"{s['id']}.png"
            run_cmd(["npx", "remotion", "still", "DupPresenter", str(out_png), f"--frame={frame}"])
        print(f"[OK] Rendered {len(resolved['slides'])} slide stills -> {stills_dir}")

    if args.render:
        out_stem = f"{resolved['slug']}_draft" if args.draft else resolved["slug"]
        out_mp4 = ROOT / "out" / f"{out_stem}.mp4"
        out_thumb = ROOT / "out" / f"{resolved['slug']}_thumb.png"
        out_mp4.parent.mkdir(parents=True, exist_ok=True)
        run_cmd(["npx", "tsc", "--noEmit"])
        render_cmd = [
            "npx", "remotion", "render", "DupPresenter", str(out_mp4),
            "--audio-codec=aac", "--audio-bitrate=320K",
            f"--crf={effective_crf}",
        ]
        if args.draft:
            render_cmd.append(f"--scale={DRAFT_RENDER_SCALE}")
        run_cmd(render_cmd)
        # Item 3: every render gets the broadcast profile (yuv420p/bt709, maxrate, GOP, 30 fps) before
        # loudness and QA. Media QA then enforces the hard limits on the encoded file.
        from broadcast_encode import broadcast_encode  # noqa: E402

        bc = broadcast_encode(out_mp4)
        print(f"[encode] broadcast profile: {bc['bytes_before'] / 1_048_576:.1f} MB -> "
              f"{bc['bytes_after'] / 1_048_576:.1f} MB (maxrate {bc['maxrate']}, crf {bc['crf']})")
        loudnorm_applied = False
        if not args.no_loudnorm and (deck.get("audio") or {}).get("loudnorm", True):
            lufs = normalize_mp4_loudness(out_mp4, target_lufs=-16.0, true_peak=-1.5)
            loudnorm_applied = True
            print(
                f"[audio] loudnorm: {lufs['input_lufs']} LUFS (TP {lufs['input_tp_db']} dB) "
                f"-> {lufs['output_lufs']} LUFS (TP {lufs['output_tp_db']} dB)"
            )

        qa_report = None
        if not args.no_qa:
            from media_qa import run_media_qa  # noqa: E402

            qa_report = run_media_qa(
                out_mp4,
                resolved=resolved,
                expect_loudnorm=loudnorm_applied,
                expected_scale=(DRAFT_RENDER_SCALE if args.draft else 1.0),
                draft=args.draft,
            )
            qa_path = out_mp4.parent / f"{out_stem}_qa.json"
            qa_path.write_text(json.dumps(qa_report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(
                f"[qa] {'PASS' if qa_report['ok'] else 'FAIL'} | "
                f"{qa_report['width']}x{qa_report['height']} {qa_report['duration_sec']}s | "
                f"LUFS={qa_report['audio'].get('integrated_lufs')} TP={qa_report['audio'].get('true_peak_dbtp')} dBTP | "
                f"max_silence={qa_report['audio'].get('max_interior_silence_sec')}s"
            )
            if not qa_report["ok"]:
                raise RuntimeError(f"Media QA Gate FAILED ({qa_report['hard_fails']} hard fail(s)); see {qa_path}")

        if args.draft:
            if storyboard_target and resolved.get("slug") == deck.get("slug"):
                record_draft_build(deck["slug"], raw_deck_sha, list(resolved["slides"]))
                print(f"[storyboard] draft bound to deck sha256={raw_deck_sha[:12]} (approve in console before master)")
            print(
                f"[OK] Draft rendered ({DRAFT_RENDER_SCALE}x, crf={effective_crf}): "
                f"{out_mp4} ({out_mp4.stat().st_size / 1_048_576:.2f} MB) — master MP4 untouched"
            )
            return 0

        total_frames = int(resolved.get("total_frames") or round(resolved["total_seconds"] * resolved.get("fps", 30)))
        thumb_frame = min(45, max(0, total_frames - 1))
        run_cmd(["npx", "remotion", "still", "DupPresenter", str(out_thumb), f"--frame={thumb_frame}"])

        from publish_pack import build_publish_pack  # noqa: E402

        pack = build_publish_pack(resolved, mp4_path=out_mp4, qa_report=qa_report, out_dir=out_mp4.parent)
        print(
            f"[pack] wrote {pack['chapters'].name}, {pack['post_copy'].name}, {pack['metadata'].name}"
        )
        print(f"[OK] Rendered (crf={effective_crf}): {out_mp4} ({out_mp4.stat().st_size / 1_048_576:.2f} MB) + {out_thumb.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
