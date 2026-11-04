"""Browser test for BA-0014 and BA-0015 (4 Nov 2026): scroll boxes don't drag each other or the page.
Usage: python3 tests/browser_scroll_test.py <site url>   (fresh database; adds an admin and 30 live cars)
Runs at 1280x440 (a short laptop window, where the Admin menu is taller than the screen).
Covers: the Admin menu ends on the screen and scrolls on its own; scrolling it to its end doesn't move the page; scrolling the
page doesn't move the menu; the same on the Reports menu; the report records scroll in their own frame no taller than the
screen with the column names kept in view, and scrolling the frame doesn't move the page; every scroll box on the page says
overscroll-behavior (chat, pop-up, dropdown list, terms text, Build Assistant); no sideways scroll on a phone."""
import sys, os, json, time, base64, hashlib, hmac, struct, datetime, psycopg2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import admin_session
from playwright.sync_api import sync_playwright
SITE = sys.argv[1]
db = psycopg2.connect(host="/var/tmp/saazpg", port=5433, user="postgres", dbname="sb"); db.autocommit = True; cur = db.cursor()
def sql(q, a=()): cur.execute(q, a or None); return cur.fetchall() if cur.description else None
def user(e, n): return sql("insert into auth.users (email, raw_user_meta_data, email_confirmed_at) values (%s,%s,now()) returning id", (e, json.dumps({"name": n, "country": "UG"})))[0][0]
A = user("sadmin@saaz.test", "Ann Admin"); sql("insert into admins (user_id, name, role) values (%s,'Ann Admin','admin')", (A,))
SEL = user("sseller@x.test", "Sam Seller")
for i in range(30):
    v = sql("insert into vehicles (vin, make, model) values (%s,'Toyota','Premio') returning id", ("JTSCRL%011d" % i,))[0][0]
    sql("""insert into listings (vehicle_id, seller_id, country, region, status, make, model, year, fuel, gearbox, body, colour, engine, mileage, plate, currency, price,
           description, photos, logbook_name_matches, owner_authorised, live_at) values (%s,%s,'UG','Kampala','live','Toyota','Premio',2012,'Petrol','Automatic','Sedan','White','1.5',90000,%s,'UGX',%s,'Clean car',%s,true,true,%s)""",
        (v, SEL, "UBS %03dS" % i, 20000000 + i * 100000, ["a.webp"], datetime.datetime.now(datetime.timezone.utc)))
