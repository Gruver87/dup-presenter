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
| `voice` | `object` | Yes | `{ "engine": "edge_tts" \| "kokoro_v1" \| "silero_v5_ru", "lang": "ru" \| "en", "speaker": "...", "rate": "96%", "mode": "single" \| "duo" }` |
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

## Markdown Authoring (`scripts/md_deck.py`)

For quick decks without JSON, write Markdown with slide directives (`hero_3d`, `outro_3d`, `kpi`, `timeline`) and convert fail-closed:

```powershell
python scripts/md_deck.py examples/md-talk-demo.md --out decks/md-talk-demo.json
```

Unknown keys, malformed lines, or unsupported slide types abort with the exact line number and write no output file.
