"""Single visual token source for Python-rendered cards (pipeline item 8).

Remotion slides take their palette from `src/themes.ts`; the TikTok outro cards are drawn by
`render_tiktok_outros.py` (HTML canvas). Before this module the outro hard-coded its own background, text and
font stacks, so the two looked like different products. Now the outro reads these tokens.

Drift guard: `tests/test_visual_tokens.py` parses `src/themes.ts` and fails if the mirrored neon_cyber values
here stop matching it. Change the TypeScript first, then mirror the change here.
"""

from __future__ import annotations

# Typography: the same stacks the Remotion compositions use.
FONT_UI = "Segoe UI, Inter, Arial, sans-serif"  # src/Thumbnail.tsx
FONT_MONO = "Consolas, monospace"  # src/UniversalSlides.tsx, src/StorySlides.tsx
# Canvas `ctx.font` needs the quoted family form; kept derived from the same stack.
FONT_UI_CANVAS = '"Segoe UI", Inter, Arial, sans-serif'
FONT_MONO_CANVAS = FONT_MONO

# Palette mirrored from src/themes.ts THEMES.neon_cyber (the default theme).
NEON_CYBER_MIRROR: dict[str, str] = {
    "bg": "#050714",
    "text": "#f8fafc",
    "muted": "#cbd5e1",
    "cardBg": "rgba(15,23,42,0.72)",
}

BG = NEON_CYBER_MIRROR["bg"]
TEXT = NEON_CYBER_MIRROR["text"]
MUTED = NEON_CYBER_MIRROR["muted"]
CARD_BG = NEON_CYBER_MIRROR["cardBg"]
# Gradient stops of the starfield backdrop. Not theme colours; they are a shade between bg and black.
BG_GRADIENT_MID = "#091026"
BG_GRADIENT_DEEP = "#02040b"

# Output formats. Keep in step with build_deck.ASPECT_DIMS (checked by the tests).
FORMATS: dict[str, tuple[int, int]] = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
}
