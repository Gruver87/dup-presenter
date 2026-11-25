"""DUP Presenter - project analyzer (read-only).

Reads a local project folder and writes a fact sheet with stable source IDs:
    D* = documentation chunks (README, CHANGELOG, docs/)
    C* = code files with top-level symbols and line ranges
    I* = screenshots usable on screen_split slides

Fail-closed rules:
    - files whose names look like secrets/keys/wallets/env/logs/databases are never read;
    - binaries and files above MAX_TEXT_BYTES are never read;
    - every line that looks like a secret value is redacted before it leaves this module.

Usage:
    python scripts/analyze_project.py <folder> --out work/<slug>/facts.json
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
import tomllib
from pathlib import Path

MAX_TEXT_BYTES = 300_000
README_LINE_CAP = 300
CHANGELOG_LINE_CAP = 60
DOC_LINE_CAP = 160
DOC_FILE_CAP = 12
DOCS_TOTAL_CHARS = 12_000
CODE_INDEX_CAP = 120
SYMBOLS_CAP = 20
IMAGE_CAP = 10
IMAGE_MAX_BYTES = 5 * 1024 * 1024
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
IMAGE_DIR_HINTS = {"docs", "assets", "screenshots", "images", "media", "static", "screens"}
CODE_EXTS = {".py", ".rs", ".ts", ".tsx", ".js", ".mjs", ".go", ".ps1", ".sh"}
ENTRY_NAMES = {"main.py", "__main__.py", "server.py", "app.py", "cli.py", "main.rs", "lib.rs", "index.ts"}

SKIP_DIRS = {
    ".git", ".venv", "venv", "env", "node_modules", "target", "__pycache__",
    ".pytest_cache", ".ruff_cache", ".mypy_cache", ".hypothesis", ".idea", ".vscode",
    ".cursor", ".agents", ".github", "dist", "build", "out", "data", "logs",
    "coverage", ".next", ".cache", "models", "work", "vendor",
}

# File names that must never be read or sent to a model (data, keys, env, logs, configs).
# Source files are NOT excluded by name: their content is redacted line by line instead.
SECRET_NAME_RE = re.compile(
    r"(^\.env|\.key$|\.pem$|\.p12$|\.pfx$|\.kdbx$|\.jks$|\.ovpn$|\.db$|\.sqlite|\.log$|\.jsonl$"
    r"|\.ya?ml$|\.conf$|\.ini$|\.cfg$|\.token$|keystore|mnemonic|^secrets?\.|^credentials?\."
    r"|^api[_-]?keys?\.|^wallet\.(json|dat)$)",
    re.IGNORECASE,
)

KV_SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|secret[_-]?key|secret|token|passw(?:or)?d|private[_-]?key"
    r"|mnemonic|seed[_-]?phrase|authorization)\b(\s*[:=]\s*)(\S+)"
)
# Bare high-entropy strings (hex keys, base58 keys): 40+ alphanumerics, no dots or slashes.
LONG_TOKEN_RE = re.compile(r"(?<![\w/.\-])[A-Za-z0-9]{40,}(?![\w/.\-])")
GITHUB_URL_RE = re.compile(r"https://github\.com/[\w.\-]+(?:/[\w.\-]+)?")
SYMBOL_RE = re.compile(
    r"^(?P<indent>\s*)(?:pub\s+)?(?:export\s+)?(?:async\s+)?(?P<kind>fn|def|class|struct|impl|function|enum|trait)\s+(?P<name>[A-Za-z_]\w*)"
)
COMMENT_RE = re.compile(r"^\s*(?:#|//|///|--)\s*(?P<text>.+)$")


class AnalyzeError(RuntimeError):
    """Raised when the project folder cannot be analyzed safely."""


def redact_line(line: str) -> tuple[str, bool]:
    """Redact secret-looking values. Returns (clean_line, was_redacted)."""
    cleaned = KV_SECRET_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", line)
    cleaned = LONG_TOKEN_RE.sub("[REDACTED]", cleaned)
    return cleaned, cleaned != line


def read_lines(path: Path, stats: dict) -> list[str]:
    if path.stat().st_size > MAX_TEXT_BYTES:
        return []
    raw = path.read_text(encoding="utf-8", errors="replace").splitlines()
    out: list[str] = []
    for line in raw:
        clean, changed = redact_line(line)
        if changed:
            stats["redacted_lines"] += 1
        out.append(clean)
    return out


def walk(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for fn in sorted(filenames):
            yield Path(dirpath) / fn


def rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def project_name_and_description(root: Path, readme_lines: list[str]) -> tuple[str, str]:
    name = root.name
    pyproject = root / "pyproject.toml"
    package_json = root / "package.json"
    if pyproject.is_file():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            name = data.get("project", {}).get("name") or name
        except tomllib.TOMLDecodeError:
            pass
    elif package_json.is_file():
        try:
            name = json.loads(package_json.read_text(encoding="utf-8")).get("name") or name
        except json.JSONDecodeError:
            pass
    description = ""
    for line in readme_lines:
        s = line.strip()
        if s and not s.startswith(("#", "!", "[", "<", "|", "-", "*", "```")):
            description = s[:200]
            break
    return str(name), description


def build_docs(root: Path, stats: dict) -> list[dict]:
    docs: list[dict] = []
    used_chars = 0

    def add(path: Path, cap: int, label_path: str | None = None) -> None:
        nonlocal used_chars
        if used_chars >= DOCS_TOTAL_CHARS:
            return
        lines = read_lines(path, stats)[:cap]
        text = "\n".join(lines)
        room = DOCS_TOTAL_CHARS - used_chars
        if len(text) > room:
            text = text[:room]
        used_chars += len(text)
        docs.append({
            "id": f"D{len(docs) + 1}",
            "path": label_path or rel(path, root),
            "lines": f"1-{len(lines)}",
            "text": text,
        })

    readme = next((p for p in root.iterdir() if p.is_file() and p.name.lower() == "readme.md"), None)
    if readme:
        add(readme, README_LINE_CAP)
    changelog = root / "CHANGELOG.md"
    if changelog.is_file():
        add(changelog, CHANGELOG_LINE_CAP)

    docs_dir = root / "docs"
    if docs_dir.is_dir():
        md_files = sorted(p for p in docs_dir.glob("*.md") if p.is_file() and not SECRET_NAME_RE.search(p.name))
        for p in md_files[:DOC_FILE_CAP]:
            add(p, DOC_LINE_CAP)
        adr_dir = docs_dir / "adr"
        if adr_dir.is_dir():
            titles = []
            for p in sorted(adr_dir.glob("*.md"))[:40]:
                first = next((ln for ln in read_lines(p, stats) if ln.startswith("#")), "")
                if first:
                    titles.append(f"{p.name}: {first.lstrip('# ').strip()}")
            if titles:
                add_text = "\n".join(titles)
                room = DOCS_TOTAL_CHARS - used_chars
                if room > 0:
                    docs.append({
                        "id": f"D{len(docs) + 1}",
                        "path": "docs/adr/ (titles)",
                        "lines": f"{len(titles)} entries",
                        "text": add_text[:room],
                    })
    stats["doc_files"] = len(docs)
    return docs


def summarize_code(lines: list[str], suffix: str) -> tuple[str, list[dict]]:
    summary = ""
    if suffix == ".py":
        text = "\n".join(lines)
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return "unparsed python module", []
        doc = ast.get_docstring(tree) or ""
        summary = (doc.splitlines()[0] if doc else "")[:160]
        symbols = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                kind = "def"
            elif isinstance(node, ast.ClassDef):
                kind = "class"
            else:
                continue
            node_doc = ast.get_docstring(node) or ""
            symbols.append({
                "name": node.name,
                "kind": kind,
                "start": node.lineno,
                "end": node.end_lineno or node.lineno,
                "doc": (node_doc.splitlines()[0] if node_doc else "")[:160],
            })
        return summary, symbols[:SYMBOLS_CAP]

    for ln in lines[:10]:
        m = COMMENT_RE.match(ln)
        if m:
            summary = m.group("text").strip().lstrip("!/ ").strip()[:160]
            break
    starts = []
    for idx, ln in enumerate(lines, start=1):
        m = SYMBOL_RE.match(ln)
        if m and len(m.group("indent")) <= 4:
            starts.append((idx, m.group("kind"), m.group("name")))
    symbols = []
    for i, (start, kind, name) in enumerate(starts):
        end = starts[i + 1][0] - 1 if i + 1 < len(starts) else len(lines)
        doc = ""
        if start >= 2:
            prev = COMMENT_RE.match(lines[start - 2])
            if prev:
                doc = prev.group("text").strip().lstrip("!/ ").strip()[:160]
        symbols.append({"name": name, "kind": kind, "start": start, "end": max(start, end), "doc": doc})
    return summary, symbols[:SYMBOLS_CAP]


def build_code(root: Path, stats: dict) -> list[dict]:
    candidates = []
    for path in walk(root):
        if path.suffix.lower() not in CODE_EXTS or SECRET_NAME_RE.search(path.name):
            continue
        lines = read_lines(path, stats)
        is_entry = path.name in ENTRY_NAMES or path.name.startswith("run_")
        if not lines or (len(lines) < 5 and not is_entry):
            continue
        # Entry points first, then the largest substantive files.
        candidates.append((0 if is_entry else 1, -min(len(lines), 2000), rel(path, root), path, lines))
    candidates.sort(key=lambda c: (c[0], c[1], c[2]))
    stats["code_files_total"] = len(candidates)
    entries = []
    for _, _, relpath, path, lines in candidates[:CODE_INDEX_CAP]:
        summary, symbols = summarize_code(lines, path.suffix.lower())
        entries.append({
            "id": f"C{len(entries) + 1}",
            "path": relpath,
            "line_count": len(lines),
            "summary": summary,
            "symbols": symbols,
        })
    stats["code_files_indexed"] = len(entries)
    return entries


def build_images(root: Path, stats: dict) -> list[dict]:
    found = []
    for path in walk(root):
        if path.suffix.lower() not in IMAGE_EXTS:
            continue
        if path.stat().st_size > IMAGE_MAX_BYTES:
            continue
        parts = Path(rel(path, root)).parts
        if len(parts) > 1 and parts[0].lower() not in IMAGE_DIR_HINTS:
            continue
        found.append(rel(path, root))
    found.sort()
    images = [{"id": f"I{i + 1}", "path": p} for i, p in enumerate(found[:IMAGE_CAP])]
    stats["images"] = len(images)
    return images


def collect_urls(texts: list[str]) -> list[str]:
    urls: set[str] = set()
    for text in texts:
        urls.update(GITHUB_URL_RE.findall(text))
    return sorted(urls)


def analyze(root: Path) -> dict:
    if not root.is_dir():
        raise AnalyzeError(f"Project folder not found: {root}")
    stats = {"redacted_lines": 0, "excluded_secret_like_names": 0}

    readme_path = next((p for p in root.iterdir() if p.is_file() and p.name.lower() == "readme.md"), None)
    readme_lines = read_lines(readme_path, stats)[:README_LINE_CAP] if readme_path else []
    name, description = project_name_and_description(root, readme_lines)

    docs = build_docs(root, stats)
    code = build_code(root, stats)
    images = build_images(root, stats)

    for path in walk(root):
        if SECRET_NAME_RE.search(path.name):
            stats["excluded_secret_like_names"] += 1

    urls = collect_urls([d["text"] for d in docs])
    return {
        "schema": "dup-presenter.facts.v1",
        "root": str(root.resolve()),
        "root_name": root.name,
        "project": {"name": name, "description": description},
        "urls": urls,
        "docs": docs,
        "code": code,
        "images": images,
        "stats": stats,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="DUP Presenter project analyzer")
    parser.add_argument("folder", help="Path to the project folder")
    parser.add_argument("--out", required=True, help="Where to write facts.json")
    args = parser.parse_args()

    facts = analyze(Path(args.folder).resolve())
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[analyze] project={facts['project']['name']} docs={len(facts['docs'])} "
          f"code={len(facts['code'])}/{facts['stats'].get('code_files_total', 0)} "
          f"images={len(facts['images'])} redacted_lines={facts['stats']['redacted_lines']}")
    print(f"[analyze] wrote {out}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AnalyzeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(2)
