# Contributing to DUP Presenter

Contributions are welcome, provided they follow DUP Labs engineering standards: **fail-closed validation**, **honest evidence**, and **zero silent fallbacks**.

## Required Local Checks

Before opening a pull request, run all checks from the repository root:

```powershell
# 1. TypeScript type-check (uses tests/fixtures/deck_resolved.typecheck.json if src/generated is empty)
npx tsc --noEmit

# 2. Python syntax check
python -m py_compile scripts/*.py

# 3. Full Python unit & gate test suite (137 tests)
python -m unittest discover -s tests -v
```

If you modify the local web console (`scripts/console_server.py`), also run the live Playwright smoke check:

```powershell
python scripts/console_server.py --port 8790 --no-auto-ollama
python scripts/console_ui_check.py --url http://127.0.0.1:8790/
```

## Architecture & Invariants

1. **Theme Single Source of Truth:** Every theme ID in `src/themes.ts` (`THEMES` / `ThemeId`) **must** have a matching entry in `scripts/theme_catalog.py` (`THEME_CATALOG`), and vice versa.
2. **Slide Schema Parity:** Adding or modifying a slide `type` requires updating:
   - `src/types.ts` (TypeScript contract)
   - `scripts/build_deck.py` (`ALLOWED_TYPES` + fail-closed validator)
   - `src/Composition.tsx` / `src/StorySlides.tsx` (renderer for both 16:9 and 9:16 where applicable)
   - `tests/` (positive + negative fail-closed unit tests)
   - `README.md` and `docs/DECK_SCHEMA.md`
3. **Honest Captions & Audio:** Never claim real word-level alignment when estimated timing was used; preserve the explicit alignment logging in `scripts/build_deck.py` and `scripts/audio_fx.py`.
4. **Do Not Commit Heavy / Local Artifacts:**
   - Never commit `out/`, `public/voice/`, `public/music/`, `public/ui_recordings/`, `public/screens/dup-protocol/`, `models/`, or `secrets/`.
   - Showcase MP4s belong in **GitHub Releases** (see `scripts/github_release_uploader.py`), with only lightweight JPEG thumbnails (`~50–170 KB`) in `docs/media/`.

## Pull Request Checklist

- [ ] `npx tsc --noEmit` passes with 0 errors
- [ ] `python -m py_compile scripts/*.py` passes
- [ ] `python -m unittest discover -s tests -v` passes
- [ ] New behavior is covered by unit tests (including fail-closed rejection cases)
- [ ] Documentation (`README.md`, `CHANGELOG.md`, `docs/`) accurately reflects disk state
