"""Click audit for the local console: every visible control in every tab is clicked once.

What it proves (per control):
  - "api"      : the click sent at least one request to /api/... (the control is wired to the backend)
  - "ui-only"  : the click sent no request (tab switch, toggle, copy, language/theme, details); listed for review
  - "failed"   : Playwright could not click it, or the page raised an error during the click
  - "skipped"  : hidden or disabled at the time of the check

Safety: every POST/PUT/DELETE to the console is intercepted and answered with a mock
`{"ok": true, "mocked": true}`. Nothing is rendered, uploaded to TikTok, written to decks or sent to a
paid API during the audit. This verifies WIRING (the right request is sent), not backend results; backend
behaviour is covered by the unit tests. GET requests go to the real server.

Requires a running console and Playwright with Chromium. Writes out/preview/click_audit.json.
Exit code 0 only when there are no "failed" controls and no 5xx responses.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "out" / "preview" / "click_audit.json"
TABS = ["new", "edit", "merge", "logs", "3d"]
# Superset of the response fields the console handlers read, so a mocked POST does not crash a handler
# (e.g. critique reads d.add.length). Mock shape only; real results are covered by unit tests.
# Controls that refuse to act on empty input (they show a validation message instead). Filling a sample
# value lets the audit prove the request is sent. Only mocked POST endpoints are involved.
# Controls deliberately NOT clicked: they call external services (a real network GET to Wikimedia / NASA /
# Openverse), which an offline audit must not do. Reported as skipped with the reason, not as passing.
EXTERNAL_NETWORK = {
    "arcSearchBtn": "calls external archive APIs (Wikimedia / NASA / Openverse); verify manually",
}
PREFILL = {
    "ideaGenBtn": ("#ideaTopicInput", "Тестовая тема для аудита"),
    "mdImportBtn": ("#mdImportInput", "# Аудит\n## Слайд\n- пункт"),
}
MOCK_RESPONSE = {
    "ok": True, "mocked": True, "slug": "click-audit", "ideas": [], "items": [], "jobs": [],
    "add": [], "remove": [], "upgrade": [], "changes": [], "score": 0, "slide_count": 0,
    "critique": {"score": 0, "add": [], "remove": [], "upgrade": []},
    "bytes": 0, "out": "", "slides": 0, "aspect": "", "preset": "", "warnings": [], "errors": [],
}
SETTLE_SEC = 0.7
MAX_PER_TAB = 200


def _label(loc) -> str:
    try:
        ident = loc.get_attribute("id") or ""
        text = (loc.inner_text(timeout=500) or "").strip().replace("\n", " ")
        if not text:
            text = (loc.get_attribute("aria-label") or loc.get_attribute("title") or loc.get_attribute("placeholder") or "")
        return (f"#{ident} " if ident else "") + text[:60]
    except Exception:  # noqa: BLE001 - label is best-effort only
        return "?"


_OPEN_DETAILS_JS = """(scope) => {
  const root = scope ? document.querySelector(scope) : document.body;
  if (root) root.querySelectorAll('details').forEach(d => { d.open = true; });
}"""


def _group_controls(page, scope: str) -> list[dict]:
    """Return one descriptor per control in `scope` (a CSS selector, or "" for header/sidebar controls).

    Indices are positions in the full querySelectorAll list of the scope, so they match the Playwright
    locator built in `_nth_control`. Closed <details> are opened first so their controls are reachable.
    """
    return page.evaluate(
        """(scope) => {
          const root = scope ? document.querySelector(scope) : document.body;
          if (!root) return [];
          if (scope) root.querySelectorAll('details').forEach(d => { d.open = true; });
          const sel = 'button, summary, input[type=checkbox], input[type=button], input[type=submit], [role=button]';
          const out = [];
          root.querySelectorAll(sel).forEach((el, i) => {
            // Header/sidebar group: skip everything that belongs to a tab section or is a tab switch button.
            if (!scope && (el.closest('section.tab') || el.hasAttribute('data-tab'))) return;
            const r = el.getBoundingClientRect();
            const visible = r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden';
            const disabled = !!el.disabled;
            const label = (el.id ? '#' + el.id + ' ' : '') + (el.innerText || el.getAttribute('aria-label') || el.title || el.placeholder || '').trim().replace(/\\s+/g, ' ').slice(0, 60);
            out.push({index: i, id: el.id || '', label, visible, disabled, tag: el.tagName.toLowerCase(), type: el.type || ''});
          });
          return out;
        }""",
        scope,
    )


def _nth_control(page, scope: str, index: int, el_id: str = ""):
    """Locate one control. Controls with an id are located by id, so re-rendered lists (merge queue)
    cannot shift them. Others fall back to their index in the scope.

    `:is(...)` keeps the scope prefix over the whole selector list. A bare "scope a, b, c" would
    apply the scope only to "a" and match "b, c" across the whole page (wrong element for index).
    """
    if el_id:
        return page.locator(f"#{el_id}")
    sel = "button, summary, input[type=checkbox], input[type=button], input[type=submit], [role=button]"
    base = f"{scope} " if scope else ""
    return page.locator(f"{base}:is({sel})").nth(index)


_BLOCKER_JS = """([scope, index, elId]) => {
  const root = scope ? document.querySelector(scope) : document.body;
  const sel = 'button, summary, input[type=checkbox], input[type=button], input[type=submit], [role=button]';
  const el = elId ? document.getElementById(elId) : (root ? root.querySelectorAll(sel)[index] : null);
  if (!el) return 'element not found';
  const r = el.getBoundingClientRect();
  const det = el.closest('details');
  const top = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
  const topDesc = top ? (top.tagName.toLowerCase() + (top.id ? '#' + top.id : '') + ' "' + (top.innerText || '').trim().slice(0, 30) + '"') : 'none';
  return JSON.stringify({
    rect: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)],
    disabled: !!el.disabled,
    detailsOpen: det ? det.open : null,
    topmost: topDesc,
    covered: !!top && !el.contains(top),
  });
}"""


def _blocker(page, scope: str, index: int, el_id: str = "") -> str:
    """Describe why a control could not be clicked: geometry, disabled state, and the element on top of it."""
    try:
        return str(page.evaluate(_BLOCKER_JS, [scope, index, el_id]))
    except Exception as exc:  # noqa: BLE001 - diagnostics must never mask the original finding
        return f"diagnostic failed: {str(exc).splitlines()[0][:80]}"


def _fmt_page_error(err) -> str:
    """Keep the message plus the first stack frame, so the source of an uncaught error is visible."""
    message = getattr(err, "message", None) or str(err)
    stack_lines = (getattr(err, "stack", None) or "").splitlines()
    frame = stack_lines[1].strip() if len(stack_lines) > 1 else ""
    return f"{message} @ {frame}"[:240]


def run_audit(url: str) -> dict:
    results: list[dict] = []
    http_5xx: list[str] = []
    requests_seen: list[tuple[str, str]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            page_errors: list[str] = []
            page.on("pageerror", lambda e: page_errors.append(_fmt_page_error(e)))
            page.on("dialog", lambda d: d.dismiss())

            def on_route(route, request):
                url_path = request.url.split("?")[0].split("127.0.0.1:8790")[-1]
                if request.method != "GET" and url_path.startswith("/api/"):
                    requests_seen.append((request.method, url_path))
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(MOCK_RESPONSE),
                    )
                    return
                route.continue_()

            page.route("**/api/**", on_route)

            def on_response(resp):
                if resp.url.startswith(url.rstrip("/")) and resp.status >= 500:
                    http_5xx.append(f"{resp.status} {resp.url}")

            page.on("response", on_response)

            page.goto(url, wait_until="networkidle")

            # Global controls (header / sidebar) are audited once, on the first tab.
            scopes = [("global", "")] + [(t, f"#tab-{t}") for t in TABS]
            for tab_name, scope in scopes:
                if tab_name != "global":
                    page.click(f'[data-tab="{tab_name}"]')
                    page.wait_for_timeout(300)
                descriptors = _group_controls(page, scope)
                for d in descriptors[:MAX_PER_TAB]:
                    row = {"group": tab_name, "label": d["label"], "tag": d["tag"], "type": d["type"]}
                    if not d["visible"] or d["disabled"]:
                        row.update(status="skipped", reason="hidden" if not d["visible"] else "disabled", requests=[])
                        results.append(row)
                        continue
                    if d["id"] in EXTERNAL_NETWORK:
                        row.update(status="skipped", reason=EXTERNAL_NETWORK[d["id"]], requests=[])
                        results.append(row)
                        continue
                    if tab_name != "global":
                        page.click(f'[data-tab="{tab_name}"]')
                        page.wait_for_timeout(150)
                    before = len(requests_seen)
                    errors_before = len(page_errors)
                    try:
                        # Clicking a <summary> closes its disclosure; re-open before each click so the
                        # controls inside it stay reachable (a closed <details> hides its children).
                        page.evaluate(_OPEN_DETAILS_JS, scope)
                        if d["id"] in PREFILL:
                            field_sel, field_value = PREFILL[d["id"]]
                            page.fill(field_sel, field_value, timeout=2000)
                        _nth_control(page, scope, d["index"], d["id"]).click(timeout=3000)
                        page.wait_for_timeout(int(SETTLE_SEC * 1000))
                        click_error = None
                    except Exception as exc:  # noqa: BLE001 - recorded as a finding, not raised
                        # Playwright's call log ("- waiting for ..." / "- element is not stable" / "intercepts...")
                        # is what names the real reason; keep the last informative lines, not just the header.
                        log_lines = [ln.strip() for ln in str(exc).splitlines() if ln.strip().startswith("-")]
                        reason = " / ".join(dict.fromkeys(log_lines))  # unique, in order
                        click_error = f"{reason[:600]} | blocker: {_blocker(page, scope, d['index'], d['id'])}"
                        page.keyboard.press("Escape")
                    new_requests = requests_seen[before:]
                    new_errors = page_errors[errors_before:]
                    if click_error:
                        status = "failed"
                    elif new_errors:
                        status = "failed"
                    elif new_requests:
                        status = "api"
                    else:
                        status = "ui-only"
                    row.update(
                        status=status,
                        requests=[f"{m} {path}" for m, path in new_requests],
                        error=click_error or ("; ".join(new_errors)[:200] if new_errors else None),
                    )
                    results.append(row)
            browser.close()
        finally:
            try:
                browser.close()
            except Exception:  # noqa: BLE001 - already closed above on success
                pass

    summary: dict[str, dict[str, int]] = {}
    for r in results:
        g = summary.setdefault(r["group"], {"total": 0, "api": 0, "ui-only": 0, "failed": 0, "skipped": 0})
        g["total"] += 1
        g[r["status"]] += 1
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "url": url,
        "summary": summary,
        "http_5xx": http_5xx,
        "controls": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://127.0.0.1:8790/")
    args = parser.parse_args()
    report = run_audit(args.url)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("group    total  api  ui-only  failed  skipped")
    for g, s in report["summary"].items():
        print(f"{g:<8} {s['total']:>5} {s['api']:>4} {s['ui-only']:>8} {s['failed']:>7} {s['skipped']:>8}")
    failed = [c for c in report["controls"] if c["status"] == "failed"]
    for c in failed:
        print(f"[FAILED] {c['group']}: {c['label']} -> {c.get('error')}")
    if report["http_5xx"]:
        print("[5xx]", report["http_5xx"][:10])
    print(f"report: {REPORT}")
    ok = not failed and not report["http_5xx"]
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
