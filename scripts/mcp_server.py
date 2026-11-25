"""Minimal zero-dependency stdio MCP Server (JSON-RPC 2.0) for DUP Presenter.

Allows AI coding agents (Cursor, Claude Desktop, etc.) to inspect decks, audit claims
against source repos, generate 9:16 Short cutdowns, check Media QA, and manage the
pronunciation dictionary directly via standard MCP tool calls.

Run over stdio:
    python scripts/mcp_server.py
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from build_deck import validate_deck  # noqa: E402
from claim_audit import audit_deck  # noqa: E402
from deck_doctor import load_and_diagnose  # noqa: E402
from idea_engine import generate_ideas, write_idea_deck  # noqa: E402
from make_cutdown import build_short_cutdown  # noqa: E402
from media_qa import run_media_qa  # noqa: E402
from publish_pack import build_publish_pack  # noqa: E402
from ru_speech import get_latin_ru, load_pronunciation_overrides, save_pronunciation_overrides  # noqa: E402
from thumbnail_studio import build_thumbnail_props, render_thumbnail  # noqa: E402
from video_pack import plan_video_pack  # noqa: E402

PREVIEW_TIMEOUT_SEC = 900

SERVER_INFO = {"name": "dup-presenter-mcp", "version": "1.0.0"}
PROTOCOL_VERSION = "2024-11-05"

TOOLS = [
    {
        "name": "list_decks",
        "description": "List available presentation deck JSON files in dup-presenter/decks with slide count, language, and aspect.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "generate_ideas",
        "description": "Generate 1..7 diverse video concepts (hook, genre, aspect, theme, slide blueprint) using offline templates or LLM (fail-closed).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Topic, product name, or short brief"},
                "lang": {"type": "string", "enum": ["ru", "en"], "default": "ru"},
                "genre": {"type": "string", "default": "all"},
                "count": {"type": "integer", "default": 5},
                "mode": {"type": "string", "enum": ["template", "ollama", "cloud"], "default": "template"},
            },
            "required": ["topic"],
            "additionalProperties": False,
        },
    },
    {
        "name": "idea_to_deck",
        "description": "Convert a generated idea object into a validated DUP Presenter deck JSON in decks/<slug>.json.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "idea": {"type": "object", "description": "Idea object returned by generate_ideas"},
                "slug": {"type": "string", "default": ""},
                "overwrite": {"type": "boolean", "default": False},
            },
            "required": ["idea"],
            "additionalProperties": False,
        },
    },
    {
        "name": "plan_video_pack",
        "description": "Validate a deck and return a multi-format Video Pack build plan (16:9 + 9:16 Short + optional translation + 1280x720 thumbnail).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "deck": {"type": "string", "description": "Source deck path"},
                "include_short": {"type": "boolean", "default": True},
                "include_thumbnail": {"type": "boolean", "default": True},
                "translate_to": {"type": "string", "enum": ["", "ru", "en"], "default": ""},
                "preset": {"type": "string", "default": ""},
            },
            "required": ["deck"],
            "additionalProperties": False,
        },
    },
    {
        "name": "render_thumbnail",
        "description": "Render a 1280x720 clickable cover PNG via Remotion DupThumbnail composition.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "deck": {"type": "string", "default": ""},
                "title": {"type": "string", "default": ""},
                "subtitle": {"type": "string", "default": ""},
                "accent_badge": {"type": "string", "default": ""},
                "theme": {"type": "string", "default": ""},
                "out": {"type": "string", "description": "Output PNG path under out/"},
            },
            "required": ["out"],
            "additionalProperties": False,
        },
    },
    {
        "name": "audit_deck_claims",
        "description": "Verify deck numeric claims, code symbols, file:line citations, and safety invariants against a source repository.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "deck": {"type": "string", "description": "Deck path (e.g. decks/radar-pro.json)"},
                "repo": {"type": "string", "description": "Absolute path to source repository"},
            },
            "required": ["deck", "repo"],
            "additionalProperties": False,
        },
    },
    {
        "name": "make_short_cutdown",
        "description": "Generate a validated 9:16 ~60s vertical Short deck from a 16:9 deck without inventing new claims.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "deck": {"type": "string", "description": "Source deck path (e.g. decks/radar-pro.json)"},
                "max_slides": {"type": "integer", "default": 4},
                "write": {"type": "boolean", "default": False, "description": "When true, save to decks/<slug>-short.json"},
            },
            "required": ["deck"],
            "additionalProperties": False,
        },
    },
    {
        "name": "run_media_qa",
        "description": "Run fail-closed Media QA Gate (ffprobe + LUFS/TP + dead-air check) on a rendered MP4.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mp4": {"type": "string", "description": "Path to MP4 file (e.g. out/radar-pro.mp4)"},
                "expect_loudnorm": {"type": "boolean", "default": True},
            },
            "required": ["mp4"],
            "additionalProperties": False,
        },
    },
    {
        "name": "pronunciation_dictionary",
        "description": "Get or update Russian TTS pronunciation overrides in config/pronunciation.json.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "add": {
                    "type": "object",
                    "description": "Optional mapping of lowercase token -> Cyrillic pronunciation to add/update",
                    "additionalProperties": {"type": "string"},
                }
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "build_publish_pack",
        "description": "Generate YouTube chapters, social post copy, and metadata.json from deck_resolved.json.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "resolved": {"type": "string", "default": "src/generated/deck_resolved.json"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "deck_doctor",
        "description": "Pre-render diagnostics (no rendering): schema, Cyrillic in EN decks, missing screenshots/music, overwrite risk, length and render-time estimates.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "deck": {"type": "string", "description": "Deck path (e.g. decks/radar-cosmic-v4-en.json)"},
                "overwrite": {"type": "boolean", "default": False},
            },
            "required": ["deck"],
            "additionalProperties": False,
        },
    },
    {
        "name": "render_deck",
        "description": "Start a full MP4 render in the background. Refuses if deck_doctor finds errors or if out/<slug>.mp4 exists and overwrite is false. Returns a log path; poll with render_status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "deck": {"type": "string"},
                "skip_tts": {"type": "boolean", "default": False, "description": "Reuse existing WAV files"},
                "overwrite": {"type": "boolean", "default": False},
            },
            "required": ["deck"],
            "additionalProperties": False,
        },
    },
    {
        "name": "render_status",
        "description": "Report progress of a background render for a slug: running/finished, exit code, MP4 presence, and the last log lines.",
        "inputSchema": {
            "type": "object",
            "properties": {"slug": {"type": "string"}},
            "required": ["slug"],
            "additionalProperties": False,
        },
    },
    {
        "name": "preview_stills",
        "description": "Render one PNG frame per slide to out/<slug>_stills/ (synchronous, up to 15 minutes). Use only_slide to isolate one slide.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "deck": {"type": "string"},
                "only_slide": {"type": "string", "default": ""},
                "skip_tts": {"type": "boolean", "default": False},
            },
            "required": ["deck"],
            "additionalProperties": False,
        },
    },
]


def _resolve_path(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else (ROOT / path)


def handle_tool_call(name: str, arguments: dict) -> dict:
    if name == "list_decks":
        decks = []
        for p in sorted((ROOT / "decks").glob("*.json")):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                decks.append({
                    "file": f"decks/{p.name}",
                    "slug": d.get("slug"),
                    "lang": d.get("lang") or (d.get("voice") or {}).get("lang") or "ru",
                    "aspect": d.get("aspect", "16:9"),
                    "slides": len(d.get("slides") or []),
                })
            except Exception as exc:
                decks.append({"file": f"decks/{p.name}", "error": str(exc)})
        return {"decks": decks}

    if name == "audit_deck_claims":
        dp = _resolve_path(arguments["deck"])
        deck = json.loads(dp.read_text(encoding="utf-8"))
        validate_deck(deck)
        return audit_deck(deck, repo_root=Path(arguments["repo"]))

    if name == "make_short_cutdown":
        dp = _resolve_path(arguments["deck"])
        deck = json.loads(dp.read_text(encoding="utf-8"))
        short = build_short_cutdown(deck, max_slides=int(arguments.get("max_slides", 4)))
        saved = None
        if arguments.get("write"):
            out_p = ROOT / "decks" / f"{short['slug']}.json"
            out_p.write_text(json.dumps(short, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            saved = str(out_p)
        return {"slug": short["slug"], "aspect": short["aspect"], "slides": len(short["slides"]), "saved": saved}

    if name == "run_media_qa":
        mp4 = _resolve_path(arguments["mp4"])
        return run_media_qa(mp4, expect_loudnorm=bool(arguments.get("expect_loudnorm", True)))

    if name == "pronunciation_dictionary":
        add_map = arguments.get("add")
        if isinstance(add_map, dict) and add_map:
            cur = load_pronunciation_overrides()
            cur.update({str(k).strip().lower(): str(v).strip() for k, v in add_map.items()})
            save_pronunciation_overrides(cur)
        return {"overrides": load_pronunciation_overrides(), "total_entries": len(get_latin_ru())}

    if name == "build_publish_pack":
        rp = _resolve_path(arguments.get("resolved") or "src/generated/deck_resolved.json")
        resolved = json.loads(rp.read_text(encoding="utf-8"))
        mp4 = ROOT / "out" / f"{resolved['slug']}.mp4"
        pack = build_publish_pack(resolved, mp4_path=mp4 if mp4.is_file() else None)
        return {k: str(v) for k, v in pack.items()}

    if name == "deck_doctor":
        dp = _resolve_path(arguments["deck"])
        return load_and_diagnose(dp, overwrite=bool(arguments.get("overwrite", False)))

    if name == "render_deck":
        return _start_render(
            _resolve_path(arguments["deck"]),
            skip_tts=bool(arguments.get("skip_tts", False)),
            overwrite=bool(arguments.get("overwrite", False)),
        )

    if name == "render_status":
        return _render_status(str(arguments["slug"]))

    if name == "preview_stills":
        return _preview_stills(
            _resolve_path(arguments["deck"]),
            only_slide=str(arguments.get("only_slide") or "").strip(),
            skip_tts=bool(arguments.get("skip_tts", False)),
        )

    if name == "generate_ideas":
        return generate_ideas(
            str(arguments["topic"]),
            lang=str(arguments.get("lang") or "ru"),
            genre=str(arguments.get("genre") or "all"),
            count=int(arguments.get("count") or 5),
            mode=str(arguments.get("mode") or "template"),
        )

    if name == "idea_to_deck":
        deck, deck_path = write_idea_deck(
            arguments["idea"],
            ROOT / "decks",
            slug=str(arguments.get("slug") or ""),
            overwrite=bool(arguments.get("overwrite", False)),
        )
        return {"ok": True, "slug": deck["slug"], "path": str(deck_path), "slides": len(deck["slides"])}

    if name == "plan_video_pack":
        return plan_video_pack(
            _resolve_path(arguments["deck"]),
            include_short=bool(arguments.get("include_short", True)),
            include_thumbnail=bool(arguments.get("include_thumbnail", True)),
            translate_to=str(arguments.get("translate_to") or ""),
            preset=str(arguments.get("preset") or ""),
        )

    if name == "render_thumbnail":
        deck_data = None
        if arguments.get("deck"):
            deck_data = json.loads(_resolve_path(arguments["deck"]).read_text(encoding="utf-8"))
        props = build_thumbnail_props(
            deck=deck_data,
            title=str(arguments.get("title") or ""),
            subtitle=str(arguments.get("subtitle") or ""),
            accent_badge=str(arguments.get("accent_badge") or ""),
            theme=str(arguments.get("theme") or ""),
        )
        out_p = _resolve_path(arguments["out"])
        return render_thumbnail(out_p, props, dry_run=False)

    raise ValueError(f"Unknown tool: {name}")


def _safe_slug(slug: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,80}", slug):
        raise ValueError(f"invalid slug {slug!r}")
    return slug


def _start_render(deck_path: Path, *, skip_tts: bool, overwrite: bool) -> dict:
    report = load_and_diagnose(deck_path, overwrite=overwrite)
    if not report["ok"]:
        raise ValueError("deck doctor refused to render: " + "; ".join(report["errors"]))
    slug = _safe_slug(str(json.loads(deck_path.read_text(encoding="utf-8"))["slug"]))
    out_dir = ROOT / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / f"{slug}_build.log"
    mp4_path = out_dir / f"{slug}.mp4"
    # Fail closed on concurrent renders: a second build would truncate the log and write the same MP4.
    if log_path.is_file() and "BUILD_EXIT=" not in log_path.read_text(encoding="utf-8", errors="replace"):
        raise ValueError(f"render already running for slug {slug!r}; poll render_status first")

    cmd = [sys.executable, str(ROOT / "scripts" / "build_deck.py"), str(deck_path), "--render"]
    if skip_tts:
        cmd.append("--skip-tts")
    if overwrite:
        cmd.append("--overwrite")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    logf = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=logf, stderr=subprocess.STDOUT, env=env)

    def _finish() -> None:
        rc = proc.wait()
        logf.write(f"\nBUILD_EXIT={rc}\n")
        logf.close()

    threading.Thread(target=_finish, daemon=True).start()
    return {
        "started": True,
        "pid": proc.pid,
        "log": str(log_path),
        "mp4": str(mp4_path),
        "warnings": report["warnings"],
        "estimates": report["estimates"],
        "note": "Background render. Poll render_status with the slug; the render can take several minutes.",
    }


def _render_status(slug: str) -> dict:
    slug = _safe_slug(slug)
    log_path = ROOT / "out" / f"{slug}_build.log"
    mp4_path = ROOT / "out" / f"{slug}.mp4"
    if not log_path.is_file():
        return {"slug": slug, "status": "not_started"}
    text = log_path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"BUILD_EXIT=(\d+)", text)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return {
        "slug": slug,
        "status": "finished" if m else "running",
        "exit_code": int(m.group(1)) if m else None,
        "mp4_exists": mp4_path.is_file(),
        "mp4_bytes": mp4_path.stat().st_size if mp4_path.is_file() else 0,
        "tail": lines[-12:],
    }


def _preview_stills(deck_path: Path, *, only_slide: str, skip_tts: bool) -> dict:
    validate_deck(json.loads(deck_path.read_text(encoding="utf-8")))
    if only_slide and not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", only_slide):
        raise ValueError(f"invalid only_slide {only_slide!r}")
    cmd = [sys.executable, str(ROOT / "scripts" / "build_deck.py"), str(deck_path), "--preview-stills"]
    if only_slide:
        cmd += ["--only-slide", only_slide]
    if skip_tts:
        cmd.append("--skip-tts")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=PREVIEW_TIMEOUT_SEC, env=env)
    if proc.returncode != 0:
        raise ValueError(f"preview failed (exit {proc.returncode}): {proc.stderr[-800:]}")
    slug = json.loads(deck_path.read_text(encoding="utf-8"))["slug"]
    if only_slide:
        slug = f"{slug}_{only_slide}"
    stills = ROOT / "out" / f"{slug}_stills"
    return {"stills_dir": str(stills), "pngs": sorted(p.name for p in stills.glob("*.png"))}


def handle_rpc(req: dict) -> dict | None:
    req_id = req.get("id")
    method = req.get("method")
    params = req.get("params") or {}

    if method == "notifications/initialized":
        return None
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            },
        }
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        try:
            data = handle_tool_call(str(params.get("name") or ""), params.get("arguments") or {})
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False, indent=2)}],
                    "isError": False,
                },
            }
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Error: {type(exc).__name__}: {exc}"}],
                    "isError": True,
                },
            }
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            sys.stdout.write(
                json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}}) + "\n"
            )
            sys.stdout.flush()
            continue
        resp = handle_rpc(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
