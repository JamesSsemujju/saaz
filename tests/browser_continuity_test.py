"""Browser test for the continuity work of 5 Nov 2026 (from the Mercedes-Benz navigation study).
Usage: python3 tests/browser_continuity_test.py <site url>   (fresh database; adds a seller with 30 live cars and an admin)
Covers: the header is in the page before any script runs and the footer starts below the screen; layout shift under 0.1 on
home, the car list and a car page, on desktop and on a phone at Slow 4G; visitors download no selling, garage or admin code,
which loads when first needed; Back returns to the same place in the list at once, Forward too, and a refresh after an action
doesn't jump; photos hide until loaded, then fade in over a reserved frame; resting on or touching a car starts loading it,
and the tap then needs no new request; links answer a press at once; reduced motion turns the fade off; no script errors."""
import sys, os, json, time, datetime, base64, hashlib, hmac, struct, psycopg2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import admin_session
from playwright.sync_api import sync_playwright
SITE = sys.argv[1]
db = psycopg2.connect(host="/var/tmp/saazpg", port=5433, user="postgres", dbname="sb"); db.autocommit = True; cur = db.cursor()
def sql(q, a=()): cur.execute(q, a or None); return cur.fetchall() if cur.description else None
def user(e, n): return sql("insert into auth.users (email, raw_user_meta_data, email_confirmed_at) values (%s,%s,now()) returning id", (e, json.dumps({"name": n, "country": "UG"})))[0][0]
A = user("ctadmin@saaz.test", "Ann Admin"); sql("insert into admins (user_id, name, role) values (%s,'Ann Admin','admin')", (A,))
SEL = user("ctseller@x.test", "Sam Seller")
for i in range(30):
    v = sql("insert into vehicles (vin, make, model) values (%s,'Toyota','Premio') returning id", ("JTCONT%011d" % i,))[0][0]
    sql("""insert into listings (vehicle_id, seller_id, country, region, status, make, model, year, fuel, gearbox, body, colour, engine, mileage, plate, currency, price,
           description, photos, logbook_name_matches, owner_authorised, live_at) values (%s,%s,'UG','Kampala','live','Toyota','Premio',2012,'Petrol','Automatic','Sedan','White','1.5',90000,%s,'UGX',%s,'Clean car',%s,true,true,%s)""",
        (v, SEL, "UBT %03dT" % i, 20000000 + i * 100000, ["a.webp"], datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=i)))
