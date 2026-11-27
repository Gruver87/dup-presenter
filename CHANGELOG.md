# Changelog

All notable changes to **DUP Presenter** are documented in this file. Dates and versions match actual commits and verified runs on disk.

## [Unreleased]

### Changed (publish gate, pending state, LinkedIn copy, aspect guard)
- **Media QA is bound to the exact file** (`scripts/media_qa.py`): every QA report now records the MP4's `sha256` and byte size. `qa_binding_error()` refuses an upload when the report is missing, unreadable, has no hash (reports written before this change), describes a different size or hash, or has a hard failure. The TikTok uploader runs this gate before any token or network call, dry runs included. Covered by `tests/test_media_qa_binding.py`.
- **Re-QA needed for existing masters**: the Russian and English Director's Cut MP4s on disk were QA'd before this change, so the gate refuses them until media QA is run again on the same file (or the master is rebuilt).
- **Audited verification** (`scripts/tiktok_uploader.py`): every status check appends a row (`verification`, `status_check`, `recheck`) to `work/tiktok_publish_audit.jsonl` with the TikTok status, verified flag and poll count. Upload rows gained `event: "upload"`; older rows without the field count as uploads.
- **PENDING state for accepted-but-unconfirmed uploads**: an upload TikTok accepted but has not finished processing exits with code 3 (`EXIT_PENDING`), not 1. The console shows it as `pending`, not `error`. `--list-pending` and `--recheck-pending` re-query uploads the audit log has not settled; the console has a "Проверить ожидающие TikTok" button that runs the recheck as a job. Covered by `tests/test_tiktok_pending.py`.
- **LinkedIn copy in every publish pack** (`scripts/linkedin_copy.py`, `scripts/publish_pack.py`): `out/<slug>_linkedin.md` holds a post and a first comment, with their lengths checked against 3,000 and 1,250 characters. Over-limit text is flagged, not truncated. QA facts appear only for a report that passed. The copy is English and generic: it has no slug or brand fallback for the headline and no repository link unless the deck's last slide has a `url`. Covered by `tests/test_linkedin_copy.py`.
- **Aspect change needs confirmation** (`scripts/console_server.py`, `scripts/console_ui.html`): `/api/save-deck` refuses a changed `aspect` unless `confirm_aspect_change` is true, before writing anything. The console asks for confirmation before sending a changed format. Covered by `tests/test_console_aspect_guard.py`.
- **Publish-gate smoke** (`scripts/smoke_publish_gate.py`): real ffmpeg, a 4-second synthetic MP4, no TTS, Remotion or network. It checks QA pass, binding, the TikTok gate, refusal after a one-byte change, and the LinkedIn file. Run as `tests/test_smoke_publish_gate.py`. This is not a full render and does not replace a real master build.
- **Not done in this change**: the pacing feature is still not enabled by any deck (enabling it changes approved voices and needs a measured TTS run). The 16:9 end cards are rendered by scripts outside this repository and are not on the shared visual tokens.

