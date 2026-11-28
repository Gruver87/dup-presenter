<p align="center">
  <a href="https://github.com/Gruver87">
    <img src="https://raw.githubusercontent.com/Gruver87/Gruver87/main/assets/card-dup-presenter.png" alt="dup-presenter — Interactive 3D & Cinema Production Studio" width="880" />
  </a>
</p>

# DUP Presenter

[![CI](https://github.com/Gruver87/dup-presenter/actions/workflows/ci.yml/badge.svg)](https://github.com/Gruver87/dup-presenter/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Gruver87/dup-presenter)](https://github.com/Gruver87/dup-presenter/releases/tag/v1.2.0)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776ab.svg)](https://www.python.org/)
[![Node 22](https://img.shields.io/badge/Node-22-339933.svg)](package.json)

**Declarative 3D Product Presentation Engine** by **DUP Labs** (JSON/Markdown deck → neural TTS + STFT de-esser + dynamic music ducking + word-level karaoke captions → Remotion 4 3D slides & cosmic themes → broadcast `−16 LUFS` 1080p/9:16 MP4 + fail-closed Media QA Gate + Publish Pack).

It builds reproducible product 3D presentations (16:9 and 9:16) with live code, real screenshots, UI recordings, holographic 3D architecture, KPI metrics, and fact checks against the repository source — **without manual video editing**.

**English** · [Русский](README.ru.md)

---

## Demo videos (GitHub Releases)

MP4 files are not committed to git (100 MB limit). Ready renders with subtitles `.srt/.vtt`, chapters, and Media QA Gate reports are published in **GitHub Releases**:

### 1. DUP Protocol Cosmos (`quantum_ledger` · RU & EN)

| Russian version (`229.4 s`, `−16.0 LUFS`, Edge Neural `dmitry`) | English version (`245.5 s`, `−16.06 LUFS`, Kokoro `am_michael`) |
|---|---|
| [![DUP Protocol Cosmos RU](docs/media/dup-protocol-cosmos-ru-thumb.jpg)](https://github.com/Gruver87/dup-presenter/releases/tag/media-dup-protocol-cosmos) | [![DUP Protocol Cosmos EN](docs/media/dup-protocol-cosmos-en-thumb.jpg)](https://github.com/Gruver87/dup-presenter/releases/tag/media-dup-protocol-cosmos) |

- Decks: [`decks/dup-protocol-cosmos.json`](decks/dup-protocol-cosmos.json) (RU) and [`decks/dup-protocol-cosmos-en.json`](decks/dup-protocol-cosmos-en.json) (EN), theme `quantum_ledger`, 10 scenes, flagship slides `protocol_cosmos`, `ledger_layers`, `tx_journey`, `mesh_network`.
- Release with MP4, `.srt/.vtt`, `_chapters.txt` and `_qa.json`: [**`media-dup-protocol-cosmos`**](https://github.com/Gruver87/dup-presenter/releases/tag/media-dup-protocol-cosmos).

### 2. DUP Market Radar Showcase v2 (`142 s`, `−16 LUFS`, Media QA PASS)

[![Watch the demo: DUP Market Radar](docs/media/radar-showcase-v2-thumb.jpg)](https://github.com/Gruver87/dup-presenter/releases/download/media-radar-showcase-v2/radar-showcase-v2.mp4)

- Deck: [`decks/radar-showcase-v2.json`](decks/radar-showcase-v2.json) · Release: [**`media-radar-showcase-v2`**](https://github.com/Gruver87/dup-presenter/releases/tag/media-radar-showcase-v2).

---

## Pipeline architecture

```text
decks/<slug>.json  (or examples/*.md -> scripts/md_deck.py)
   │
   ▼  python scripts/build_deck.py decks/<slug>.json --render
1. Fail-closed schema validation + deck_doctor + optional Claim Audit (--audit-repo)
2. Voiceover RU (Edge TTS dmitry + offline Silero v5 eugene) / EN (Kokoro-82M v1.0 am_michael)
   + STFT de-esser + speech detector for dynamic music ducking
   + word-level caption timings (Edge WordBoundary for RU / local faster-whisper ASR for EN)
   + procedural SFX (transition whoosh + UI pop)
3. Render in Remotion 4 (TransitionSeries fade/slide/wipe + 12 themes + 18 3D slide templates)
4. Audio mastering to -16.0 LUFS / -1.5 dBTP (two-pass ffmpeg loudnorm, 48 kHz AAC 320 kbps)
5. Media QA Gate (ffprobe + LUFS + True Peak + dead-air check) -> out/<slug>_qa.json
6. Publish Pack: out/<slug>.srt/.vtt, _chapters.txt, _post_copy.md, _metadata.json, _thumb.png
```

Detailed diagram and module map: [**`docs/ARCHITECTURE.md`**](docs/ARCHITECTURE.md) · Full deck schema: [**`docs/DECK_SCHEMA.md`**](docs/DECK_SCHEMA.md).

---

## 18 slide templates (`type`)

| Template | Description |
|----------|-------------|
| `hero_3d` | Title slide with a gradient, colored badges and a rotating 3D cube (`backfaceVisibility: hidden`) |
| `protocol_cosmos` | Central rotating crypto reactor, 6 concave 3D stations with fiber-optic beams and a red `fail-closed` shield |
| `ledger_layers` | 3D stack of architecture layers (3–6 layers) with step-by-step focus and a localized `GUARANTEE:` / `ГАРАНТИЯ:` badge |
| `tx_journey` | Transaction lifecycle: Merkle tree collapse, `prev_hash` block linking and a `SEALED ✓` stamp |
| `mesh_network` | 3D topology of 3–4 network nodes with block propagation pulses, consistency probes and recovery cards |
| `versus_split` | **A vs B** comparison (two concave 3D columns, a pulsing `VS` center and a `VERDICT` badge) |
| `chart_story` | Animated charts (`bar`, `line`, `donut`) with spring-animated value growth and labels |
| `stat_burst` | Dynamic hook slide for the first 3–5 seconds (a giant floating number/thesis + energy ring) |
| `broll_cinematic` | Full-screen cinematic slide with Ken Burns, vignetting and thesis cards |
| `cinema_clip` | Full-screen video with no frames or diagrams: `cinema.src` (MP4 under `public/`, duration read via `ffprobe`, looped to the voiceover) or a stock background from `background_query`. If the file is missing, the build fails (fail-closed) |
| `code_split` | Split screen: thesis on the left, a 3D window with real code on the right, animated line by line |
| `screen_split` | Split screen with real screenshots and a virtual camera with auto-zoom (`focus: {x, y, zoom}`) |
| `ui_recording` | Live recording of a UI scenario via Playwright (`scripts/record_ui.py`) with duration auto-fitted through `ffprobe` |
| `arch_flow` | 3D architecture pipeline with animated packet flows |
| `kpi` | Key metrics (1–4 cards; in `quantum_ledger` — concave shelves and floating numbers) |
| `timeline` | Step-by-step pipeline / roadmap (2–6 steps) |
| `terminal` | Animated terminal output |
| `quote` | Quote in a 3D card (`title`, up to 220 characters) with attribution in `subtitle` |
| `outro_3d` | Closing slide with a repository link, badges, a tagline and a 3D cube |

## New studio tools (Idea Engine, Presets, Thumbnail Studio, Video Pack)

```powershell
# A) Built-in Idea Engine (7 genres, offline templates / Ollama / Cloud / DeepSeek, 1 step -> deck draft)
python scripts/idea_engine.py --topic "Python vs Rust in 2026" --genre versus_battle --lang en --write-first
# LLM modes are fail-closed: --mode ollama (local), --mode cloud (OPENAI_API_KEY or DEEPSEEK_API_KEY),
# --mode deepseek (needs DEEPSEEK_API_KEY; model DEEPSEEK_MODEL, default deepseek-chat).
# Keys come only from environment variables; if the provider fails, templates are NOT substituted.
python scripts/idea_engine.py --topic "The Big Bang" --lang en --mode deepseek --write-first

# C) Clickable 1280x720 cover generator (Thumbnail Studio)
python scripts/thumbnail_studio.py --deck decks/dup-protocol-cosmos.json --badge "0 FLOAT · 48H PASS" --out out/cover.png

# D) Multi-format Video Pack (16:9 + 9:16 Short + translation + cover + combined QA manifest)
python scripts/video_pack.py decks/radar-pro.json --translate-to en --preset cinema_cosmos --plan-only
```

## Studio in the web console (`python scripts/console_server.py --open`)

All features are optional; the CLI (`build_deck.py`, `idea_engine.py`, `publish_pack.py`) works as before.

| Tab | What it does |
|---|---|
| 01 · New video | Build from a local folder or GitHub; Idea Engine with optional web search for fresh facts (LLM modes Ollama / Cloud only) |
| 02 · Editor | Drag-and-drop images and video (up to 100 MB) from Windows, from an https link, or from a search of Wikimedia / NASA / Openverse straight onto a slide; asset inspector with license info (CC BY / CC BY-SA are added to `_post_copy.md` automatically); timeline with slide reordering and voiceover preview; storyboard and master approval |
| 03 · Merge | Combine several MP4 files into one, with format and audio alignment |
| 05 · 3D Studio | Image-to-3D (Tripo3D / Fal.ai) and `.glb` preview in a Three.js viewport (rotate, zoom, grid) |

Keys are **only Windows user environment variables**, never files in the repository. Without a key the feature refuses explicitly (fail-closed); there is no substitution:

| Variable | Used for |
|---|---|
| `SERPER_API_KEY` or `BRAVE_API_KEY` | Web search for Idea Engine (Serper takes priority) |
| `TRIPO_API_KEY` or `FAL_KEY` | 3D model generation from an image |
| `DUP_LLM_API_KEY` / `DEEPSEEK_API_KEY` / `OPENAI_API_KEY` | Cloud LLM for plans and ideas |

```powershell
[Environment]::SetEnvironmentVariable("SERPER_API_KEY", "<key>", "User")
# the console picks up a new key from the registry without restart (refresh the page);
# for CLI scripts open a NEW PowerShell window
```

The console listens only on `127.0.0.1` and rejects requests with a foreign `Host` (DNS rebinding) and cross-site POSTs from other browser tabs.

## 12 visual themes (`theme`)

Single source of truth: `src/themes.ts` ↔ `scripts/theme_catalog.py`.

- **Dark:** `quantum_ledger` (concave cosmic 3D funnel, 22 transaction beams, concave shelves and floating text), `neon_cyber` (default), `cosmic_radar`, `terminal_green`, `deep_ocean`, `sunset_orange`, `cyber_magenta`, `aurora_purple`, `mono_graphite`.
- **Light:** `minimal_light`, `paper_warm`, `corporate_blue`.

## Caption styles (`caption_style`)

- `box` (default) — the whole line in a neat panel.
- `karaoke` — word-by-word highlight as the speech plays. Timing sources, in priority order:
  1. Russian Edge TTS voices (`WordBoundary`) give exact per-word timing from the TTS.
  2. English voices (Kokoro-82M, Silero EN) get exact timing from local recognition with `faster-whisper` (`base.en`, CPU).
  3. If the ASR package is not installed, words are estimated proportionally to their length, and the log says `estimated` explicitly (honest status, no faked result).
- `bold` — large white text with a shadow and no panel (for vertical 9:16 videos).

---

## Presentation from Markdown (no JSON)

```powershell
python scripts/md_deck.py examples/md-talk-demo.md --out decks/md-talk-demo.json
python scripts/build_deck.py decks/md-talk-demo.json --render
```

Supported types: `hero_3d`, `outro_3d`, `kpi`, `timeline`. An unclear line, an unknown key or an unsupported type gives a fail-closed refusal with the line number; no file is created.

---

## Quick start

```powershell
# Install dependencies
npm ci
pip install numpy scipy httpx playwright edge-tts kokoro-onnx faster-whisper

# Full build + render + -16 LUFS + Media QA + Publish Pack
python scripts/build_deck.py decks/radar-pro.json --render

# Quick preview of ONE slide (seconds instead of minutes)
python scripts/build_deck.py decks/radar-pro.json --only-slide s5 --render

# Save one PNG frame per slide without a full MP4 render
python scripts/build_deck.py decks/radar-pro.json --preview-stills

# Strict offline mode (Privacy Lock: no network TTS and no stock sources)
python scripts/build_deck.py decks/radar-pro.json --offline-only --render

# Audit the deck's facts against a real repository before the build
python scripts/claim_audit.py decks/radar-pro.json --repo C:\path\to\repo

# Make a vertical 9:16 Short (~50–60 s) from a 16:9 deck
python scripts/make_cutdown.py decks/radar-pro.json

# Translate a deck RU <-> EN (keeping code, numbers and URLs)
python scripts/translate_deck.py decks/radar-pro.json --to en

# Automatic capture of a clean UI / scenario with Playwright
python scripts/capture_ui.py --url http://127.0.0.1:8080 --out live_ui.png --focus-selector "table"
python scripts/record_ui.py --scenario <your-scenario>.json   # format: see the docstring in scripts/record_ui.py

# Start the local web console (Markdown import and caption_style selection supported)
python scripts/console_server.py --open

# Start the MCP server (stdio JSON-RPC 2.0 for Cursor / Claude)
python scripts/mcp_server.py

# Publish an MP4 (>100 MB) and the Publish Pack to a GitHub Release
python scripts/github_release_uploader.py --mp4 out/radar-pro.mp4 --repo Gruver87/dup-presenter --dry-run
```

## Pronunciation dictionary

Edit `config/pronunciation.json`, or use the web console API `GET/POST /api/pronunciation`.

## What is not published to Git

- `decks/dup-protocol.json`, `decks/dup-protocol-story.json`, `decks/dup-protocol-cosmos.json` and `decks/dup-protocol-cosmos-en.json` reference local screenshots in `public/screens/dup-protocol/` (listed in `.gitignore`). On a clean clone `deck_doctor` returns `missing screen file`, and rendering does not start (fail-closed).
- `out/` (MP4 renders and reports), `work/`, `public/voice/`, `public/music/`, `public/ui_recordings/`, `public/uploads/` (console uploads), `public/models3d/` (3D models), `models/` and `secrets/` are not committed to git.

## Tests and checks

```powershell
npx tsc --noEmit
python -m py_compile scripts/*.py
python -m unittest discover -s tests -v

# Live check of the web console in Chromium (the console must be running on the right port)
python scripts/console_server.py --port 8790 --no-auto-ollama
python scripts/console_ui_check.py --url http://127.0.0.1:8790/

# Live check of the 3D viewport: loading a real .glb (needs access to esm.sh for Three.js)
python scripts/glb_viewer_check.py --url http://127.0.0.1:8790/

# Click audit of the console: every visible button/checkbox on every tab is clicked once.
# POST/PUT/DELETE are intercepted and get a mock response (nothing is published or written); report: out/preview/click_audit.json
python scripts/console_click_audit.py --url http://127.0.0.1:8790/

# Backup of user data outside git (decks, work/ with licenses, uploads, 3D models; keys are not copied)
powershell -ExecutionPolicy Bypass -File scripts\backup_user_data.ps1 -Destination "D:\DUP_backup"
```

Current CI status: `npx tsc --noEmit`, `py_compile` and **Python unit/gate tests** (548 locally on Windows, including a live Playwright UI recording test; the Windows Credential Manager round-trip test is skipped on Linux) run on every push/PR in [`.github/workflows/ci.yml`](.github/workflows/ci.yml). Python test dependencies are pinned in [`requirements-dev.txt`](requirements-dev.txt).

## Documentation and the DUP Labs ecosystem

- **In this repository:** [ARCHITECTURE.md](docs/ARCHITECTURE.md) · [DECK_SCHEMA.md](docs/DECK_SCHEMA.md) · [CHANGELOG.md](CHANGELOG.md) · [CONTRIBUTING.md](CONTRIBUTING.md) · [SECURITY.md](SECURITY.md) · [CITATION.cff](CITATION.cff)
- **Related DUP Labs repositories:**
  - [`Gruver87/dup-protocol`](https://github.com/Gruver87/dup-protocol) — industrial L1 audit-pin (Python + Rust)
  - [`Gruver87/dup-protocol-experimental`](https://github.com/Gruver87/dup-protocol-experimental) — R&D sandbox for DUP Protocol
  - [`Gruver87/dup-market-radar`](https://github.com/Gruver87/dup-market-radar) — DUP Market Radar

## Licenses of third-party components

- **`dup-presenter` license**: MIT (see [`LICENSE`](LICENSE)). It covers the project's code and templates. It does not grant any rights to Remotion or other third-party components.
- **Disclaimer**: the software is provided "as is". The user is responsible for content, visual rights, keys and compliance with platform rules. See [`DISCLAIMER.md`](DISCLAIMER.md).
- **Remotion**: free license for individuals and teams of up to 3 people ([remotion.dev/docs/license/pricing](https://www.remotion.dev/docs/license/pricing)). Check Remotion's terms before commercial use.
- **Silero TTS v5** (MIT), **Kokoro-82M ONNX** (Apache-2.0), **faster-whisper** (MIT), **Edge TTS** (online Microsoft service).