REF = sql("select ref from listings where status='live' order by live_at desc limit 1")[0][0]
SECRET = "JBSWY3DPEHPK3PXP"
admin_session.claims(cur, A); cur.execute("reset role"); sql("update auth.mfa_factors set secret=%s", (SECRET,))
def totp(secret):
    k = base64.b32decode(secret); h = hmac.new(k, struct.pack(">Q", int(time.time()) // 30), hashlib.sha1).digest(); o = h[-1] & 15
    return "%06d" % ((struct.unpack(">I", h[o:o + 4])[0] & 0x7fffffff) % 1000000)
ok = bad = 0
def check(n, c, x=""):
    global ok, bad
    if c: ok += 1; print("PASS", n)
    else: bad += 1; print("FAIL", n, str(x)[:400])
errors = []
CLS = """() => { window.__cls = 0; new PerformanceObserver(l => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__cls += e.value; }).observe({type: 'layout-shift', buffered: true}); }"""
def slow(ctx, pg):
    c = ctx.new_cdp_session(pg); c.send("Network.enable"); c.send("Network.setCacheDisabled", {"cacheDisabled": True})
    c.send("Network.emulateNetworkConditions", {"offline": False, "latency": 550, "downloadThroughput": 1350000 / 8, "uploadThroughput": 675000 / 8}); return c
with sync_playwright() as p:
    br = p.chromium.launch()
    # 1. Without scripts: the header is there, the footer starts below the screen
    nj = br.new_context(viewport={"width": 390, "height": 700}, java_script_enabled=False); q = nj.new_page(); q.goto(SITE); q.wait_for_timeout(800)
    check("header is in the page before any script runs", q.locator("header.apphead .appnav a").count() == 4 and q.locator("header.apphead .sellbtn").count() == 1)
    check("the footer starts below the first screen", q.evaluate("() => document.querySelector('.site-footer, footer').getBoundingClientRect().top >= innerHeight - 1"))
    nj.close()
    # 2. Layout shift, desktop and phone Slow 4G
    for label, w, s in (("desktop", 1280, False), ("phone Slow 4G", 390, True)):
        ctx = br.new_context(viewport={"width": w, "height": 800 if w > 500 else 700})
        for name, h in (("home", "#/"), ("car list", "#/browse"), ("car page", "#/car/" + REF)):
            pg = ctx.new_page(); pg.on("pageerror", lambda e: errors.append(str(e)))
            if s: slow(ctx, pg)
            pg.add_init_script("(" + CLS + ")()")
            pg.goto(SITE + h, wait_until="load", timeout=120000); pg.wait_for_timeout(9000 if s else 2500)
            c = pg.evaluate("window.__cls")
            check(f"{label}, {name}: layout shift under 0.1", c < 0.1, round(c, 3))
            if name == "car list":
                scripts = pg.evaluate("() => performance.getEntriesByType('resource').map(e => e.name.split('/').pop().split('?')[0]).filter(n => /^app-/.test(n))")
                check(f"{label}: a visitor loads no selling, garage or admin code", not any(x in scripts for x in ("app-seller.js", "app-garage.js", "app-admin.js", "app-reports.js", "app-notify.js", "app-promotions.js")), scripts)
            pg.close()
        ctx.close()
    # 3. Code loads when needed
    ctx = br.new_context(viewport={"width": 1280, "height": 800}); pg = ctx.new_page(); pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(SITE + "#/sell"); pg.wait_for_timeout(2000)
    check("Sell a car loads the selling code and shows its page", pg.evaluate("() => performance.getEntriesByType('resource').some(e => /app-seller\\.js/.test(e.name))") and pg.locator("#view").inner_text().strip() != "", pg.inner_text("#view")[:100])
    check("…without the admin code", not pg.evaluate("() => performance.getEntriesByType('resource').some(e => /app-admin\\.js/.test(e.name))"))
    ctx.close()
    # 4. Back keeps your place (phone, one card per row, so the list is long)
    ctx = br.new_context(viewport={"width": 390, "height": 700}); pg = ctx.new_page(); pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(SITE + "#/browse"); pg.wait_for_timeout(2000)
    pg.evaluate("window.scrollTo({top: 1800, behavior: 'instant'})"); pg.wait_for_timeout(300)
    y0 = pg.evaluate("scrollY")
    card = pg.locator(".car").nth(5); href = card.get_attribute("href") or card.locator("a").first.get_attribute("href")
    pg.evaluate("(h) => { location.hash = h.replace(/^.*#/, '#'); }", href); pg.wait_for_timeout(1500)
    check("a new page starts at the top", pg.evaluate("scrollY") == 0)
    pg.go_back(); pg.wait_for_timeout(60)
    early = pg.evaluate("() => ({y: scrollY, cards: document.querySelectorAll('#view .car').length})")
    check("Back: the list is there at once, at the same place", early["cards"] > 0 and abs(early["y"] - y0) <= 2, (early, y0))
    pg.wait_for_timeout(1500)
    check("Back: still at the same place once refreshed", abs(pg.evaluate("scrollY") - y0) <= 2, (pg.evaluate("scrollY"), y0))
    pg.go_forward(); pg.wait_for_timeout(1500)
    check("Forward: back on the car page", "#/car/" in pg.evaluate("location.hash"))
    pg.go_back(); pg.wait_for_timeout(1500)
    pg.evaluate("window.scrollTo({top: 600, behavior: 'instant'})"); pg.wait_for_timeout(200)
    pg.evaluate("Saaz.render()"); pg.wait_for_timeout(1500)
    check("a refresh after an action stays put (no jump to an older view)", abs(pg.evaluate("scrollY") - 600) <= 2, pg.evaluate("scrollY"))
    # 5. Photos: hidden until loaded, then shown; the frame keeps its place colour
    st = pg.evaluate("() => { const i = document.querySelector('.car-photo img'); const f = i.closest('.car-photo'); return {loaded: i.classList.contains('is-loaded'), op: getComputedStyle(i).opacity, bg: getComputedStyle(f).backgroundImage}; }")
    check("photos are marked loaded (or failed) and shown", st["loaded"] and st["op"] == "1", st)
    check("the photo frame keeps a placeholder colour", "gradient" in st["bg"], st)
    ctx.close()
    sp = br.new_context(viewport={"width": 1280, "height": 800}); pg = sp.new_page(); slow(sp, pg)
    pg.goto(SITE + "#/browse", timeout=120000); pg.wait_for_selector(".car-photo img", timeout=60000)
    pend = pg.evaluate("() => [...document.querySelectorAll('.car-photo img')].filter(i => !i.classList.contains('is-loaded')).map(i => getComputedStyle(i).opacity)")
    check("slow network: photos still loading stay hidden over their frame (no half-drawn photo)", all(o == "0" for o in pend), pend[:5])
    sp.close()
    # 6. Prefetch on hover or touch; the tap then needs no new request
    ctx = br.new_context(viewport={"width": 1280, "height": 800}); pg = ctx.new_page(); pg.on("pageerror", lambda e: errors.append(str(e)))
    reqs = []; pg.on("request", lambda r: reqs.append(r.url) if "/rest/v1/listings" in r.url else None)
    pg.goto(SITE + "#/browse"); pg.wait_for_timeout(2000)
    c3 = pg.locator(".car").nth(2); h3 = c3.get_attribute("href") or c3.locator("a").first.get_attribute("href"); ref3 = h3.split("/car/")[1]
    reqs.clear(); c3.hover(); pg.wait_for_timeout(400)
    check("resting the mouse on a car starts loading it", any(ref3 in u for u in reqs), reqs)
    n = len(reqs); c3.click(); pg.wait_for_timeout(1200)
    check("the tap then needs no new request for the car", len([u for u in reqs[n:] if ref3 in u]) == 0 and ref3 in pg.evaluate("location.hash"), reqs[n:])
    check("the car page shows", pg.locator("#view h1").count() >= 1)
    # 7. Press state
    pg.goto(SITE + "#/browse"); pg.wait_for_timeout(1500)
    link = pg.locator(".appnav a").first; b = link.bounding_box(); pg.mouse.move(b["x"] + 5, b["y"] + 5); pg.mouse.down(); pg.wait_for_timeout(30)
    op = pg.evaluate("getComputedStyle(document.querySelector('.appnav a')).opacity"); pg.mouse.up()
    check("a link answers the press at once", float(op) < 1, op)
    ctx.close()
    # 8. Admin: its code loads when entering Admin, and Admin still works
    ctx = br.new_context(viewport={"width": 1280, "height": 800}); pg = ctx.new_page(); pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(SITE + "#/signin"); pg.wait_for_timeout(1200); pg.check("input[name=as][value=seller]"); pg.fill("input[name=email]", "ctadmin@saaz.test"); pg.fill("input[name=password]", "demo1234"); pg.click("form button"); pg.wait_for_timeout(1500)
    pg.goto(SITE + "#/admin/verify"); pg.wait_for_timeout(1500); pg.fill("input[name=password]", "demo1234"); pg.click("#pf button"); pg.wait_for_timeout(1200)
    pg.fill("input[name=code]", totp(SECRET)); pg.click("#cf button"); pg.wait_for_timeout(2500)
    check("Admin opens with its code loaded", pg.locator("[data-ref=admin-menu]").count() == 1 and pg.evaluate("() => !!window.Saaz.adminPage"))
    pg.evaluate("location.hash = '#/admin/outbox'"); pg.wait_for_timeout(1500)
    check("Admin pages from later files work (Outbox)", "Outbox" in pg.inner_text(".adminmain h2"))
    pg.evaluate("location.hash = '#/admin/promotions'"); pg.wait_for_timeout(1500)
    check("Admin pages from later files work (Promotions)", "Promotions" in pg.inner_text(".adminmain h2"))
    ctx.close()
    # 9. Reduced motion: no photo fade
    rm = br.new_context(viewport={"width": 1280, "height": 800}, reduced_motion="reduce"); q = rm.new_page(); q.goto(SITE + "#/browse"); q.wait_for_timeout(1500)
    check("reduced motion: photos appear without the fade", q.evaluate("getComputedStyle(document.querySelector('.car-photo img')).animationName") == "none")
    rm.close()
    check("no script errors", not errors, errors[:3])
    br.close()
print(f"\n{ok} passed, {bad} failed")
sys.exit(1 if bad else 0)
