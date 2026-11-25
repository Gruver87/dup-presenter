---
name: Bug report
about: Report a reproducible bug or fail-closed gate failure in DUP Presenter
title: "[bug] "
labels: bug
---

## Summary
Clear description of the unexpected behavior.

## Reproduction
1. Deck file or command run:
   ```powershell
   python scripts/build_deck.py decks/<slug>.json --preview-stills
   ```
2. Environment: OS, Python version, Node version, TTS engine (`edge_tts` / `kokoro_v1` / `silero_v5_ru`).

## Actual Output / Logs
Paste the exact error message or `out/<slug>_qa.json` output (never include secrets or tokens).

## Expected Behavior
What should happen (or what fail-closed error should be raised).
