"""Browser test for the link standard (links.css, 7 Nov 2026) on the local stack.
Usage: python3 tests/browser_links_test.py <site url>   (fresh database; it adds its own people and cars)
Title links draw a line from the left on hover and draw it back on leaving; other links brighten; links in sentences keep
a faint underline; keyboard focus shows the line; on touch screens arrow links always show their line; with reduced motion
nothing animates; no link outside the kept cases (solid buttons, listing cards, report tiles, the logo) has a box,
background or border, on the public pages and in Admin. SHOTS=<dir> saves screenshots."""
import sys, os, json, time, base64, hashlib, hmac, struct, psycopg2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import admin_session
from playwright.sync_api import sync_playwright
SITE = sys.argv[1]
db = psycopg2.connect(host="/var/tmp/saazpg", port=5433, user="postgres", dbname="sb"); db.autocommit = True; cur = db.cursor()
def sql(q, a=()): cur.execute("reset role; select set_config('request.jwt.claims','',false)"); cur.execute(q, a or None); return cur.fetchall() if cur.description else None
def user(e, n): return sql("insert into auth.users (email, raw_user_meta_data, email_confirmed_at) values (%s,%s,now()) returning id", (e, json.dumps({"name": n, "country": "UG"})))[0][0]
A = user("ladmin@saaz.test", "Ann Admin"); sql("insert into admins (user_id, name, role) values (%s,'Ann Admin','admin')", (A,))
S = user("lseller@x.test", "Sam Seller")
SECRET = "JBSWY3DPEHPK3PXP"; admin_session.claims(cur, A); cur.execute("reset role"); sql("update auth.mfa_factors set secret=%s", (SECRET,))
sql("insert into vehicles (vin,make,model) select 'LNKX'||lpad(g::text,13,'0'),'Toyota','Harrier' from generate_series(1,3) g")
sql("""insert into listings (vehicle_id, seller_id, country, region, status, make, model, year, fuel, gearbox, body, colour, engine, mileage, plate, currency, price, description, photos,
       logbook_name_matches, owner_authorised, live_at) select v.id, %s, 'UG','Kampala','live',v.make,v.model,2015,'Petrol','Automatic','SUV','White','2.0',50000,'ULK '||right(v.vin,3)||'A','UGX',90000000,
       'Clean car, one owner, full service history.',array['x.webp'],true,true,now() from vehicles v where v.vin like 'LNKX%%'""", (S,))
