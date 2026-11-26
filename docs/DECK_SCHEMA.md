# Deck Schema Reference (`decks/*.json`)

Every presentation in DUP Presenter is defined by a declarative JSON deck validated fail-closed by `scripts/build_deck.py` and `scripts/deck_doctor.py`.

## Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `slug` | `string` | Yes | Output identifier (`out/<slug>.mp4`, `_qa.json`, `.srt`, `.vtt`, etc.) |
| `lang` | `"ru" \| "en"` | Yes | Narration and UI label language (`ГАРАНТИЯ:` vs `GUARANTEE:`) |
| `theme` | `ThemeId` | Yes | One of the 12 themes in `scripts/theme_catalog.py` / `src/themes.ts` |
| `aspect` | `"16:9" \| "9:16"` | No | Video aspect ratio (default `"16:9"`, `1920×1080`; `"9:16"` = `1080×1920`) |
| `brand` | `string` | No | Top-left brand badge text (e.g. `"DUP LABS"`) |
| `burn_captions` | `boolean` | No | Enable burned-in captions (default `true`) |
| `caption_style` | `"box" \| "karaoke" \| "bold"` | No | Caption preset (`"box"` default, `"karaoke"` word highlight, `"bold"` vertical) |
| `transition_style` | `"fade" \| "slide" \| "wipe"` | No | Remotion `TransitionSeries` style |
| `transition_frames` | `number` | No | Transition overlap duration in frames (at `fps: 30`) |
| `sfx_enabled` | `boolean` | No | Procedural transition whoosh and UI pop SFX |
| `sfx_volume` | `number` | No | SFX gain (`0.0–1.0`, e.g. `0.16`) |
| `music` | `object` | No | `{ "enabled": true, "file": "track.mp3", "volume": 0.1, "duck_db": -10.5 }` |
| `voice` | `object` | Yes | `{ "engine": "edge_tts" \| "kokoro_v1" \| "silero_v5_ru", "lang": "ru" \| "en", "speaker": "...", "speaker_b": "..." (podcast only), "rate": "96%", "mode": "single" \| "podcast" }`. `mode: "podcast"` = two-voice dialogue (`speaker` = A, `speaker_b` = B, optional per-slide `dialogue: [{ speaker: "A" \| "B", text }]`). Any other value falls back to single-voice narration. |
| `director_preset` | `string` | No | One of `cinema_cosmos`, `fast_shorts`, `documentary`, `news_flash`, `tech_pitch` (see `scripts/director_presets.py`). Applied by `build_deck.py` before validation with `override_existing=False`: explicit deck keys always win. Unknown preset = fail-closed error. |
| `slides` | `Slide[]` | Yes | Ordered array of slide objects |

## Supported Themes (`theme`)

- **Dark:** `neon_cyber` (default), `quantum_ledger` (concave 3D warp + transaction light beams + inflated 3D shelves), `cosmic_radar`, `terminal_green`, `deep_ocean`, `sunset_orange`, `cyber_magenta`, `aurora_purple`, `mono_graphite`
- **Light:** `minimal_light`, `paper_warm`, `corporate_blue`

## Supported Slide Types (`slide.type`)

Every slide requires `id`, `type`, `title`, and `voice_text` (or explicit timing). Optional common fields: `tag`, `subtitle`, `duration_sec`, `voice_delay_sec`.