### Changed (pipeline hardening: media QA, encode, pacing, publish verification)
- **Media QA video gates** (`scripts/media_qa.py`): black spans longer than 0.6 s inside a film fail (`no_black_frames`, hard), frozen pictures over 6 s warn (`no_long_freeze`, soft), and pixel format, bitrate ceiling (16 Mbps) and frame rate (30 fps) are hard gates. The ffmpeg used must provide `blackdetect` and `freezedetect`; otherwise QA fails closed. Covered by `tests/test_media_qa_video.py`.
- **Cinema coverage check** (`scripts/deck_doctor.py`): a `loop=false` cinema slide whose shots end before the slide ends is flagged. It is a **warning** because it works on word-count estimates, which run 2-5 s above real narration. Real black tails are caught by the rendered-output gate above. `playback_rate` is now honoured for single-`src` clips.
- **Broadcast encode in the pipeline** (`scripts/broadcast_encode.py`): every render (master and draft) is re-encoded to H.264 High@4.1, yuv420p, BT.709, maxrate 12M, GOP 60, 30 fps, faststart, with audio copied, before loudness and QA. Vertical teasers use the same module with maxrate 10M. Verified on a real 16:9 render: yuvj420p to yuv420p, 5.07 to 3.86 Mbps, no black or freeze. Fractional `playback_rate` values get a doctor warning (`fractional_rate_warnings`).
- **Source decks are no longer written by validation** (`scripts/build_deck.py`): `validate_deck` is pure. The build pipeline uses `prepare_deck`, which annotates a copy (`kind`, `clip_duration_sec`) that goes only into the resolved deck. Previously validation put these fields into the source deck through the console save path. Covered by `tests/test_deck_pure_validation.py`.
- **Automatic pacing** (`scripts/pacing.py`, `scripts/build_deck.py`): a deck may set `"pacing": {"target_wpm": N, "tolerance": 0.04, "min_rate_pct": 70, "max_rate_pct": 110}`. Each plain single-speaker slide is measured and re-synthesized at most twice, with the rate clamped. The rate used and the measured wpm are written per slide to the resolved deck. Slides with `voice_ssml` keep their own rate and are reported. Podcast mode is not paced. No deck opts in yet. Covered by `tests/test_pacing.py` (fake synthesizer, no real TTS).
- **TikTok publish verification** (`scripts/tiktok_uploader.py`): after an upload the publish status is polled (`/v2/post/publish/status/fetch/`) until `SEND_TO_USER_INBOX` or `PUBLISH_COMPLETE`. `FAILED` is reported with its reason. A timeout or unknown state is **not** reported as verified. New CLI: `--check-publish <publish_id>`, `--verify-wait-sec`. Covered by `tests/test_tiktok_publish_status.py`. The live status endpoint was not called in this change.
- **Verified release publish** (`scripts/github_release_uploader.py`): a SHA-256 manifest (`<stem>_release_manifest.json`) is written and uploaded with the assets. Same-named assets are refused unless `--replace` is given (which alone enables `--clobber`). After upload, the release is queried and every local file must be present with the same size. Covered by `tests/test_release_publish.py` with a scripted `gh`. Not run against a live release in this change.
- **Shared visual tokens** (`scripts/visual_tokens.py`): TikTok outro cards take background, text, muted text, panel and font stacks from one module that mirrors `THEMES.neon_cyber`. Drift from `src/themes.ts` fails `tests/test_visual_tokens.py`. Outro panels move to the theme card colour (alpha 0.72 instead of 0.86), so re-rendered outros will look slightly different. The 16:9 end cards are still rendered by scripts outside this repo and are not yet on these tokens.
- **Console refusals drain the request body** (`scripts/console_server.py`): the 403 guard (Host, Origin, Sec-Fetch-Site) reads the unread body before replying and closes the connection. Previously Windows could reset the socket and the client saw `ConnectionAbortedError` instead of the 403, which made `tests/test_console_dashboard.py::test_cross_site_and_dns_rebinding_requests_refused` flaky under load. Six isolated runs and two full-suite runs (374 passed) were green after the change.

### Added
- **Interactive Studio — Iteration 1 (HTML5 Drag-and-Drop, Asset Inspector, Free Archive Search & Idea Engine Web Search)** (`scripts/asset_store.py`, `scripts/web_search.py`, `scripts/idea_engine.py`, `scripts/publish_pack.py`, `scripts/console_server.py`, `scripts/console_ui.html`):
  - **Drag-and-Drop & Asset Store**: slide cards (`cinema_clip`, `broll_cinematic`, `screenshot`) have native HTML5 drop zones accepting local Windows files (binary upload up to 100 MB into gitignored `public/uploads/<slug>/`), `https://` links, and draggable cards from the built-in archive search. Magic-byte + PIL/ffprobe validation, smart binding (`cinema.src` for video, `cinema.shots` for image on `cinema_clip`, `broll.image` on `broll_cinematic`), per-deck `work/<slug>/assets_meta.json` automatically read by `publish_pack.py` for CC BY / BY-SA credits.
  - **Asset Inspector & Free Archive Search**: inspect resolution/size/format/license, edit attribution metadata inline, and search Wikimedia / NASA / Openverse right inside the console and drag results onto slides.
  - **Promoted Director Presets**: preset selector (`cinema_cosmos`, `fast_shorts`, `documentary`, `news_flash`, `tech_pitch`) moved to the top bar of the Editor tab.
  - **Idea Engine `--web-search`**: optional flag in `scripts/idea_engine.py` and checkbox in the console using `SERPER_API_KEY` or `BRAVE_API_KEY` (fail-closed when no key is set or in template mode). Covered by `tests/test_web_search.py` (5 tests) and `tests/test_console_dnd.py` (3 tests).
