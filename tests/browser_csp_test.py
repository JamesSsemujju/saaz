"""The security policy on every page: nothing the site needs is blocked, outside scripts are, and Saaz won't run in a frame.
Run after tests/stack/sync.sh, with the local stack up (site on :8777)."""
import pathlib, sys
from playwright.sync_api import sync_playwright
SITE = "http://localhost:8777/saaz/"; ROOT = pathlib.Path("/home/claude/stk/srv/saaz")
ok = bad = 0
def check(n, c, x=""):
    global ok, bad
    if c: ok += 1; print("PASS", n)
    else: bad += 1; print("FAIL", n, x)
pages = sorted(str(p.relative_to(ROOT)) for p in ROOT.rglob("*.html"))
check("every built page carries the security policy", all("Content-Security-Policy" in (ROOT / p).read_text() for p in pages), [p for p in pages if "Content-Security-Policy" not in (ROOT / p).read_text()])
check("every built page sets a referrer policy", all('name="referrer"' in (ROOT / p).read_text() for p in pages))
check("no page loads a script from another site", not [p for p in pages if "<script src=\"http" in (ROOT / p).read_text()])
APP = ["#/browse", "#/signin", "#/signup", "#/forgot", "#/verify", "#/report/sample", "#/sell", "#/how", "#/garage/apply"]
with sync_playwright() as pw:
    br = pw.chromium.launch(); ctx = br.new_context(viewport={"width": 1280, "height": 900}); pg = ctx.new_page()
    blocked = []; errs = []
    pg.on("console", lambda m: blocked.append((pg.url, m.text)) if "Content Security Policy" in m.text else None)
    pg.on("pageerror", lambda e: errs.append((pg.url, str(e))))
    for p in pages:
        pg.goto(SITE + p); pg.wait_for_timeout(250)
    for h in APP:
        pg.goto("about:blank"); pg.goto(SITE + h); pg.wait_for_timeout(900)
    check(f"{len(pages)} pages and {len(APP)} app screens: nothing blocked by the policy", not blocked, blocked[:5])
    check("no script errors", not errs, errs[:3])
    pg.goto(SITE + "#/report/sample"); pg.wait_for_timeout(1500)
    check("sample report draws its QR code from the self-hosted library", pg.locator(".report canvas, .report img[src^='data:'], .qr canvas, .qr img").count() > 0)
    check("print button works without inline script", pg.locator("[data-print]").count() == 1 and pg.locator("[onclick]").count() == 0)
    # An outside script injected into the page is refused
    pg.goto(SITE + "#/browse"); pg.wait_for_timeout(800); blocked.clear()
    pg.evaluate("() => { const s = document.createElement('script'); s.src = 'https://example.com/x.js'; document.head.appendChild(s); }"); pg.wait_for_timeout(300)
    check("a script from another site is refused", any("example.com" in t for _, t in blocked), blocked)
    blocked.clear(); pg.evaluate("() => { document.body.insertAdjacentHTML('beforeend', '<img src=x onerror=\"window.__pwned=1\">'); }"); pg.wait_for_timeout(300)
    check("an injected inline event handler does not run", pg.evaluate("() => window.__pwned") is None)
    # Framing: a page on another origin puts Saaz in a frame
    fr = ctx.new_page(); fr.set_content(f"<iframe id=f src='{SITE}#/browse' width=800 height=600></iframe>"); fr.wait_for_timeout(2500)
    inner = fr.frames[1] if len(fr.frames) > 1 else None
    framed_ok = inner is None or inner.evaluate("() => document.querySelector('#app') === null || document.body === null || document.body.innerText.trim() === ''")
    check("Saaz draws nothing inside another site's frame", framed_ok)
    br.close()
print(f"\n{ok} passed, {bad} failed"); sys.exit(1 if bad else 0)
