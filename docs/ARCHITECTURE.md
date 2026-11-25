# Architecture — DUP Presenter

DUP Presenter separates **declarative deck authoring & fail-closed validation (Python)** from **deterministic 3D frame rendering (TypeScript / React / Remotion 4)** and **broadcast audio mastering / verification (FFmpeg + Media QA Gate)**.

## End-to-End Pipeline

```text
decks/<slug>.json  (or examples/*.md via scripts/md_deck.py)
   │
   ▼  1. Schema & Fact Gates (fail-closed)
      scripts/build_deck.py · scripts/deck_doctor.py · scripts/claim_audit.py
      - Validates slide types, required fields, theme ID parity, local asset paths
      - Optional --audit-repo verifies deck claims against a target git repository
   │
   ▼  2. Voice Synthesis & Word Alignment
      scripts/tts_engines.py · scripts/edge_engine.py · scripts/ru_speech.py · scripts/audio_fx.py
      - RU: Edge Neural TTS (dmitry / svetlana) with real WordBoundary events; offline Silero v5 fallback
      - EN: Kokoro-82M v1.0 ONNX (am_michael / af_bella / ...) + local faster-whisper (base.en) ASR word alignment
      - Audio conditioning: STFT de-esser, silence trimming, speech-activity envelope for dynamic music ducking
      - Procedural SFX: transition whoosh + UI pop
   │
   ▼  3. Resolved Build Manifest
      src/generated/deck_resolved.json (gitignored, per-build)
      - Exact frame counts, audio paths, aligned word timings, resolved theme palette, aspect ratio
   │
   ▼  4. Deterministic 3D Video Render (Remotion 4)
      src/Root.tsx · src/Composition.tsx · src/StorySlides.tsx · src/CosmosBackdrop.tsx · src/themes.ts
      - TransitionSeries (fade / slide / wipe), 16:9 (1920x1080) or 9:16 (1080x1920)
      - 14 slide templates + 12 themes (including quantum_ledger concave warp & transaction light beams)
      - Caption presets: box | karaoke (word-by-word highlight) | bold
   │
   ▼  5. Broadcast Audio Mastering (FFmpeg)
      - Two-pass loudnorm to -16.0 LUFS / -1.5 dBTP (48 kHz AAC 320 kbps)
   │
   ▼  6. Fail-Closed Media QA Gate
      scripts/media_qa.py -> out/<slug>_qa.json
      - Checks H.264 video, AAC 48 kHz audio, exact resolution & duration, integrated LUFS (-16.0 ± 2.5),
        True Peak (<= -0.2 dBTP), and interior dead-air silence (<= 4.5s)
      - Non-zero hard_fails fails the build
   │
   ▼  7. Publish Pack & Distribution
      scripts/publish_pack.py -> .srt, .vtt, _chapters.txt, _post_copy.md, _metadata.json, _thumb.png
      scripts/github_release_uploader.py · scripts/tiktok_uploader.py
```

## Module Map

### Renderer (`src/`)
| File | Responsibility |
|------|----------------|
| `src/index.ts`, `src/Root.tsx` | Remotion entry point and composition registration (`DupPresenter`) |
| `src/types.ts` | TypeScript interfaces for resolved decks, all 14 slide types, captions, and word timings |
| `src/themes.ts` | Single TypeScript registry for all 12 visual palettes (`ThemeId`, `THEMES`) |
| `src/CosmosBackdrop.tsx` | `QuantumWarpBackdrop`: concave 3D tunnel, meridians, depth rings, nebulae, and 22 transaction light beams (with red fail-closed perimeter deflections) |
| `src/StorySlides.tsx` | `LedgerLayersSlide`, `TxJourneySlide`, `MeshNetworkSlide`, `ProtocolCosmosSlide` (both 16:9 and 9:16 layouts, inflated 3D shelves & floating typography in `quantum_ledger`) |
| `src/Composition.tsx` | Core slide renderers (`hero_3d`, `code_split`, `screen_split`, `ui_recording`, `arch_flow`, `kpi`, `timeline`, `terminal`, `quote`, `outro_3d`), 3D cube, transitions, captions, and audio tracks |

### Build, Audio, QA & Automation (`scripts/`)
| Group | Scripts |
|-------|---------|
| **Core build & validation** | `build_deck.py`, `deck_doctor.py`, `claim_audit.py`, `theme_catalog.py`, `media_qa.py`, `publish_pack.py` |
| **Speech & audio DSP** | `tts_engines.py`, `edge_engine.py`, `ru_speech.py`, `audio_fx.py`, `voice_clean.py`, `voice_bench.py`, `voice_samples.py`, `calibrate_speech.py` |
| **Authoring & planning** | `md_deck.py`, `plan_deck.py`, `make_project_deck.py`, `analyze_project.py`, `fetch_repo.py`, `translate_deck.py`, `make_cutdown.py`, `merge_videos.py`, `stock_media.py` |
| **UI capture & recording** | `capture_ui.py`, `record_ui.py` |
| **Interactive interfaces** | `console_server.py` (local web studio), `console_ui_check.py` (Playwright smoke check), `mcp_server.py` (stdio JSON-RPC 2.0 MCP server) |
| **Publishing** | `github_release_uploader.py`, `tiktok_uploader.py` |

## Fail-Closed Invariants

1. **Theme parity:** `scripts/theme_catalog.py` (`THEME_IDS`) and `src/themes.ts` (`ThemeId`) must stay in lockstep.
2. **No silent broken assets:** `build_deck.py` refuses missing screenshots or UI recordings before invoking Remotion.
3. **Honest caption timing:** Word alignment source (`WordBoundary` vs `faster-whisper` ASR vs `estimated`) and match percentage are always logged; estimated timing is never labeled as real word alignment.
4. **Broadcast QA gate:** Every rendered MP4 is verified by `media_qa.py`; `hard_fails > 0` fails the pipeline.
5. **Privacy Lock (`--offline-only`):** Blocks all outbound network TTS and stock media calls when local-only operation is required.