- **Interactive Studio — Iteration 2 (Timeline & 3D Studio)** (`scripts/studio_3d.py`, `scripts/console_server.py`, `scripts/console_ui.html`, `tests/test_timeline_and_3d.py`):
  - **Timeline**: horizontal draggable slide strip in Tab 02 (`POST /api/slides/reorder`, fail-closed exact permutation check) with aligned real voice WAV amplitude waveform bars and inline ▶ audio audition (`GET /voice/<slug>/<sid>.wav`).
  - **3D Studio (`05 · 3D Studio`)**: Image-to-3D backend (`TRIPO_API_KEY` / `FAL_KEY`, fail-closed 503 when unconfigured), offline `.glb` drag-and-drop upload (`public/models3d/`, gitignored, 50 MB cap, `glTF` magic-byte check), and interactive Three.js + `OrbitControls` + `GLTFLoader` viewport. Covered by `tests/test_timeline_and_3d.py` (4 tests).
- **Visual credits in the publish pack** (`scripts/publish_pack.py`): `out/<slug>_post_copy.md` gets a "Источники визуалов" / "Visual credits" section listing every assigned visual under CC BY or CC BY-SA (creator, title, licence, licence URL, source page), read from `work/visual_sources/<slug>/plan.json`. CC0 and PDM need no credit and are not listed. Covered by `tests/test_publish_credits.py` (3 offline tests).

### Added
- **CI and dependency hygiene**: `requirements-dev.txt` pins the test dependencies (numpy, scipy, httpx, playwright, pillow, ruff). Previously CI installed no Pillow, so `test_console_dnd`, `test_timeline_and_3d` and `test_visual_sourcing` failed to import on every push to `main`. CI now installs from the pinned file and runs `ruff check --select F` (undefined names, unused imports). Verified in a clean virtualenv built from the pinned file: 324 tests OK.
- **`scripts/console_click_audit.py`**: clicks every visible button and checkbox in every console tab once. Requests to `/api/` are intercepted and mocked, so nothing is published or written. Each control is reported as `api` (sent a request), `ui-only`, `failed` or `skipped` with a reason. Verified: `RESULT: PASS`, 0 failed, 0 5xx. Controls that call external services (arc search) are reported as skipped, not as passing.
- **`scripts/glb_viewer_check.py`**: live check of the 3D Studio viewport. Uploads a real glTF 2.0 triangle, loads it in Three.js and checks the success status and absence of page errors. Verified: `RESULT: PASS`.
- **`scripts/backup_user_data.ps1`**: copies `decks/`, `work/` (licence and attribution records, storyboard approvals), `public/uploads/` and `public/models3d/` to a timestamped folder outside the repo. `secrets/` and `.env` are never copied. Verified on a temporary destination.
- **`DISCLAIMER.md`**: software is provided AS IS (MIT); the user is responsible for content, third-party asset rights, API keys and platform rules; forks and contributions terms. Linked from README and `CONTRIBUTING.md`. `LICENSE` text is unchanged.
- **TikTok licence gate** (`scripts/asset_store.py`, `scripts/console_server.py`): `/api/tiktok/upload` refuses (409, `unlicensed` list) when a deck uses an uploaded asset whose licence is `unknown` or empty. Only files with a metadata record are checked; hand-placed files under `public/` are not. Covered by `test_tiktok_blocked_until_uploaded_asset_has_licence`.