SECRET = "JBSWY3DPEHPK3PXP"
admin_session.claims(cur, A); cur.execute("reset role"); sql("update auth.mfa_factors set secret=%s", (SECRET,))
def totp(secret):
    k = base64.b32decode(secret); h = hmac.new(k, struct.pack(">Q", int(time.time()) // 30), hashlib.sha1).digest(); o = h[-1] & 15
    return "%06d" % ((struct.unpack(">I", h[o:o + 4])[0] & 0x7fffffff) % 1000000)
ok = bad = 0
def check(n, c, x=""):
    global ok, bad
    if c: ok += 1; print("PASS", n)
    else: bad += 1; print("FAIL", n, str(x)[:300])
errors = []
BOX = """(sel) => { const e = document.querySelector(sel); if (!e) return null; const s = getComputedStyle(e), r = e.getBoundingClientRect();
  return {sh: e.scrollHeight, ch: e.clientHeight, st: e.scrollTop, oy: s.overflowY, ob: s.overscrollBehaviorY, bottom: r.bottom, top: r.top, vh: innerHeight}; }"""
with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={"width": 1280, "height": 440}); pg = ctx.new_page(); pg.on("pageerror", lambda e: errors.append(str(e)))
    def go(h): pg.goto("about:blank"); pg.goto(SITE + h); pg.wait_for_timeout(1400)
    go("#/signin"); pg.check("input[name=as][value=seller]"); pg.fill("input[name=email]", "sadmin@saaz.test"); pg.fill("input[name=password]", "demo1234"); pg.click("form button"); pg.wait_for_timeout(1500)
    go("#/admin/verify"); pg.fill("input[name=password]", "demo1234"); pg.click("#pf button"); pg.wait_for_timeout(1200)
    pg.fill("input[name=code]", totp(SECRET)); pg.click("#cf button"); pg.wait_for_timeout(1800)
    def wheel_on(sel, dy, times=12):
        r = pg.evaluate("(s) => { const b = document.querySelector(s).getBoundingClientRect(); return [b.left + 20, Math.max(b.top, 0) + Math.min(b.height, innerHeight - Math.max(b.top, 0)) / 2]; }", sel)
        pg.mouse.move(r[0], r[1])
        for _ in range(times): pg.mouse.wheel(0, dy); pg.wait_for_timeout(60)
        pg.wait_for_timeout(300)
    for label, route, sel in (("Admin menu", "#/admin/vehicles", "[data-ref=admin-menu]"), ("Reports menu", "#/admin/reports/inventory", "[data-ref=report-menu]")):
        go(route); pg.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
        b = pg.evaluate(BOX, sel)
        check(f"{label}: ends on the screen", b and b["bottom"] <= b["vh"] + 1, b)
        check(f"{label}: scrolls on its own and holds its scroll (overscroll contain)", b and b["oy"] in ("auto", "scroll") and b["ob"] == "contain", b)
        if b and b["sh"] > b["ch"]:
            y0 = pg.evaluate("scrollY"); wheel_on(sel, 400)
            b2 = pg.evaluate(BOX, sel)
            check(f"{label}: scrolling it to its end reaches the end", b2["st"] + b2["ch"] >= b2["sh"] - 2, b2)
            check(f"{label}: scrolling it never moves the page", pg.evaluate("scrollY") == y0, (y0, pg.evaluate("scrollY")))
            pg.evaluate("(s) => { document.querySelector(s).scrollTop = 0; }", sel)
        else:
            check(f"{label}: taller than the screen at 440 px (needed for the test)", False, b)
        st = pg.evaluate(BOX, sel)["st"]; pg.mouse.move(900, 300)
        for _ in range(6): pg.mouse.wheel(0, 300); pg.wait_for_timeout(60)
        pg.wait_for_timeout(300)
        check(f"{label}: scrolling the page doesn't move the menu's own scroll", pg.evaluate(BOX, sel)["st"] == st)
    # BA-0015: the records frame
    go("#/admin/reports/inventory"); pg.evaluate("window.scrollTo(0, 0)")
    fr = ".rtable .tablewrap"
    f = pg.evaluate(BOX, fr)
    check("report frame: scrolls on its own, overscroll contain", f and f["oy"] in ("auto", "scroll") and f["ob"] == "contain", f)
    check("report frame: no taller than the screen", f and f["ch"] <= f["vh"], f)
    if f and f["sh"] > f["ch"]:
        # bring the frame fully into view below the fixed header and area bar, the way a person scrolls down to it
        pg.evaluate("() => { const w = document.querySelector('.rtable .tablewrap'), hb = document.querySelector('.areabar').getBoundingClientRect().bottom; window.scrollBy({top: w.getBoundingClientRect().top - hb - 8, behavior: 'instant'}); }"); pg.wait_for_timeout(600)
        hit = pg.evaluate("() => { const w = document.querySelector('.rtable .tablewrap'), b = w.getBoundingClientRect(); const e = document.elementFromPoint(b.left + 20, b.top + b.height / 2); return w.contains(e); }")
        check("report frame: fully on the screen when scrolled to", hit and pg.evaluate("() => document.querySelector('.rtable .tablewrap').getBoundingClientRect().bottom <= innerHeight + 1"))
        y0 = pg.evaluate("scrollY")
        wheel_on(fr, 300, 20)
        f2 = pg.evaluate(BOX, fr)
        check("report frame: scrolls through the records", f2["st"] > 0, f2)
        check("report frame: scrolling it to its end never moves the page", pg.evaluate("scrollY") == y0, (y0, pg.evaluate("scrollY")))
        th = pg.evaluate("() => { const t = document.querySelector('.rtable thead th').getBoundingClientRect(), w = document.querySelector('.rtable .tablewrap').getBoundingClientRect(); return [t.top - w.top, getComputedStyle(document.querySelector('.rtable thead th')).position]; }")
        check("report frame: column names stay in view while scrolling", th[1] == "sticky" and abs(th[0]) <= 2, th)
    else:
        check("report frame: has more records than fit (needed for the test)", False, f)
    check("report sorting links still work", pg.locator(".rtable thead th a").count() > 0)
    # every scroll box the stylesheet defines says overscroll-behavior (the build checks the CSS; this checks it reaches the page)
    boxes = pg.evaluate("""() => { const out = []; for (const sh of document.styleSheets) { let rules; try { rules = sh.cssRules; } catch (e) { continue; }
      const walk = (rs) => { for (const r of rs) { if (r.cssRules) walk(r.cssRules); if (!r.style) continue;
        const o = r.style.overflowY || r.style.overflow; if (/auto|scroll/.test(o || '') && !r.style.overscrollBehaviorY && !r.style.overscrollBehavior) out.push(r.selectorText); } }; walk(rules); } return out; }""")
    check("every scroll box in the stylesheet holds its scroll", not boxes, boxes)
    ctx.close()
    # phones keep the card list
    ph = br.new_context(viewport={"width": 390, "height": 800}); q = ph.new_page(); q.on("pageerror", lambda e: errors.append(str(e)))
    q.goto(SITE + "#/browse"); q.wait_for_timeout(1500)
    check("phones: no sideways scroll", q.evaluate("() => document.documentElement.scrollWidth <= innerWidth + 1"))
    check("no script errors", not errors, errors[:3])
    br.close()
print(f"\n{ok} passed, {bad} failed")
sys.exit(1 if bad else 0)
