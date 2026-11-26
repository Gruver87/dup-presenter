"""Live browser check for the local console: caption style load, Markdown import, duplicate refusal.

Requires a running console (`python scripts/console_server.py --port 8790`) and Playwright with Chromium
(`python -m playwright install chromium`). Creates a temporary deck and always removes it, even on failure.
Exit code 0 only when every check passes (fail-closed).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SLUG = "ui-import-check"
SOURCE_MD = ROOT / "examples" / "md-talk-demo.md"
SCREENSHOT = ROOT / "out" / "preview" / "console_edit_tab.png"
TEST_DECK = ROOT / "decks" / f"{SLUG}.json"
KARAOKE_DECK = "caption-karaoke-demo"


def _markdown_with_slug() -> str:
    text = SOURCE_MD.read_text(encoding="utf-8")
    return text.replace("slug: md-talk-demo", f"slug: {SLUG}", 1)


def run_checks(url: str) -> bool:
    ok = True
    md_text = _markdown_with_slug()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(url, wait_until="networkidle")
            page.click('[data-tab="edit"]')

            # 1) caption style is loaded from the deck
            page.wait_for_selector("#deckSelect option", state="attached", timeout=15000)
            page.select_option("#deckSelect", KARAOKE_DECK)
            page.wait_for_function(
                "document.querySelector('#editCaptionStyleSelect').value === 'karaoke'", timeout=15000
            )
            style = page.input_value("#editCaptionStyleSelect")
            print(f"[check] {KARAOKE_DECK} -> editCaptionStyleSelect = {style!r}")
            ok &= style == "karaoke"

            # 2) Markdown import creates the deck and selects it
            page.locator("details", has=page.locator("#mdImportInput")).locator("summary").click()
            page.fill("#mdImportInput", md_text)
            page.click("#mdImportBtn")
            page.wait_for_function(
                "['OK', 'Error'].some(p => document.querySelector('#mdImportMsg').textContent.startsWith(p))",
                timeout=20000,
            )
            msg = page.text_content("#mdImportMsg")
            print(f"[check] import message: {msg!r}")
            ok &= msg == f"OK ({SLUG})"
            page.wait_for_function(f"document.querySelector('#deckSelect').value === '{SLUG}'", timeout=15000)

            # 3) duplicate import is refused
            page.click("#mdImportBtn")
            page.wait_for_function(
                "document.querySelector('#mdImportMsg').textContent.startsWith('Error')", timeout=20000
            )
            dup_msg = page.text_content("#mdImportMsg")
            print(f"[check] duplicate import: {dup_msg!r}")
            ok &= "already exists" in (dup_msg or "")

            # 4) web-search checkbox: disabled with a visible reason in template mode, clickable with an LLM source
            page.click('[data-tab="new"]')
            page.select_option("#ideaModeSelect", "template")
            tpl = page.evaluate(
                "() => ({disabled: document.getElementById('ideaWebSearchCheck').disabled, "
                "hint: document.getElementById('webSearchHint').textContent})"
            )
            print(f"[check] web search in template mode: {tpl}")
            ok &= tpl["disabled"] is True and "Недоступно" in tpl["hint"]
            page.select_option("#ideaModeSelect", "cloud")
            page.click("#ideaWebSearchCheck")
            cloud = page.evaluate("() => document.getElementById('ideaWebSearchCheck').checked")
            print(f"[check] web search with cloud source, after click: checked={cloud}")
            ok &= cloud is True
            page.uncheck("#ideaWebSearchCheck")
            page.click('[data-tab="edit"]')

            SCREENSHOT.parent.mkdir(parents=True, exist_ok=True)
            page.locator("#tab-edit").screenshot(path=str(SCREENSHOT))
            print(f"[check] screenshot -> {SCREENSHOT}")

            print(f"[check] page errors: {errors or 'none'}")
            ok &= not errors
        finally:
            browser.close()
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8790/", help="console URL")
    args = parser.parse_args()
    try:
        ok = run_checks(args.url)
    finally:
        if TEST_DECK.exists():
            TEST_DECK.unlink()
            print(f"[check] removed test deck {TEST_DECK.name}")
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