### Security
- **Console CSRF / DNS-rebinding guard** (`scripts/console_server.py`): every request must carry `Host: 127.0.0.1:<port>` or `localhost:<port>`; POSTs with a foreign `Origin` (including `null`) or `Sec-Fetch-Site: cross-site` are refused with 403. Previously any open web page could send a "simple" `text/plain` POST (no CORS preflight) that the server parsed as JSON — enough to overwrite decks, start renders or trigger `/api/tiktok/upload`. Covered by `tests/test_console_dashboard.py::test_cross_site_and_dns_rebinding_requests_refused`.
- **Fal.ai key leak guard** (`scripts/studio_3d.py`): `status_url` / `response_url` from the queue response receive the `Authorization` header, so they must start with `https://queue.fal.run/`; anything else is refused before a request is sent. Covered by `test_fal_queue_urls_outside_fal_host_are_refused`.
- **https-only after redirects** (`scripts/asset_store.py`, `scripts/studio_3d.py`): URL downloads now check the final URL after redirects, not only the initial one.

### Fixed
- **Corrupt `assets_meta.json` no longer wipes attribution** (`scripts/asset_store.py`): a malformed file used to load as `{}`, and the next upload or metadata save overwrote it, silently dropping CC BY credits for every other asset. It now raises `AssetStoreError` (HTTP 400) and leaves the file untouched; a malformed visual plan likewise raises instead of hiding licence info. Inspector shows ffprobe/PIL failures (`probe_error`) instead of silent `0×0`. Covered by `test_corrupt_assets_meta_refuses_instead_of_overwriting`.
- **Studio buttons silent without a deck** (`scripts/console_ui.html`): Советчик, Авто-исправить, Обложка, Short, Media QA, Video Pack, Feedback and Save returned without any message when no deck was selected. They now state what is missing (`requireSlug`). Verified in a browser with no deck selected.
- **QA LUFS shown as "?"** (`scripts/console_server.py`, `scripts/console_ui.html`): the console read top-level `lufs`, but `media_qa` writes `audio.integrated_lufs` / `audio.true_peak_dbtp`; fixed in the file panel and the Media QA button.
- **Web search toggle** (`scripts/console_ui.html`): disabled in "offline templates" mode, where the server refuses web search.
- **Provider keys without relaunch** (`scripts/console_server.py`): `SERPER_API_KEY`, `BRAVE_API_KEY`, `TRIPO_API_KEY`, `FAL_KEY` are refreshed from the Windows User environment like `DUP_LLM_*`, so a newly set key works after a page reload.
- **Console dashboard reliability & gates** (`scripts/console_server.py`, `scripts/console_ui.html`, `tests/test_console_dashboard.py`):
  - Fixed a `TypeError` crash on `/api/video-pack/build` (`JOBS.start` argument mismatch) and added upfront fail-closed storyboard gate check (409 when unapproved).
  - Fixed `/api/save-deck` overwriting `deck.music.file` and custom `volume` (and extra `background` fields) when saving edits.
  - Gated `/api/tiktok/upload` fail-closed (409) for deck-backed MP4s unless the storyboard is approved for the current deck (merged MP4s without a deck remain uploadable).
  - Exposed full Publish Pack exports (`_post_copy.md`, `_chapters.txt`, `_visual_credits.txt`, `_cover.png`, `_qa.json`, `_draft.mp4`) + one-click post copy, Media QA, Short 9:16 cutdown, and Save-Only buttons in the UI; fixed undefined `--bg2`, dimmed disabled buttons, and added status chip tooltips. Verified with `tests/test_console_dashboard.py` (6 tests) and Playwright `scripts/console_ui_check.py` (`RESULT: PASS`, 0 page errors).
