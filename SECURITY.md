# Security Policy

## Scope & Threat Model

`dup-presenter` is a local-first presentation build and rendering engine (Python + TypeScript / Remotion 4 + FFmpeg + Playwright). It is **not** a public multi-tenant web service.

Key security boundaries enforced by the repository:

1. **No secrets in Git:** `secrets/`, `.env`, upload tokens (e.g. TikTok/GitHub credentials), and local recordings are excluded via `.gitignore`. Never commit API keys, OAuth tokens, or private screenshots.
2. **Offline Privacy Lock (`--offline-only`):** Running `scripts/build_deck.py --offline-only` disables external network TTS (Edge TTS) and stock media fetches, restricting synthesis to local engines (Silero v5 RU / Kokoro-82M v1.0 EN) and local assets only.
3. **Fail-Closed Deck & Path Validation:**
   - `scripts/build_deck.py` and `scripts/deck_doctor.py` refuse malformed schemas, unknown slide types, missing local screenshots/recordings, or unbalanced diagram structures instead of silently rendering broken frames.
   - `scripts/claim_audit.py` audits deck claims against an actual local repository before rendering.
4. **Local-Only Console (`scripts/console_server.py`):** Intended to bind on loopback (`127.0.0.1`) for local operator use. Do **not** expose the console server directly to the public internet without an authenticated reverse proxy.

## Supported Versions

Only the latest commit on `main` and the latest tagged release (`v1.2.0`) receive fixes.

## Reporting a Vulnerability

If you discover a security issue (for example, path traversal in the local console API, unsafe subprocess/command handling in scripts, or secret leakage):

- **Do not** open a public issue with exploit details.
- Use GitHub **Private Vulnerability Reporting** on [`Gruver87/dup-presenter`](https://github.com/Gruver87/dup-presenter/security/advisories) or contact the maintainer via GitHub (`@Gruver87`).
- Include reproduction steps, affected file/script, and expected fail-closed behavior.
