"""Refit the deck_doctor speech-length model (VOICE_FIT) from build logs.

Reads out/*_build.log ([tts] lines) and decks/*.json (narration word count per slide),
then prints a least-squares line per language. Run after changing voices:
    python scripts/calibrate_speech.py
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TTS_RE = re.compile(r"\[tts\] (\S+) \([^)]*\): ([\d.]+)s(?: \([^)]*\))? -> slide (\d+)s")
TAG_RE = re.compile(r"<[^>]+>")

samples = {"en": [], "ru": []}
for log in sorted((ROOT / "out").glob("*_build.log")):
    slug = log.name[: -len("_build.log")]
    deck_path = ROOT / "decks" / f"{slug}.json"
    if not deck_path.exists():
        continue
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    lang = deck.get("lang", "ru")
    by_id = {s["id"]: s for s in deck["slides"]}
    raw = log.read_bytes()
    # PowerShell `*>` writes UTF-16 LE with BOM; other logs are UTF-8.
    text_log = raw.decode("utf-16") if raw[:2] == b"\xff\xfe" else raw.decode("utf-8", errors="replace")
    for m in TTS_RE.finditer(text_log):
        sid, tts_sec = m.group(1), float(m.group(2))
        s = by_id.get(sid)
        if not s:
            continue
        text = s.get("voice_text") or TAG_RE.sub(" ", s.get("voice_ssml", "") or "")
        words = len(text.split())
        if words:
            samples[lang].append((slug, sid, words, tts_sec))

for lang, rows in samples.items():
    if len(rows) < 2:
        print(lang, "not enough samples", len(rows))
        continue
    n = len(rows)
    xs = [r[2] for r in rows]
    ys = [r[3] for r in rows]
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx if sxx else 0
    intercept = my - slope * mx
    wps = 1 / slope if slope else 0
    errs = [abs((intercept + slope * x) - y) for x, y in zip(xs, ys)]
    print(f"{lang}: n={n} seconds = {intercept:.2f} + {slope:.3f} * words  (words/sec ~ {wps:.2f}); "
          f"mean abs err {sum(errs)/n:.2f}s, max {max(errs):.2f}s")
    for r in rows:
        print(f"   {r[0]:24s} {r[1]:4s} words={r[2]:3d} tts={r[3]:6.2f}s")

