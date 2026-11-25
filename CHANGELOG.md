# Changelog

All notable changes to **DUP Presenter** are documented in this file. Dates and versions match actual commits and verified runs on disk.

## [Unreleased / 1.3.0-dev] — 2026-11-25

### Added (Universal Studio Roadmap A–D)
- **Phase A — Built-in Idea Engine (`scripts/idea_engine.py`, `console_server.py`, `console_ui.html`, `mcp_server.py`):** 7 video genres (`tech_explainer`, `versus_battle`, `short_60s`, `news_digest`, `investor_pitch`, `case_study`, `tutorial`), honest offline template mode vs fail-closed Ollama/Cloud LLM mode, and 1-click conversion into validated `decks/<slug>.json`.
- **Phase B — 4 Universal Slide Templates (`src/UniversalSlides.tsx`, `src/types.ts`, `scripts/build_deck.py`):** `versus_split` (A vs B 3D comparison + verdict), `chart_story` (`bar` / `line` / `donut`), `stat_burst` (high-impact hook slide), and `broll_cinematic` (Ken Burns full-bleed storytelling) — total **18 slide types**.
- **Phase C — Director Presets, Thumbnail Studio & Duo Speaker Indicator:**
  - `scripts/director_presets.py` (`cinema_cosmos`, `fast_shorts`, `documentary`, `news_flash`, `tech_pitch`).
  - `scripts/thumbnail_studio.py` + Remotion `DupThumbnail` (`src/Thumbnail.tsx`, `1280×720`).
  - Upgraded `duo` active-speaker badge (`HOST` / `EXPERT`) in `src/Composition.tsx`.
- **Phase D — Multi-Format Video Pack (`scripts/video_pack.py` + MCP `plan_video_pack` / `render_thumbnail`):** builds coordinated 16:9 + 9:16 Short + optional translation + 1280×720 cover + unified fail-closed `out/<slug>_pack_manifest.json`.
- **Tests:** `tests/test_idea_engine.py`, `tests/test_universal_slides.py`, `tests/test_director_thumb_pack.py` (**153 total tests passing**).

## [1.2.0] — 2026-11-25

### Added
- **Cosmic `quantum_ledger` theme (`src/CosmosBackdrop.tsx`, `src/themes.ts`, `scripts/theme_catalog.py`):**
  - Deep concave 3D cosmic tunnel with converging meridians, concentric depth rings, multi-tone flank nebulae, and 22 animated transaction light beams (cyan/emerald/gold/violet flowing inward; red invalid packets deflecting with shockwave rings at the outer fail-closed perimeter).
  - Inflated/beveled 3D shelves, concave column angling (`rotateY`), and floating detached typography/KPI numbers across story and core slides.
- **4 new visual storytelling slide types (`src/StorySlides.tsx`, `scripts/build_deck.py`, `src/types.ts`):**
  - `protocol_cosmos` — central rotating holographic crypto reactor (`DUP CORE`), 6 angled 3D stations, Bezier optical conduits with traveling light packets, and animated red fail-closed shield deflection.
  - `ledger_layers` — 3D isometric layer stack (3–6 layers) with per-layer highlight and localized `GUARANTEE:` / `ГАРАНТИЯ:` banner.
  - `tx_journey` — animated transaction lifecycle with golden Merkle tree folding, `prev_hash` block chaining, and atomic green `SEALED ✓` / `ROCKSDB COMMITTED ✓` stamp.
  - `mesh_network` — 3–4 node P2P mesh topology with live block propagation pulses, consistency probes, and recovery/fail-closed cards.
- **New DUP Protocol showcase decks:**
  - `decks/dup-protocol-cosmos.json` (RU, 10 scenes, `quantum_ledger`, Edge Neural `dmitry`, `229.42s`, Media QA PASS `-16.0 LUFS`).
  - `decks/dup-protocol-cosmos-en.json` (EN, 10 scenes, `quantum_ledger`, Kokoro `am_michael` + `faster-whisper` ASR 88–100% word alignment, `245.50s`, Media QA PASS `-16.06 LUFS`).
  - `decks/dup-protocol-story.json` (RU mini-film, `213.8s`, Media QA PASS `-16.02 LUFS`).
- **Repository & documentation suite:** `CHANGELOG.md`, `CITATION.cff`, `SECURITY.md`, `CONTRIBUTING.md`, `docs/ARCHITECTURE.md`, `docs/DECK_SCHEMA.md`, `.github/REPO_PROFILE.md`, and GitHub Issue/PR templates.
- **Tests:** `tests/test_story_slides.py` covering positive and fail-closed validation for all 4 new story slide types (137 total unit tests passing).

### Changed
- `decks/dup-protocol.json`: updated `screen_split` to use all 5 full-resolution (`2560×1528`) local Ops Console screenshots.
- `package.json`: updated package metadata (`dup-presenter`, `1.2.0`, repository/homepage/keywords).

## [1.1.0] — 2026-11-25

### Added
- **Caption styles (`caption_style`):** `box` (default), `karaoke` (word-level highlight), and `bold` (shadowed vertical-video captions).
- **Real word-level caption timing:**
  - Russian Edge TTS `WordBoundary` token alignment with fail-closed fallback and explicit match-percentage logging.
  - English local `faster-whisper` (`base.en`) ASR word timing for Kokoro / Silero EN voices.
- **Markdown deck importer (`scripts/md_deck.py`):** fail-closed conversion from Markdown to JSON for `hero_3d`, `outro_3d`, `kpi`, and `timeline`, plus `/api/import-md` in the web console.
- **New slide types:** `quote` (single statement with attribution, strict planner rules) and `ui_recording` (Playwright UI scenario recordings with auto-zoom via `scripts/record_ui.py` and `ffprobe` duration sizing in `deck_doctor.py`).
- **Web console upgrades (`scripts/console_server.py`, `scripts/console_ui_check.py`):** caption style selector, Markdown import UI, and live Chromium UI smoke verification.

### Fixed
- 3D cube faces (`backfaceVisibility: "hidden"`) so rear cube labels no longer bleed mirrored through front faces.
- `deck_doctor.py` speech duration estimation calibrated per language from narration words rather than on-screen text, plus `check_assets` flag for CI runs on clean checkouts.

## [1.0.0] — 2026-11-25

### Added
- Core declarative pipeline: JSON deck validation (`build_deck.py`, `deck_doctor.py`), repository fact audit (`claim_audit.py`), neural TTS (`tts_engines.py`, `edge_engine.py`, `ru_speech.py`), STFT de-esser & dynamic music ducking (`audio_fx.py`), procedural SFX, Remotion 4 3D renderer (`src/Composition.tsx`), two-pass `-16 LUFS` broadcast mastering, fail-closed `Media QA Gate` (`media_qa.py`), and `Publish Pack` generator (`publish_pack.py`).
- Core slide templates: `hero_3d`, `code_split`, `screen_split`, `arch_flow`, `kpi`, `timeline`, `terminal`, `outro_3d`.
- Automation tools: local web console (`console_server.py`), stdio JSON-RPC 2.0 MCP server (`mcp_server.py`), 9:16 short cutdown (`make_cutdown.py`), RU↔EN deck translator (`translate_deck.py`), Playwright screenshotter (`capture_ui.py`), and GitHub Release / TikTok uploaders.
- First published showcase release: [`media-radar-showcase-v2`](https://github.com/Gruver87/dup-presenter/releases/tag/media-radar-showcase-v2).