- **`@remotion/media` engine warning** (`src/composition/sceneVideo.tsx`): `objectFit` is passed as a prop instead of `style.objectFit`, which logged a warning per tab. Verified with `verify_stage5_sfx_split.ps1 -Live`: no warning, media-engine draft passes Media QA.
- **Off-topic visual in the Big Bang film** (`work/visual_sources/bolshoy-vzryv-kak-iz-odnoy-tochki-voznikla-vselenn-1min/plan.json`, scene `a1s01`): a Kingdom Hearts game map matched the word "Universe" and was replaced with the public-domain painting "Big bang" (PDM, no credit needed).

- **Storyboard approval gate (Stage 4)** (`scripts/storyboard_gate.py`, `scripts/build_deck.py`, `scripts/console_server.py`, `scripts/console_ui.html`): drafts record the deck and draft hashes; the console builds one frame per slide, shows the visual licence and source, and enables "master MP4" only after a human approves. Any deck edit or new draft invalidates the approval. Generation, feedback, "save edits" and Video Pack now build drafts or pass `--require-storyboard`. Covered by `tests/test_storyboard_gate.py` (17 offline tests) and `scripts/verify_stage4_storyboard.ps1 -Live` (real draft render, gate refusals, console HTTP probes, approval invalidation).
- **Named SFX library (Stage 5, part 1)** (`scripts/sfx_library.py`, `scripts/build_deck.py`): slide cues may use `name` (`whoosh`, `pop`, `impact`, `tick`, `riser`, `ding`) instead of `src`; effects are synthesized deterministically into `public/sfx/library/` and resolved before validation. Covered by `tests/test_sfx_library.py` (11 offline tests).
- **`@remotion/media` as an opt-in cinema video engine (Stage 5, part 3)** (`scripts/build_deck.py`, `src/composition/sceneVideo.tsx`, `src/UniversalSlides.tsx`, `src/types.ts`): new optional deck field `media_engine` (`"offthread"` default, or `"media"`). The cinema clip shots use a `SceneVideo` wrapper; the default path renders the same bytes as before (6 reference frames SHA256-identical). `"media"` sets `disallowFallbackToOffthreadVideo`, so it cannot fall back silently. A/B on the same deck: the engines are not bit-identical (PSNR 20–26 dB, fine texture differences; same scene and layout). Covered by `tests/test_media_engine.py` and `scripts/verify_stage5_sfx_split.ps1 -Live`. `@remotion/three` is deferred (needs a WebGL render check).
- **Split `src/Composition.tsx` (Stage 5, part 2)** into `src/composition/` (`deckContext.ts`, `cosmicBackdrop.tsx`, `aurora3d.tsx`, `primitives.tsx`, `slides3d.tsx`, `captions.tsx`, `stockBackdrop.tsx`). The entry file is now 246 lines. Verified as a pure refactor: six reference frames are byte-identical (SHA256) before and after, and `tsc --noEmit` passes. Covered by `scripts/verify_stage5_sfx_split.ps1`.
- **`cinema_clip` v2 cinematic scene engine** (`scripts/build_deck.py`, `src/UniversalSlides.tsx`, `src/Composition.tsx`, `src/types.ts`): full-screen single clip or multi-shot sequence (`cinema.shots[1..8]`, mixing video clips and Ken Burns still images), zero-dip dissolve crossfades between shots and on loops (`crossfade_frames`), trim (`start_sec`/`end_sec`), slow-mo/speed (`playback_rate`), optional auto-ducked native clip audio (`audio_volume`, fail-closed if clip has no audio track), color grading (`grade`), and 2.39:1 `letterbox` bars.
- **Per-slide SFX cues (`slide.sfx[]`)** (`scripts/build_deck.py`, `src/Composition.tsx`, `src/types.ts`): timed audio cues under `public/` on any slide type, auto-ducked under speech, validated fail-closed.
- **H.264 `--crf` quality control & fast `--draft` preview mode** (`scripts/build_deck.py`, `scripts/media_qa.py`, `scripts/deck_doctor.py`, `scripts/console_server.py`): default master `--crf 20` (reduces 1080p MP4 bloat), `--draft` renders `0.5×` preview to `out/<slug>_draft.mp4` + `out/<slug>_draft_qa.json` (`"draft": true`) without touching master MP4. Covered by `tests/test_cinema_clip.py` (18 tests).
- **`deepseek` LLM mode in the Idea Engine** (`scripts/idea_engine.py`): `--mode deepseek` (key `DEEPSEEK_API_KEY` or `DUP_LLM_API_KEY`, model `DEEPSEEK_MODEL`/`DUP_LLM_MODEL`, default `deepseek-chat`, base `https://api.deepseek.com/v1`, `max_tokens: 8192`). `--mode cloud` picks DeepSeek when only `DEEPSEEK_API_KEY` is set. Covered by `tests/test_deepseek_mode.py` (8 mocked tests) and live-verified against `api.deepseek.com/v1` (`count=3` → 3/3 validated decks).

