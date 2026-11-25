"""DUP Presenter — Director Presets (pacing, theme, transitions, captions, audio mix).

Applies cohesive, production-tested directing presets to any deck without
silently inventing unverified content. Unknown preset IDs fail closed.
"""

from __future__ import annotations

import copy
from typing import Any

from build_deck import ASPECT_DIMS

DIRECTOR_PRESETS: dict[str, dict[str, Any]] = {
    "cinema_cosmos": {
        "id": "cinema_cosmos",
        "label_ru": "Космическое кино (16:9, quantum_ledger, караоке)",
        "label_en": "Cinema Cosmos (16:9, quantum_ledger, karaoke)",
        "theme": "quantum_ledger",
        "aspect": "16:9",
        "caption_style": "karaoke",
        "transition_style": "fade",
        "transition_frames": 15,
        "sfx_enabled": True,
        "sfx_volume": 0.16,
        "music_volume": 0.10,
        "duck_db": -10.5,
        "voice_rate": "96%",
    },
    "fast_shorts": {
        "id": "fast_shorts",
        "label_ru": "Динамичный Short / Reels (9:16, крупный bold, быстрый ритм)",
        "label_en": "Fast Short / Reels (9:16, bold captions, punchy rhythm)",
        "theme": "cyber_magenta",
        "aspect": "9:16",
        "caption_style": "bold",
        "transition_style": "slide",
        "transition_frames": 10,
        "sfx_enabled": True,
        "sfx_volume": 0.22,
        "music_volume": 0.12,
        "duck_db": -9.5,
        "voice_rate": "104%",
    },
    "documentary": {
        "id": "documentary",
        "label_ru": "Спокойный документальный (16:9, deep_ocean, плавный fade)",
        "label_en": "Calm Documentary (16:9, deep_ocean, slow fade)",
        "theme": "deep_ocean",
        "aspect": "16:9",
        "caption_style": "box",
        "transition_style": "fade",
        "transition_frames": 20,
        "sfx_enabled": True,
        "sfx_volume": 0.08,
        "music_volume": 0.08,
        "duck_db": -12.0,
        "voice_rate": "94%",
    },
    "news_flash": {
        "id": "news_flash",
        "label_ru": "Новостной дайджест (16:9, cosmic_radar, wipe, караоке)",
        "label_en": "News Flash Digest (16:9, cosmic_radar, wipe, karaoke)",
        "theme": "cosmic_radar",
        "aspect": "16:9",
        "caption_style": "karaoke",
        "transition_style": "wipe",
        "transition_frames": 10,
        "sfx_enabled": True,
        "sfx_volume": 0.18,
        "music_volume": 0.09,
        "duck_db": -11.0,
        "voice_rate": "102%",
    },
    "tech_pitch": {
        "id": "tech_pitch",
        "label_ru": "Светлый питч для фонда / бизнеса (16:9, minimal_light)",
        "label_en": "Clean Investor / Business Pitch (16:9, minimal_light)",
        "theme": "minimal_light",
        "aspect": "16:9",
        "caption_style": "box",
        "transition_style": "fade",
        "transition_frames": 14,
        "sfx_enabled": True,
        "sfx_volume": 0.10,
        "music_volume": 0.07,
        "duck_db": -12.0,
        "voice_rate": "97%",
    },
}

PRESET_CATALOG: list[dict[str, Any]] = list(DIRECTOR_PRESETS.values())


class DirectorPresetError(ValueError):
    """Raised when an unknown or malformed director preset is requested."""


def apply_director_preset(
    deck: dict[str, Any],
    preset_id: str,
    *,
    override_existing: bool = True,
) -> dict[str, Any]:
    """Return a copy of `deck` with director preset settings applied (fail-closed)."""
    if preset_id not in DIRECTOR_PRESETS:
        raise DirectorPresetError(
            f"Unknown director preset {preset_id!r}; allowed: {', '.join(sorted(DIRECTOR_PRESETS))}"
        )
    p = DIRECTOR_PRESETS[preset_id]
    out = copy.deepcopy(deck)

    def _set(key: str, val: Any) -> None:
        if override_existing or key not in out:
            out[key] = val

    _set("theme", p["theme"])
    _set("aspect", p["aspect"])
    w, h = ASPECT_DIMS[out["aspect"]]
    out["width"], out["height"] = w, h
    _set("caption_style", p["caption_style"])
    _set("transition_style", p["transition_style"])
    _set("transition_frames", p["transition_frames"])
    _set("sfx_enabled", p["sfx_enabled"])
    _set("sfx_volume", p["sfx_volume"])

    music = dict(out.get("music") or {"enabled": True})
    if override_existing or "volume" not in music:
        music["volume"] = p["music_volume"]
    if override_existing or "duck_db" not in music:
        music["duck_db"] = p["duck_db"]
    out["music"] = music

    voice = dict(out.get("voice") or {})
    if voice and (override_existing or "rate" not in voice):
        voice["rate"] = p["voice_rate"]
        out["voice"] = voice

    out["director_preset"] = preset_id
    return out