| `type` | Purpose | Required Type-Specific Payload |
|--------|---------|--------------------------------|
| `hero_3d` | Opening title slide with gradient typography, badges, and rotating 3D cube | `pills` (optional), `cube_faces` (6 strings, optional) |
| `outro_3d` | Closing slide with repository URL, badges, tagline, and 3D cube | `url`, `tagline` (optional), `badges` (optional), `cube_faces` (optional) |
| `code_split` | Split-screen: left bullet cards, right 3D code window with line animation | `bullets`, `code: { filename, lines: [{ text, color }] }` |
| `screen_split` | Split-screen with real screenshots and virtual auto-zoom camera | `bullets`, `screens: [{ src, caption, focus?: { x, y, zoom } }]` |
| `ui_recording` | Live Playwright UI recording clip embedded as a 3D video slide | `recording: { src, caption? }` (clip duration probed via `ffprobe`) |
| `arch_flow` | 3D architecture pipeline with animated packet flow | `nodes`, `links` / flow payload |
| `kpi` | Key metric cards (1–4 items; floating numbers & concave angling in `quantum_ledger`) | `kpis: [{ value, label }]` (1–4 items) |
| `timeline` | Step-by-step pipeline or roadmap (2–6 steps) | `steps: [{ title, desc, ... }]` (2–6 items) |
| `terminal` | Animated terminal output window | `terminal` / command output lines |
| `quote` | Single highlighted quote card with attribution | `title` (<= 220 chars), optional `subtitle` |
| `ledger_layers` | 3D isometric stack of architecture layers with per-layer guarantee banner | `layers: [{ id, name, tech, desc, guarantee, accent? }]` (3–6 items) |
| `tx_journey` | Animated transaction lifecycle: Merkle tree folding, `prev_hash` block chain, RocksDB seal | `journey: { tx_label, amount_label, signature_label, merkle_leaves[4], blocks[3..5], steps[3..6] }` |
| `mesh_network` | 3–4 node P2P mesh topology with propagation pulses, probes, and recovery cards | `mesh: { protocol_label, chain_id, probe_label, nodes[3..4], recovery_steps[2..4] }` |
| `protocol_cosmos` | Central holographic crypto reactor + 6 angled 3D stations + optical conduits + red fail-closed shield | `cosmos: { core_title, core_subtitle, core_badges[2..4], stations[6] (3 left + 3 right, unique ids) }` |
| `versus_split` | A vs B 3D comparison columns with pulsing `VS` center and optional verdict | `versus: { left: { label, points[2..5] }, right: { label, points[2..5] }, verdict? }` |
| `chart_story` | Animated `bar` / `line` / `donut` chart with spring-grown values | `chart: { kind: "bar" \| "line" \| "donut", series[2..8] of { label, value >= 0, display?, color? }, unit?, source_note? }` |
| `stat_burst` | High-impact hook slide (giant floating headline + energy ring), for the first 3–5 seconds | `stat_burst: { headline (1..24 chars), kicker?, caption, chips? (<= 3) }` |
| `broll_cinematic` | Full-bleed cinematic Ken Burns slide with vignette and thesis callouts | `broll: { image? (safe relative path, no ".."), badge?, caption?, callouts? (0..3) }` |
| `cinema_clip` | Full-screen cinematic scene (single clip or multi-shot sequence of videos & Ken Burns stills, no chrome) | `cinema: { src? \| shots?[1..8], badge?, loop? (default true), crossfade_frames? (0..30, default 12), zoom? (1.0..1.5), start_sec?, end_sec?, playback_rate? (0.25..2.0), audio_volume? (0..1, auto-ducked; clip must have audio stream), letterbox?, grade? ("none" \| "cinema_warm" \| "cinema_cold" \| "noir" \| "vivid") }`; each shot supports `{ src, kind?, duration_sec?, start_sec?, end_sec?, playback_rate?, zoom?, pan_x?, pan_y?, audio_volume? }`; without `src`/`shots` a `background_query` is required |

### Per-Slide SFX Cues (any slide type)

Any slide may declare `sfx: [{ src | name, at_sec, volume?, duration_sec? }]` (0..8 cues). Each cue has **exactly one** of:
- `src`: a safe relative audio path under `public/` (`.wav`, `.mp3`, `.ogg`, `.m4a`, `.flac`) that must exist on disk;
- `name`: an effect from the named SFX library (`scripts/sfx_library.py`): `whoosh`, `pop`, `impact`, `tick`, `riser`, `ding`. Library files are synthesized locally and deterministically into `public/sfx/library/` (gitignored, with `manifest.json` sha256s); `build_deck` resolves `name` to `src` before validation. Unknown names are refused.

Playback is automatically ducked under speech.

## Cinema Video Engine (`media_engine`)

Optional top-level field. `"offthread"` (default) keeps Remotion `OffthreadVideo` for cinema clip shots. `"media"` uses `@remotion/media` (`Video`) with `disallowFallbackToOffthreadVideo` set, so a decode failure fails the render instead of switching engines silently. Measured on the same deck (`big-bang-cinema-real`, 12 frames, 0–170 s): the two engines produce the same scene and layout but are **not bit-identical**: PSNR 20–26 dB, differences in fine nebula texture (mean abs diff 5.8–13.3 on a 0–255 scale). Full-resolution check (1920x1080 stills, 8 frames, first two cinema slides, `work/ab2_analyze.py`, dev tool): same timing (source index advances 1:1 with film time), mean RGB delta media−offthread = (−0.34, +0.28, +1.39) on 0–255, laplacian mean |L| offthread 15.76 vs media 16.38 (+3.9%), and media is further from the bicubic-scaled source in every frame (MAE 19.2 vs 17.6). The higher high-frequency energy cannot be attributed to better detail without a reference; it may equally be sharpening or noise. Decision: **keep `offthread` as the default for masters**. `media` stays an opt-in path with fallback disabled and has no measured quality advantage here.

## Named SFX Library (`scripts/sfx_library.py`)

Procedural, project-generated effects with no third-party audio (so no licence to track). Fixed RNG seed: the same bytes on every machine. `public/sfx/library/manifest.json` records schema, sha256, duration and origin for each file. Covered by `tests/test_sfx_library.py` (11 offline tests) and `scripts/verify_stage5_sfx_split.ps1`.

## Storyboard Approval Gate (`scripts/storyboard_gate.py`, console)