- **Director Script engine (`scripts/director_script.py`)**: turns a topic into a 1–10 minute multi-act script with a per-act scene plan (≤150 s per act, ≤4 acts, ≤14 scenes per act), validated timing (±15 % of requested length), speech rate (≤3.0 words/sec), language (ru/en, script-language match), visual types (`cinema_clip`, `broll_cinematic`, `stat_burst`, `kpi`), and stock queries (latin only). Output is a `build_deck` deck plus a script JSON with `fact_status: "unverified_llm_output"`. Schema errors are repaired by feeding the error back to DeepSeek (max 4 attempts per act); transport errors (HTTP, network, missing key, truncated output) are never retried. Quote slides are not allowed for LLM output (no unverifiable attributions). Covered by `tests/test_director_script.py` (33 offline tests) and `scripts/verify_stage2_director.ps1` (`-Live` runs one real 1-min DeepSeek call into `work/`).
- **Visual sourcing layer from free archives (Stage 3)** (`scripts/archive_sources.py`, `scripts/visual_sourcing.py`): per-scene search across four keyless public archives: **NASA Images**, **Wikimedia Commons**, **Internet Archive** and **Openverse** (general photos, not only space). Licence gate is fail-closed: only CC0, Public Domain Mark, CC BY, CC BY-SA and NASA media pass; NC, ND, unknown or missing licences are rejected, including a server-side `NOT licenseurl:(*-nc*)` filter on Internet Archive. Relevance is lexical and needs the query to match the title or keywords (description-only matches are not enough). Downloads are https-only, size-capped, magic-byte checked and probed (Pillow for images, ffprobe for video) before they are placed in `public/visual/<slug>/`. `apply` wires assets into `cinema.src` (`cinema_clip`) and `broll.image` (`broll_cinematic`) and validates the result with `check_assets=True`. A `cinema_clip` without media fails closed even with `--allow-missing`. Credits are written to `out/<slug>_visual_credits.txt`. Covered by `tests/test_visual_sourcing.py` (44 offline tests) and `scripts/verify_stage3_visuals.ps1`.
- **`min_duration_sec` slide field** (`scripts/build_deck.py`, optional, 1..120): a slide keeps at least this length even if its narration is shorter. The director sets it to each scene's `target_sec`.

### Changed (director, Stage 3 follow-up)
- Director narration bounds are now enforced in both directions: 1.8 to 3.3 words/sec (dead air below, too fast above). The repair message states the exact word range to write. Before this change a requested 1-minute script rendered at 31 s because the renderer sized slides from narration only.

### Changed
- `public/cinema/` is git-ignored: the AI clips are large binaries and must be regenerated per machine; decks that reference them fail closed when they are missing.
- **Canonical studio demo is `decks/studio-universal-demo-v2.json`** (slug `studio-universal-demo-v2`): 7 slides with `outro_3d` CTA, chart slides separated, portrait chart/versus layout fixed.
- **`decks/studio-universal-demo.json` is restored to the v1.3.0 snapshot** (6 slides, no outro) so that the existing `studio-universal-demo*` MP4s still match their source deck. It is superseded and kept only for reproducibility.

