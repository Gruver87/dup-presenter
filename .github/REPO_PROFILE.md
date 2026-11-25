# GitHub Repository Profile

Apply metadata with:

```powershell
gh repo edit Gruver87/dup-presenter --description "DUP Presenter (DUP Labs) — Declarative 3D presentation engine: JSON/MD deck -> neural TTS + karaoke captions -> Remotion 4 3D slides -> -16 LUFS MP4 + Media QA Gate."
gh repo edit Gruver87/dup-presenter --homepage "https://github.com/Gruver87/dup-presenter#readme"
@(
  "dup-labs","remotion","video-generation","presentation","tts","kokoro","edge-tts",
  "silero","faster-whisper","karaoke-captions","ffmpeg","python","typescript","mcp",
  "fail-closed","playwright"
) | ForEach-Object { gh repo edit Gruver87/dup-presenter --add-topic $_ }
```

## Profile Fields

| Field | Value |
|-------|-------|
| **Description** | DUP Presenter (DUP Labs) — Declarative 3D presentation engine: JSON/MD deck -> neural TTS + karaoke captions -> Remotion 4 3D slides -> -16 LUFS MP4 + Media QA Gate. |
| **Homepage** | `https://github.com/Gruver87/dup-presenter#readme` |
| **Default branch** | `main` |
| **Latest software tag** | `v1.2.0` |
| **Showcase media releases** | `media-dup-protocol-cosmos` (RU + EN) · `media-radar-showcase-v2` |
| **CI** | `.github/workflows/ci.yml` (`tsc --noEmit`, `py_compile`, 137 Python unit/gate tests including live Playwright UI recorder test) |
| **Cite** | `CITATION.cff` |

## Honest Positioning

- **Is:** A reproducible, fail-closed 3D video presentation engine built on Remotion 4 + Python + FFmpeg, with neural TTS, word-level karaoke captions, local web console, MCP server, and Media QA Gate.
- **Is not:** A hosted SaaS video editor, a replacement for checking Remotion's commercial license, or a substitute for verifying facts in target repositories (always pair with `claim_audit.py` and real disk artifacts).
