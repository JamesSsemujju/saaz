"""Browser test for BA-0016 (4 Nov 2026): moving between pages feels like one app.
Usage: python3 tests/browser_navigation_test.py <site url> <width>   (fresh database; adds an admin, a seller and 30 live cars)
Covers, in Admin: the header, area bar and Admin menu are the same elements after every move (not rebuilt), the menu keeps its
scroll, the current item moves; the page area is never blank and never shows "Loading" between pages; "who you are" is asked
once for many moves, not on every click; the scheduler step at most once a minute; fast clicking ends on the last page clicked
with nothing older drawn over it; on a slow network the old page stays (dimmed, not clickable) until the new one is ready; a
return visit shows the last view at once, then the fresh one; Reports work the same way; the marketplace keeps the page area
while its header changes; reduced motion has no animation; no script errors."""
import sys, os, json, time, base64, hashlib, hmac, struct, datetime, psycopg2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import admin_session
from playwright.sync_api import sync_playwright
SITE, W = sys.argv[1], int(sys.argv[2])
db = psycopg2.connect(host="/var/tmp/saazpg", port=5433, user="postgres", dbname="sb"); db.autocommit = True; cur = db.cursor()
def sql(q, a=()): cur.execute(q, a or None); return cur.fetchall() if cur.description else None
def user(e, n): return sql("insert into auth.users (email, raw_user_meta_data, email_confirmed_at) values (%s,%s,now()) returning id", (e, json.dumps({"name": n, "country": "UG"})))[0][0]
A = user("nvadmin@saaz.test", "Ann Admin"); sql("insert into admins (user_id, name, role) values (%s,'Ann Admin','admin')", (A,))
SEL = user("nvseller@x.test", "Sam Seller")
for i in range(30):
    v = sql("insert into vehicles (vin, make, model) values (%s,'Toyota','Premio') returning id", ("JTNAVG%011d" % i,))[0][0]
    sql("""insert into listings (vehicle_id, seller_id, country, region, status, make, model, year, fuel, gearbox, body, colour, engine, mileage, plate, currency, price,
           description, photos, logbook_name_matches, owner_authorised, live_at) values (%s,%s,'UG','Kampala','live','Toyota','Premio',2012,'Petrol','Automatic','Sedan','White','1.5',90000,%s,'UGX',%s,'Clean car',%s,true,true,%s)""",
        (v, SEL, "UBN %03dN" % i, 20000000 + i * 100000, ["a.webp"], datetime.datetime.now(datetime.timezone.utc)))