REF = sql("select ref from listings order by ref limit 1")[0][0]
def totp(secret):
    k = base64.b32decode(secret); h = hmac.new(k, struct.pack(">Q", int(time.time()) // 30), hashlib.sha1).digest(); o = h[-1] & 15
    return "%06d" % ((struct.unpack(">I", h[o:o + 4])[0] & 0x7fffffff) % 1000000)
ok = bad = 0
def check(n, c, x=""):
    global ok, bad
    if c: ok += 1; print("PASS", n)
    else: bad += 1; print("FAIL", n, str(x)[:500])
LINE = "el => { if (getComputedStyle(el).backgroundImage === 'none') return 0; const s = getComputedStyle(el).backgroundSize.split(' ')[0]; return s.endsWith('%') ? parseFloat(s) : (parseFloat(s) / el.getBoundingClientRect().width * 100); }"
# A link that looks like a box: a background, a border or a shadow (rings around a link), at rest. Kept on purpose:
# solid buttons (a.btn without ghost/text/go), listing cards, report tiles, the admin side menu's current marker, the logo.
BOXY = r"""() => [...document.querySelectorAll('a')].filter(a => a.offsetParent && !a.matches('a.btn:not(.ghost):not(.text):not(.go), a.car, .rkpis a, a.logo, .skip')).filter(a => {
  const c = getComputedStyle(a); const bg = c.backgroundColor, bd = ['Top','Right','Bottom','Left'].some(s => parseFloat(c['border'+s+'Width']) > 0 && c['border'+s+'Style'] !== 'none');
  return (bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent') || bd || (c.boxShadow !== 'none' && !/^(rgba\(0, 0, 0, 0\)|transparent)/.test(c.boxShadow) && !a.matches('[aria-current]'));
}).map(a => (a.className || a.tagName) + ': ' + a.textContent.trim().slice(0, 30))"""
errors = []; SHOTS = os.environ.get("SHOTS")
with sync_playwright() as p:
    br = p.chromium.launch()
    def page(w=1280, **kw):
        ctx = br.new_context(viewport={"width": w, "height": 900}, **kw); pg = ctx.new_page(); pg.on("pageerror", lambda e: errors.append(str(e))); return pg
    def go(pg, h): pg.goto("about:blank"); pg.goto(SITE + h); pg.wait_for_timeout(1300)

    pg = page(); go(pg, "#/")
    see = pg.locator("[data-ref=latest-cars] a.btn.text").first
    check("title link with the arrow: no line at rest", see.evaluate(LINE) < 1, see.evaluate(LINE))
    check("the line grows from the left", see.evaluate("el => getComputedStyle(el).backgroundPosition").startswith("0%") or see.evaluate("el => getComputedStyle(el).backgroundPosition").startswith("0px"))
    see.hover(); pg.wait_for_timeout(120); mid = see.evaluate(LINE)
    pg.wait_for_timeout(400); full = see.evaluate(LINE)
    check("on hover the line draws across (part way at 120 ms, whole by 520 ms)", 2 < mid < 99 and full > 99, (mid, full))
    if SHOTS: see.screenshot(path=os.path.join(SHOTS, "Saaz_Links_TitleHover_2026-11-07.png"))
    pg.mouse.move(5, 600); pg.wait_for_timeout(120); back = see.evaluate(LINE); pg.wait_for_timeout(400)
    check("leaving draws it back the same way", 1 < back < 99 and see.evaluate(LINE) < 1, (back, see.evaluate(LINE)))
    dur = see.evaluate("el => getComputedStyle(el).transitionDuration")
    check("one tuned timing for the line (340 ms)", "0.34s" in dur, dur)

    card = pg.locator("[data-ref=latest-cars] .car").first
    card.hover(); pg.wait_for_timeout(450)
    check("a listing card stays a card; hovering it draws the line under its name", card.locator(".car-name>span").evaluate(LINE) > 99)
    check("only the name's own line shows (no full-width line under the card title)", card.locator(".car-name").evaluate("el => getComputedStyle(el).boxShadow") == "none")
    nm = card.locator(".car-name>span").evaluate("el => el.getBoundingClientRect().width"); box = card.evaluate("el => el.getBoundingClientRect().width")
    check("the line follows the name, not the whole card", nm < box, (nm, box))

    nav = pg.locator(".appnav a").nth(1)
    nav.hover(); pg.wait_for_timeout(450)
    check("main menu: the line draws under the item on hover", nav.evaluate(LINE) > 99)
    foot = pg.locator(".site-footer .foot-grid a").first if pg.locator(".site-footer .foot-grid a").count() else None
    if foot:
        before = foot.evaluate("el => getComputedStyle(el).color"); foot.hover(); pg.wait_for_timeout(300); after = foot.evaluate("el => getComputedStyle(el).color")
        check("footer link: brighter on hover, no line, no box", before != after and foot.evaluate(LINE) < 1 and foot.evaluate("el => getComputedStyle(el).textDecorationLine") == "none" and foot.evaluate("el => getComputedStyle(el).backgroundColor") in ("rgba(0, 0, 0, 0)", "transparent"), (before, after))

    # keyboard
    go(pg, "#/browse"); pg.keyboard.press("Tab")
    for _ in range(40):
        if pg.evaluate("document.activeElement && document.activeElement.matches('a.btn.text, a.btn.ghost, .appnav a')"): break
        pg.keyboard.press("Tab")
    pg.wait_for_timeout(450)
    check("keyboard focus shows the line and the focus ring", pg.evaluate("document.activeElement.matches('a.btn.text, a.btn.ghost, .appnav a')") and pg.evaluate("(" + LINE + ")(document.activeElement)") > 99
          and pg.evaluate("getComputedStyle(document.activeElement).outlineStyle") != "none")

    # links inside sentences: faint underline at rest
    go(pg, "#/car/" + REF)
    crumb = pg.locator(".crumbs a").first
    check("a link inside text keeps a faint underline at rest", crumb.evaluate("el => getComputedStyle(el).textDecorationLine").startswith("underline") or crumb.evaluate("el => getComputedStyle(el).textDecorationLine") == "underline")

    # no boxes around links, public pages
    found = {}
    for h in ("#/", "#/browse", "#/car/" + REF, "#/selling", "#/verify", "#/signin", "#/sell"):
        go(pg, h); b = pg.evaluate(BOXY)
        if b: found[h] = b
    check("public pages: no link is drawn as a box", not found, found)

    # Admin
    a = page(); go(a, "#/signin"); a.check("input[name=as][value=buyer]"); a.fill("input[name=email]", "ladmin@saaz.test"); a.fill("input[name=password]", "demo1234"); a.click("form button"); a.wait_for_timeout(1500)
    go(a, "#/admin/verify"); a.fill("input[name=password]", "demo1234"); a.click("#pf button"); a.wait_for_timeout(1200); a.fill("input[name=code]", totp(SECRET)); a.click("#cf button"); a.wait_for_timeout(1800)
    found = {}
    for h in ("#/admin", "#/admin/cars", "#/admin/users", "#/admin/garages", "#/admin/team", "#/admin/settings", "#/admin/reports", "#/account", "#/inbox"):
        go(a, h); b = a.evaluate(BOXY)
        if b: found[h] = b
    check("Admin and account pages: no link is drawn as a box", not found, found)
    side = a.locator(".adminside a:not([aria-current])").first
    if side.count():
        c0 = side.evaluate("el => getComputedStyle(el).color"); side.hover(); a.wait_for_timeout(300)
        check("Admin side menu: brighter on hover, no background", side.evaluate("el => getComputedStyle(el).color") != c0 and side.evaluate("el => getComputedStyle(el).backgroundColor") in ("rgba(0, 0, 0, 0)", "transparent"))
    a.click(".acctmenu-btn, #acct summary") if a.locator("#acct summary").count() else None; a.wait_for_timeout(300)
    mi = a.locator(".acctmenu a").first
    if mi.count() and mi.is_visible():
        mi.hover(); a.wait_for_timeout(300)
        check("account menu: brighter on hover, no grey box", mi.evaluate("el => getComputedStyle(el).backgroundColor") in ("rgba(0, 0, 0, 0)", "transparent"))

    # touch: no hover, so the arrow links always show their line
    t = page(390, has_touch=True, is_mobile=True); go(t, "#/")
    check("touch: arrow links show their line without hover", t.locator("[data-ref=latest-cars] a.btn.text").first.evaluate(LINE) > 99)
    # reduced motion: no drawing, it simply appears
    r = page(reduced_motion="reduce"); go(r, "#/")
    check("reduced motion: the line doesn't animate", "background-size" not in r.locator("[data-ref=latest-cars] a.btn.text").first.evaluate("el => getComputedStyle(el).transitionProperty"))
    check("no script errors", not errors, errors[:3])
    br.close()
print(f"\n{ok} passed, {bad} failed")