### Fixed
- `make_cutdown` now fails closed on two adjacent `chart_story` slides in a 9:16 short: the second chart is replaced by a non-chart slide from the same deck, or the build raises.
- Portrait (9:16) `chart_story` bar/line/donut and `versus_split` cards fill the canvas instead of letterboxing.

## [1.3.0] — 2026-11-26

### Fixed
- **Console video-pack build no longer overwrites MP4s implicitly** (`scripts/console_server.py`): `POST /api/video-pack/build` passes `--overwrite` only on explicit `overwrite: true`; otherwise an existing MP4 fails closed.
- **Docs & counts synced:** `docs/DECK_SCHEMA.md` documents the 4 universal slide types, `director_preset`, and voice `mode: "podcast"` (the `duo` value was never a real build mode); test count corrected to 157.

### Added (Universal Studio Roadmap A–D)
- **Phase A — Built-in Idea Engine (`scripts/idea_engine.py`, `console_server.py`, `console_ui.html`, `mcp_server.py`):** 7 video genres (`tech_explainer`, `versus_battle`, `short_60s`, `news_digest`, `investor_pitch`, `case_study`, `tutorial`), honest offline template mode vs fail-closed Ollama/Cloud LLM mode, and 1-click conversion into validated `decks/<slug>.json`.
- **Phase B — 4 Universal Slide Templates (`src/UniversalSlides.tsx`, `src/types.ts`, `scripts/build_deck.py`):** `versus_split` (A vs B 3D comparison + verdict), `chart_story` (`bar` / `line` / `donut`), `stat_burst` (high-impact hook slide), and `broll_cinematic` (Ken Burns full-bleed storytelling) — total **18 slide types**.
- **Phase C — Director Presets, Thumbnail Studio & Duo Speaker Indicator:**
  - `scripts/director_presets.py` (`cinema_cosmos`, `fast_shorts`, `documentary`, `news_flash`, `tech_pitch`).
  - `scripts/thumbnail_studio.py` + Remotion `DupThumbnail` (`src/Thumbnail.tsx`, `1280×720`).
  - Upgraded two-voice active-speaker badge (`HOST` / `EXPERT`) in `src/Composition.tsx`, shared by `karaoke`, `bold` and `box` caption styles (`DuoSpeakerChip`).
- **Studio finalize (`c5c9f6c`):**
  - `auto_fix_deck()` in `scripts/idea_engine.py`: deterministic safe fixes (9:16 `box` → `bold` captions, `fast_shorts` default preset, missing `outro_3d`), validated fail-closed. Exposed as `POST /api/critique/autofix`, the «Авто-исправить дек» button, and the MCP tool `auto_fix_deck`.
  - Two-voice recommendation now uses the real `podcast` mode (was the non-existent `duo` mode in the advisor output).
  - `scripts/build_deck.py` resolves `director_preset` from the CLI (`resolve_director_preset`, explicit keys win).
  - `scripts/video_pack.py` applies `fast_shorts` to the 9:16 Short; console `POST /api/video-pack/build` + «Собрать Video Pack» button.
  - `decks/studio-universal-demo.json` gained `s5` (`chart_story` line) and `s6` (`chart_story` donut); both visually verified as stills.
- **Docs:** `docs/DECK_SCHEMA.md` documents the 4 universal slide types, `director_preset`, and `voice.mode` `podcast` (the `duo` value was never a real build mode).
- **Phase D — Multi-Format Video Pack (`scripts/video_pack.py` + MCP `plan_video_pack` / `render_thumbnail`):** builds coordinated 16:9 + 9:16 Short + optional translation + 1280×720 cover + unified fail-closed `out/<slug>_pack_manifest.json`.
- **Tests:** `tests/test_idea_engine.py`, `tests/test_universal_slides.py`, `tests/test_director_thumb_pack.py` (**157 total tests passing**).

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