SECRET = "JBSWY3DPEHPK3PXP"
admin_session.claims(cur, A); cur.execute("reset role"); sql("update auth.mfa_factors set secret=%s", (SECRET,))
def totp(secret):
    k = base64.b32decode(secret); h = hmac.new(k, struct.pack(">Q", int(time.time()) // 30), hashlib.sha1).digest(); o = h[-1] & 15
    return "%06d" % ((struct.unpack(">I", h[o:o + 4])[0] & 0x7fffffff) % 1000000)
ok = bad = 0
def check(n, c, x=""):
    global ok, bad
    if c: ok += 1; print("PASS", f"{n} @{W}")
    else: bad += 1; print("FAIL", f"{n} @{W}", str(x)[:400])
errors = []; calls = []
WATCH = """() => { window.__blank = 0; window.__loading = 0; const v = document.getElementById('view');
  new MutationObserver(() => { const m = document.querySelector('#view .adminmain') || v;
    if (!v.firstElementChild) window.__blank++; if (/^\\s*Loading/.test(v.innerText)) window.__loading++; }).observe(v, {childList: true, subtree: true}); }"""
TAG = """() => { const h = document.querySelector('.apphead'), b = document.querySelector('.areabar'), m = document.querySelector('.adminside');
  if (h) h.__keep = 1; if (b) b.__keep = 1; if (m) m.__keep = 1; }"""
SAME = """() => [!!(document.querySelector('.apphead') || {}).__keep, !!(document.querySelector('.areabar') || {}).__keep, !!(document.querySelector('.adminside') || {}).__keep]"""
with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={"width": W, "height": 800}); pg = ctx.new_page()
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("request", lambda r: calls.append(r.url.split("/rest/v1/")[-1].split("?")[0]) if "/rest/v1/" in r.url else None)
    def go(h): pg.goto("about:blank"); pg.goto(SITE + h); pg.wait_for_timeout(1400)
    def nav(h, wait=900): pg.evaluate("(h) => { location.hash = h; }", h); pg.wait_for_timeout(wait)
    go("#/signin"); pg.check("input[name=as][value=seller]"); pg.fill("input[name=email]", "nvadmin@saaz.test"); pg.fill("input[name=password]", "demo1234"); pg.click("form button"); pg.wait_for_timeout(1500)
    go("#/admin/verify"); pg.fill("input[name=password]", "demo1234"); pg.click("#pf button"); pg.wait_for_timeout(1200)
    pg.fill("input[name=code]", totp(SECRET)); pg.click("#cf button"); pg.wait_for_timeout(2000)
    nav("#/admin/cars", 1500)
    pg.evaluate(WATCH); pg.evaluate(TAG)
    if W >= 1024: pg.evaluate("document.querySelector('.adminside').scrollTop = 40")
    calls.clear()
    ROUTES = ["#/admin/garages", "#/admin/users", "#/admin/deals", "#/admin/outbox", "#/admin/audit", "#/admin/vehicles"]
    for r in ROUTES: nav(r)
    same = pg.evaluate(SAME)
    check("header and area bar stay the same elements across Admin pages", same[0] and same[1], same)
    if W >= 1024:
        check("Admin menu stays the same element (not rebuilt)", same[2], same)
        check("Admin menu keeps its scroll", pg.evaluate("document.querySelector('.adminside').scrollTop") >= 30)
        check("the current item moves with the page", pg.evaluate("document.querySelector('.adminside a[aria-current=page]').getAttribute('href')") == "#/admin/vehicles")
    else:
        check("phones: the Go to menu shows the current page", pg.evaluate("document.querySelector('select[data-jump]').value") == "#/admin/vehicles")
    check("the page area is never blank between pages", pg.evaluate("window.__blank") == 0, pg.evaluate("window.__blank"))
    check("no 'Loading' screen between pages", pg.evaluate("window.__loading") == 0, pg.evaluate("window.__loading"))
    check("'who you are' asked once at most for 6 moves", calls.count("rpc/my_roles") <= 1, calls.count("rpc/my_roles"))
    check("scheduler step not repeated on every move", calls.count("rpc/tick") <= 1, calls.count("rpc/tick"))
    check("unread count not asked on every move", calls.count("notifications") <= 1, calls.count("notifications"))
    # fast clicking
    for r in ["#/admin/garages", "#/admin/users", "#/admin/deals", "#/admin/cars", "#/admin/outbox"]: nav(r, 30)
    pg.wait_for_timeout(2500)
    check("fast clicking ends on the last page clicked", "Outbox" in pg.inner_text(".adminmain h2") and pg.evaluate("location.hash") == "#/admin/outbox", pg.inner_text(".adminmain")[:120])
    if W >= 1024: check("fast clicking: the current item is the last one", pg.evaluate("document.querySelector('.adminside a[aria-current=page]').getAttribute('href')") == "#/admin/outbox")
    # slow network
    cdp = ctx.new_cdp_session(pg); cdp.send("Network.enable")
    cdp.send("Network.emulateNetworkConditions", {"offline": False, "latency": 1500, "downloadThroughput": 50000, "uploadThroughput": 20000})   # a slow mobile line
    nav("#/admin/cars", 50)
    pg.wait_for_timeout(400)
    st = pg.evaluate("() => { const v = document.getElementById('view'); return {busy: v.classList.contains('is-busy'), inert: v.inert, txt: v.innerText.slice(0, 400), blank: !v.firstElementChild}; }")
    check("slow network: the old page stays on screen, dimmed", st["busy"] and not st["blank"], st)
    check("slow network: the old page can't be clicked while waiting", st["inert"] is True, st)
    pg.wait_for_timeout(6000)
    st2 = pg.evaluate("() => { const v = document.getElementById('view'); return {busy: v.classList.contains('is-busy'), inert: v.inert}; }")
    check("slow network: the new page arrives and works", not st2["busy"] and not st2["inert"] and pg.locator(".adminmain .car").count() > 0, st2)
    # return visit: last view shown at once while it refreshes
    nav("#/admin/garages", 6000)
    nav("#/admin/cars", 400)
    rv = pg.evaluate("() => ({cards: document.querySelectorAll('.adminmain .car').length, busy: document.getElementById('view').classList.contains('is-busy')})")
    check("return visit: the last view shows at once while fresh data loads", rv["cards"] > 0 and rv["busy"], rv)
    pg.wait_for_timeout(6000)
    check("return visit: then the fresh page, working", not pg.evaluate("document.getElementById('view').inert") and pg.locator(".adminmain .car").count() > 0)
    cdp.send("Network.emulateNetworkConditions", {"offline": False, "latency": 0, "downloadThroughput": -1, "uploadThroughput": -1})
    # Reports
    nav("#/admin/reports/inventory", 1500); pg.evaluate(TAG); pg.evaluate("window.__blank = 0; window.__loading = 0")
    nav("#/admin/reports/funnel", 1500); nav("#/admin/reports/inventory", 1500)
    check("Reports: header and report menu stay while switching reports", all(pg.evaluate(SAME)[i] for i in ((0, 2) if W >= 1024 else (0,))), pg.evaluate(SAME))
    check("Reports: never blank, no Loading screen", pg.evaluate("window.__blank") == 0 and pg.evaluate("window.__loading") == 0)
    # Marketplace: header changes (current link), the page area is kept, not blanked
    nav("#/browse", 1500); pg.evaluate("window.__blank = 0; window.__loading = 0")
    nav("#/selling", 1500); nav("#/verify", 1200); nav("#/browse", 1500)
    check("marketplace: the page area is never blank or 'Loading' between pages", pg.evaluate("window.__blank") == 0 and pg.evaluate("window.__loading") == 0)
    check("marketplace: the current header link follows the page", pg.evaluate("document.querySelector('.appnav a[aria-current=page]').getAttribute('href')") == "#/browse")
    check("changing page scrolls to the top at once", pg.evaluate("scrollY") == 0)
    # reduced motion
    rm = br.new_context(viewport={"width": W, "height": 800}, reduced_motion="reduce"); q = rm.new_page()
    q.goto(SITE + "#/browse"); q.wait_for_timeout(1200)
    check("reduced motion: no page animation", q.evaluate("() => { const s = document.createElement('div'); s.className = 'adminmain viewin'; document.body.appendChild(s); return getComputedStyle(s).animationName; }") == "none")
    check("no script errors", not errors, errors[:3])
    br.close()
print(f"\n{ok} passed, {bad} failed")
sys.exit(1 if bad else 0)