Master MP4 is gated behind a human-approved storyboard. The chain is: draft render (`--draft`, records the deck sha256, the draft sha256 and the slide timings in `work/<slug>/storyboard/draft_meta.json`) → storyboard (one still per slide from the draft, `index.json`, with the visual licence and source from the visual plan) → approval (`approval.json` binds the deck sha256 and the draft sha256). A master render with `--require-storyboard` is refused unless that approval matches the current deck and the current draft. Any deck edit or new draft invalidates it. The console always passes `--require-storyboard` for master renders and uses drafts for generation, feedback and "save edits". Ungated paths: direct CLI calls without `--require-storyboard`, `mcp_server.py` renders and `--skip-tts` / `--only-slide` masters (refused when gated). Covered by `tests/test_storyboard_gate.py` (17 offline tests) and `scripts/verify_stage4_storyboard.ps1 -Live`.

### Build Quality & Draft Preview (`scripts/build_deck.py`)

- `--crf <14..32>`: H.264 CRF quality (default `20` for master renders; `26` for `--draft`).
- `--draft`: Fast `0.5×` preview render to `out/<slug>_draft.mp4` + `out/<slug>_draft_qa.json` (`"draft": true`), without overwriting the master `out/<slug>.mp4` or generating a publish pack.

## Director Script → Deck (`scripts/director_script.py`)

Generates a deck from a topic with DeepSeek (env `DEEPSEEK_API_KEY` or `DUP_LLM_API_KEY`; https base only):

```powershell
python scripts/director_script.py --topic "..." --minutes 3 --lang ru --overwrite
python scripts/director_script.py --script-file work/director_scripts/<slug>.json --overwrite   # offline re-validation
```

- `--minutes` 1–10; ≤150 s per act, ≤4 acts. Timing must be within ±15 % of the request; speech ≤3.0 words/sec.
- Visual types for LLM output: `cinema_clip`, `broll_cinematic`, `stat_burst`, `kpi`. `quote` is refused for LLM output.
- Stock queries: 2–60 latin letters/spaces/hyphens (`stock_media.validate_query`).
- Outputs: `decks/<slug>.json` (validated with `validate_deck`) and `work/director_scripts/<slug>.json` (carries `fact_status: "unverified_llm_output"`; the facts and numbers are not verified).
- Exit codes: 0 success, 1 fail-closed generation/validation/IO error, 2 bad arguments.

## Visual Sourcing (`scripts/visual_sourcing.py`)

Fills `cinema_clip` and `broll_cinematic` slides with media from free, keyless archives. No API keys are used.

```powershell
python scripts/visual_sourcing.py search --query "nebula" --kind any
python scripts/visual_sourcing.py plan   --script work/director_scripts/<slug>.json
python scripts/visual_sourcing.py fetch  --plan work/visual_sources/<slug>/plan.json
python scripts/visual_sourcing.py apply  --plan work/visual_sources/<slug>/plan.json --deck decks/<slug>.json --overwrite
```

- Sources: NASA Images, Wikimedia Commons, Internet Archive, Openverse (images only). Topics are not limited to space.
- Licences accepted: CC0, Public Domain Mark, CC BY, CC BY-SA, NASA media guidelines. NC, ND, unknown and missing licences are rejected.
- Formats: images `.jpg/.jpeg/.png/.webp` (1280 px or larger on the long side, at least 720 px on the short side, at most 8192 px); video `.mp4/.webm` (1280x720 or larger, 1 to 120 s).
- Asset files are checked by magic bytes and real decode/probe after download. A content-type of HTML or JSON is refused.
- `apply` sets `cinema.src` (and removes `background_query`, so no hidden stock dependency remains) for `cinema_clip`, and `broll.image` for `broll_cinematic`. `stat_burst` and `kpi` are graphic slides and are skipped.
- A `cinema_clip` without media fails closed, even with `--allow-missing`. `--allow-missing` only relaxes `broll_cinematic`.
- Attribution is written to `out/<slug>_visual_credits.txt`. **Known gap:** the credit is not yet rendered on screen. CC BY and CC BY-SA require attribution, so the on-screen credit must be added before publication.
- Dependencies: Pillow (image probe) and ffprobe (video probe) are required. The project has no requirements file yet.

## Per-Slide Minimum Duration (`min_duration_sec`)

Optional, number in `1..120`. The slide keeps at least this many seconds even if its narration is shorter. Without it, the slide length follows the narration alone and the film can end up shorter than planned.

## Markdown Authoring (`scripts/md_deck.py`)

For quick decks without JSON, write Markdown with slide directives (`hero_3d`, `outro_3d`, `kpi`, `timeline`) and convert fail-closed:

```powershell
python scripts/md_deck.py examples/md-talk-demo.md --out decks/md-talk-demo.json
```

Unknown keys, malformed lines, or unsupported slide types abort with the exact line number and write no output file.
