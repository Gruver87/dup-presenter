"""Single source of truth for DUP Presenter visual themes.

Every palette id here MUST exist in src/themes.ts (THEMES). Adding a theme:
  1. add the palette to src/themes.ts and the id to ThemeId;
  2. add an entry to THEME_CATALOG below;
  3. run `npx tsc --noEmit` in the project root.

Scripts (build_deck, plan_deck, console_server) import THEME_IDS / THEME_CATALOG
from here, so the list cannot drift between Python and the Remotion renderer.
"""

from __future__ import annotations

THEME_CATALOG: list[dict[str, str]] = [
    {"id": "neon_cyber", "label": "Neon Cyber (тёмная неон)", "mode": "dark"},
    {"id": "cosmic_radar", "label": "Cosmic Radar (космос + 3D Земля + монеты)", "mode": "dark"},
    {"id": "minimal_light", "label": "Minimal Light (светлая)", "mode": "light"},
    {"id": "terminal_green", "label": "Terminal Green (матрица/код)", "mode": "dark"},
    {"id": "deep_ocean", "label": "Deep Ocean (глубокий синий)", "mode": "dark"},
    {"id": "sunset_orange", "label": "Sunset Orange (закат, тёплый)", "mode": "dark"},
    {"id": "cyber_magenta", "label": "Cyber Magenta (розово-бирюзовый)", "mode": "dark"},
    {"id": "aurora_purple", "label": "Aurora Purple (северное сияние)", "mode": "dark"},
    {"id": "mono_graphite", "label": "Mono Graphite (графит, без цвета)", "mode": "dark"},
    {"id": "paper_warm", "label": "Paper Warm (бумага, светлая)", "mode": "light"},
    {"id": "corporate_blue", "label": "Corporate Blue (деловая, светлая)", "mode": "light"},
    {"id": "quantum_ledger", "label": "Quantum Ledger (космическая 3D-воронка + свет транзакций)", "mode": "dark"},
]

THEME_IDS: tuple[str, ...] = tuple(t["id"] for t in THEME_CATALOG)
DEFAULT_THEME = "neon_cyber"
