"""Claim Audit Gate for DUP Presenter — verifies deck claims against source code and facts.

Checks every slide before render:
1. Numeric claims (integers >= 2 digits, latencies, percentages, scale constants) against repo corpus.
2. Code identifiers (snake_case, CamelCase, UPPER_CONST, file paths) against repo files/symbols.
3. Optional explicit slide `evidence: ["path/to/file.py:42"]` citations (verifies file and line exist).
4. Optional safety-config invariants (e.g. if repo has `enabled_default: false` or `FUTURES_BLOCK`,
   flags contradictory claims such as "автоторговля включена по умолчанию" or "торгует фьючерсами").

Usage:
    python scripts/claim_audit.py decks/radar-pro.json --repo C:\\Users\\vovun\\Desktop\\DUP_Projects\\dup-market-radar
    python scripts/claim_audit.py decks/radar-pro.json --facts work/radar/facts.json --strict
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Common non-factual / formatting / prose numbers we don't flag as unverified metrics
IGNORE_NUMBERS = {"2025", "2026", "2027", "1080", "1920", "30", "60", "100"}

# Identifiers that are generic tech terms, not project-specific symbols
COMMON_TECH = {
    "Python", "Rust", "React", "TypeScript", "JavaScript", "Docker", "GitHub", "TikTok", "YouTube",
    "WebSocket", "WebSockets", "FastAPI", "SQLite", "PostgreSQL", "RocksDB", "PyO3", "JSON", "REST",
    "HTTP", "HTTPS", "HTML", "CSS", "API", "CLI", "UI", "UX", "PWA", "KPI", "EVM", "NFT", "ERC",
    "USDT", "USD", "BTC", "ETH", "SOL", "OKX", "Bybit", "Binance", "KuCoin", "Bitget", "MEXC",
    "Gate", "Telegram", "Silero", "Kokoro", "Remotion", "Edge", "TTS", "MP4", "SRT", "VTT", "LUFS",
    "DUP", "Labs", "Protocol", "Market", "Radar", "Watchlist", "Markets", "Spot", "Futures",
    "USDTM", "DRY", "RUN", "OFF", "ON", "LIVE", "SOURCE", "UTC", "MS", "FLOAT",
}

NUM_RE = re.compile(r"\b\d{1,3}(?:[\s\u00a0_.,]\d{3})+\b|\b\d{2,}\b")
CODE_IDENT_RE = re.compile(r"\b[a-z][a-z0-9]*_[a-z0-9_]+\b|\b[A-Z][A-Z0-9_]{3,}\b")
EVIDENCE_RE = re.compile(r"^([^:]+?)(?::(\d+)(?:-(\d+))?)?$")


def _normalize_number(raw: str) -> str:
    return re.sub(r"[\s\u00a0_,]", "", raw).strip(".")


def _build_repo_corpus(repo_root: Path | None, facts: dict | None) -> tuple[str, set[str]]:
    """Build searchable text + normalized number set from repo files and/or facts.json."""
    chunks: list[str] = []
    if facts:
        chunks.append(json.dumps(facts, ensure_ascii=False))
    if repo_root and repo_root.is_dir():
        exts = {".py", ".rs", ".ts", ".tsx", ".js", ".json", ".toml", ".yaml", ".yml", ".md", ".txt", ".cfg", ".ini"}
        skip_dirs = {".git", "node_modules", "target", "__pycache__", ".venv", "venv", "dist", "build", "out"}
        scanned = 0
        for p in repo_root.rglob("*"):
            if any(part in skip_dirs for part in p.parts):
                continue
            if not p.is_file() or p.suffix.lower() not in exts:
                continue
            if p.stat().st_size > 400_000:
                continue
            try:
                chunks.append(p.read_text(encoding="utf-8", errors="ignore"))
                scanned += 1
                if scanned >= 400:
                    break
            except OSError:
                continue
    corpus = "\n".join(chunks)
    nums = {_normalize_number(m.group(0)) for m in NUM_RE.finditer(corpus)}
    return corpus, nums


def _slide_text(slide: dict) -> str:
    parts = [
        str(slide.get("title") or ""),
        str(slide.get("subtitle") or ""),
        str(slide.get("voice_text") or ""),
        str(slide.get("tagline") or ""),
    ]
    for b in slide.get("bullets") or []:
        parts.append(str(b.get("title") or ""))
        parts.append(str(b.get("desc") or ""))
    for k in slide.get("kpis") or []:
        parts.append(str(k.get("value") or ""))
        parts.append(str(k.get("label") or ""))
    for d in slide.get("dialogue") or []:
        parts.append(str(d.get("text") or ""))
    return "\n".join(parts)


def audit_deck(deck: dict, repo_root: Path | None = None, facts: dict | None = None) -> dict:
    """Audit deck claims against repo source and/or facts.json. Returns structured audit report."""
    corpus, corpus_nums = _build_repo_corpus(repo_root, facts)
    corpus_lower = corpus.lower()

    # Detect safety invariants present in repo
    has_auto_off_default = ("enabled_default" in corpus and "false" in corpus_lower) or ("dry_run" in corpus_lower and "true" in corpus_lower)
    has_futures_block = "futures_block" in corpus_lower or ("usdtm" in corpus_lower and "refus" in corpus_lower)

    unverified_numbers: list[dict] = []
    unverified_symbols: list[dict] = []
    evidence_errors: list[dict] = []
    safety_warnings: list[dict] = []
    verified_hits = 0

    for slide in deck.get("slides") or []:
        sid = str(slide.get("id") or "?")
        text = _slide_text(slide)

        # 1. Explicit evidence citations: ["src/foo.py:42"]
        for ref in slide.get("evidence") or []:
            m = EVIDENCE_RE.match(str(ref).strip())
            if not m:
                evidence_errors.append({"slide": sid, "ref": ref, "error": "invalid file:line format"})
                continue
            rel_path, ln_s, ln_e = m.group(1), m.group(2), m.group(3)
            if repo_root is None:
                evidence_errors.append({"slide": sid, "ref": ref, "error": "no --repo provided to verify citation"})
                continue
            target = repo_root / rel_path
            if not target.is_file():
                evidence_errors.append({"slide": sid, "ref": ref, "error": f"file not found: {rel_path}"})
                continue
            if ln_s:
                lines = target.read_text(encoding="utf-8", errors="ignore").splitlines()
                ln_start = int(ln_s)
                ln_end = int(ln_e) if ln_e else ln_start
                if not (1 <= ln_start <= len(lines)) or ln_end > len(lines):
                    evidence_errors.append({
                        "slide": sid,
                        "ref": ref,
                        "error": f"line range {ln_start}-{ln_end} out of bounds (file has {len(lines)} lines)",
                    })
                    continue
            verified_hits += 1

        # 2. Numeric claims (note: live runtime counters like ~150 ms or live watchlist counts may be runtime metrics)
        for m in NUM_RE.finditer(text):
            raw = m.group(0)
            norm = _normalize_number(raw)
            if not norm or norm in IGNORE_NUMBERS or len(norm) < 2:
                continue
            if norm in corpus_nums or norm in corpus:
                verified_hits += 1
            else:
                # Check if prefixed by approximation (~) or clearly a runtime measurement
                start = max(0, m.start() - 3)
                prefix = text[start : m.start()]
                kind = "runtime_approx" if "~" in prefix else "unverified_number"
                unverified_numbers.append({"slide": sid, "value": raw, "normalized": norm, "kind": kind})

        # 3. Code identifiers (snake_case / UPPER_CONST)
        for m in CODE_IDENT_RE.finditer(text):
            ident = m.group(0)
            if ident in COMMON_TECH:
                continue
            if ident in corpus:
                verified_hits += 1
            else:
                unverified_symbols.append({"slide": sid, "symbol": ident})

        # 4. Safety invariant contradiction check (ignore negated statements like "не торгует фьючерсами" / "never trades futures")
        tl = text.lower()
        if has_auto_off_default:
            if re.search(
                r"(?<!не\s)(?<!not\s)(?<!never\s)(?:авто\w*\s+(?:включен\w*|работает)\s+по\s+умолчан|auto[\s-]?trade\s+enabled\s+by\s+default)",
                tl,
            ):
                safety_warnings.append({
                    "slide": sid,
                    "rule": "auto_off_by_default",
                    "detail": "Deck claims auto-trading is enabled by default, contradicting repo config.",
                })
        if has_futures_block:
            if re.search(
                r"(?<!не\s)(?<!никогда\sне\s)(?<!not\s)(?<!never\s)(?:торгует\s+фьючерс|автоторговля\s+фьючерс|trades?\s+futures\s+automatically)",
                tl,
            ):
                safety_warnings.append({
                    "slide": sid,
                    "rule": "no_futures_auto",
                    "detail": "Deck claims automated futures trading, contradicting FUTURES_BLOCK in repo.",
                })

    hard_issues = len(evidence_errors) + len(safety_warnings) + len(unverified_symbols)
    non_approx_nums = [n for n in unverified_numbers if n["kind"] != "runtime_approx"]
    return {
        "ok": hard_issues == 0 and len(non_approx_nums) == 0,
        "hard_ok": hard_issues == 0,
        "slug": deck.get("slug"),
        "verified_hits": verified_hits,
        "evidence_errors": evidence_errors,
        "safety_warnings": safety_warnings,
        "unverified_symbols": unverified_symbols,
        "unverified_numbers": unverified_numbers,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="DUP Presenter Claim Audit Gate")
    parser.add_argument("deck", help="Path to deck JSON")
    parser.add_argument("--repo", default="", help="Path to target source repository to verify claims against")
    parser.add_argument("--facts", default="", help="Optional path to facts.json")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero on ANY unverified number or symbol")
    parser.add_argument("--out", default="", help="Optional JSON report output path")
    args = parser.parse_args()

    deck_p = Path(args.deck)
    if not deck_p.is_absolute():
        deck_p = ROOT / deck_p
    deck = json.loads(deck_p.read_text(encoding="utf-8"))

    repo_root = Path(args.repo) if args.repo else None
    facts = None
    if args.facts:
        fp = Path(args.facts)
        if not fp.is_absolute():
            fp = ROOT / fp
        if fp.is_file():
            facts = json.loads(fp.read_text(encoding="utf-8"))

    if repo_root is None and facts is None:
        print("[ERROR] Provide --repo <path> and/or --facts <facts.json>", file=sys.stderr)
        return 2

    report = audit_deck(deck, repo_root=repo_root, facts=facts)
    if args.out:
        op = Path(args.out)
        if not op.is_absolute():
            op = ROOT / op
        op.parent.mkdir(parents=True, exist_ok=True)
        op.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.strict:
        return 0 if report["ok"] else 1
    return 0 if report["hard_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
