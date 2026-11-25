"""Minimal zero-dependency stdio MCP Server (JSON-RPC 2.0) for DUP Presenter.

Allows AI coding agents (Cursor, Claude Desktop, etc.) to inspect decks, audit claims
against source repos, generate 9:16 Short cutdowns, check Media QA, and manage the
pronunciation dictionary directly via standard MCP tool calls.

Run over stdio:
    python scripts/mcp_server.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from build_deck import validate_deck  # noqa: E402
from claim_audit import audit_deck  # noqa: E402
from make_cutdown import build_short_cutdown  # noqa: E402
from media_qa import run_media_qa  # noqa: E402
from publish_pack import build_publish_pack  # noqa: E402
from ru_speech import get_latin_ru, load_pronunciation_overrides, save_pronunciation_overrides  # noqa: E402

SERVER_INFO = {"name": "dup-presenter-mcp", "version": "1.0.0"}
PROTOCOL_VERSION = "2024-11-05"

TOOLS = [
    {
        "name": "list_decks",
        "description": "List available presentation deck JSON files in dup-presenter/decks with slide count, language, and aspect.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
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

    raise ValueError(f"Unknown tool: {name}")


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
