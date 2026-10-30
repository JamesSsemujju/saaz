"""Browser test for BA-0001, BA-0003/BA-0005 and BA-0004 on the local stack (19 Oct 2026).
Usage: python3 tests/browser_admin_preview_test.py <site url> <width>   (fresh database; it adds its own people and cars)
Covers: buyers still see only live cars; viewing the marketplace as admin shows every car at any stage on the same card,
with the stage on the photo, a clear admin line, cards opening the admin page, and no status changed; the home page the same;
the card hover (photo lifts and zooms, text unchanged, still with reduced motion); the "List it as a Saaz car" pointer on the
sell form for admins only, which leads to the Saaz form without the logbook question."""
import sys, os, json, time, datetime, base64, hashlib, hmac, struct, psycopg2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import admin_session
from playwright.sync_api import sync_playwright
SITE, W = sys.argv[1], int(sys.argv[2])
db = psycopg2.connect(host="/var/tmp/saazpg", port=5433, user="postgres", dbname="sb"); db.autocommit = True; cur = db.cursor()
def sql(q, a=()): cur.execute(q, a or None); return cur.fetchall() if cur.description else None
def user(e, n): return sql("insert into auth.users (email, raw_user_meta_data) values (%s,%s) returning id", (e, json.dumps({"name": n, "country": "UG"})))[0][0]
A = user("admin@saaz.test", "Ann Admin"); sql("insert into admins (user_id, name, role) values (%s,'Ann Admin','admin')", (A,))
SEL = user("seller@x.test", "Sam Seller")
SECRET = "JBSWY3DPEHPK3PXP"
admin_session.claims(cur, A); cur.execute("reset role"); sql("update auth.mfa_factors set secret=%s", (SECRET,))
# one live car, one waiting for approval, one rejected: like the live site, where nothing is public yet but cars exist
CARS = [("Toyota", "Premio", 30000000, "live"), ("Subaru", "Forester", 60000000, "awaiting_approval"), ("Honda", "Fit", 25000000, "rejected")]
for i, (mk, md, pr, st) in enumerate(CARS):
    vid = sql("insert into vehicles (vin, make, model) values (%s,%s,%s) returning id", ("JTPREV%011d" % i, mk, md))[0][0]
    sql("""insert into listings (vehicle_id, seller_id, country, region, status, make, model, year, fuel, gearbox, body, colour, engine, mileage, plate, currency, price,
           description, photos, logbook_name_matches, owner_authorised, live_at) values (%s,%s,'UG','Kampala',%s,%s,%s,2015,'Petrol','Automatic','Sedan','White','1.5',80000,%s,'UGX',%s,'Clean car',%s,true,true,%s)""",
        (vid, SEL, st, mk, md, "UBP %03dP" % i, pr, ["a.webp"], datetime.datetime.now(datetime.timezone.utc) if st == "live" else None))
before = sql("select id, status from listings order by id")
def totp(secret):
    k = base64.b32decode(secret); h = hmac.new(k, struct.pack(">Q", int(time.time()) // 30), hashlib.sha1).digest(); o = h[-1] & 15
    return "%06d" % ((struct.unpack(">I", h[o:o + 4])[0] & 0x7fffffff) % 1000000)
ok = bad = 0
def check(n, c, x=""):
    global ok, bad
    if c: ok += 1; print("PASS", f"{n} @{W}")
    else: bad += 1; print("FAIL", f"{n} @{W}", str(x)[:400])
errors = []
with sync_playwright() as p:
    br = p.chromium.launch()
    def page(motion="no-preference"):
        ctx = br.new_context(viewport={"width": W, "height": 800 if W >= 768 else 760}, reduced_motion=motion)
        pg = ctx.new_page(); pg.on("pageerror", lambda e: errors.append(str(e))); return pg
    def shot(pg, name):
        if os.environ.get("SHOTS"): pg.screenshot(path=os.path.join(os.environ["SHOTS"], f"Preview_{name}_{W}.png"))
    def go(pg, h): pg.goto("about:blank"); pg.goto(SITE + h); pg.wait_for_timeout(1300)
    def signin(pg, email):
        go(pg, "#/signin"); pg.check("input[name=as][value=seller]"); pg.fill("input[name=email]", email); pg.fill("input[name=password]", "demo1234"); pg.click("form button"); pg.wait_for_timeout(1500)
    def elevate(pg):
        go(pg, "#/admin/verify"); pg.fill("input[name=password]", "demo1234"); pg.click("#pf button"); pg.wait_for_timeout(1200)
        pg.fill("input[name=code]", totp(SECRET)); pg.click("#cf button"); pg.wait_for_timeout(1800)
    def names(pg): return sorted(pg.locator(".car .car-name").all_inner_texts())

    # ---------- buyers: unchanged ----------
    pub = page(); go(pub, "#/browse")
    check("buyers still see only live cars", pub.locator(".car").count() == 1 and "Premio" in names(pub)[0], names(pub))
    check("buyers don't see the admin line", pub.locator(".admin-preview").count() == 0)

    # ---------- BA-0001: hover ----------
    if W >= 1024:
        c = pub.locator(".car").first; c.hover(); pub.wait_for_timeout(450)
        tr = pub.evaluate("() => [getComputedStyle(document.querySelector('.car .car-photo')).transform, getComputedStyle(document.querySelector('.car .car-photo img')).transform]")
        check("hover: the photo comes forward and zooms slightly", tr[0] != "none" and tr[1] != "none", tr)
        check("hover: name, year and price stay as they are", pub.locator(".car .car-price").first.is_visible() and pub.locator(".car .car-name").first.is_visible())
        shot(pub, "1-hover")
        still = page("reduce"); go(still, "#/browse"); still.locator(".car").first.hover(); still.wait_for_timeout(450)
        check("hover with reduced motion: nothing moves", still.evaluate("() => getComputedStyle(document.querySelector('.car .car-photo')).transform") == "none")
    else:
        check("phones: cards look as before (no hover state stuck on)", pub.evaluate("() => getComputedStyle(document.querySelector('.car .car-photo')).transform") == "none")

    # ---------- 29 Oct 2026: the approved photo hero replaces the BA-0006 video ----------
    home = page(); go(home, "#/"); home.wait_for_timeout(1200)
    info = home.evaluate("""() => { const h = document.querySelector('[data-ref=home-hero]'), img = h && h.querySelector('.hero-bg img');
      return { photo: !!img && img.complete && img.naturalWidth > 0, src: img && img.currentSrc, video: document.querySelectorAll('video').length,
               hidden: h.querySelector('.hero-bg').getAttribute('aria-hidden'), h1: getComputedStyle(h.querySelector('h1')).color,
               trustOutside: !h.querySelector('[data-ref=trust-section]'), latestOutside: !h.querySelector('[data-ref=latest-cars]') }; }""")
    check("home: Saaz's own car photo behind the headline, no video", info["photo"] and "home-hero" in (info["src"] or "") and info["video"] == 0, info)
    check("home: the photo is decoration for screen readers", info["hidden"] == "true", info)
    check("home: latest cars and the trust section sit outside the hero", info["trustOutside"] and info["latestOutside"], info)
    pt = home.evaluate("() => { const r = document.querySelector('[data-ref=home-hero] h1').getBoundingClientRect(); const e = document.elementFromPoint(r.left + 10, r.top + r.height / 2); return e && e.tagName.toLowerCase(); }")
    check("home: the headline sits in front of the photo", pt in ("h1", "i"), pt)
    check("home: the search works in front of the photo", home.locator("#hs select[name=make]").is_enabled())
    shot(home, "4-home-photo")

    # ---------- BA-0003 / BA-0005: viewing the marketplace as admin ----------
    adm = page(); signin(adm, "admin@saaz.test"); elevate(adm); go(adm, "#/browse")
    check("as admin: every car at any stage, the same 3 as Admin, Cars", adm.locator(".car").count() == 3, names(adm))
    check("as admin: the same buyer card design", adm.locator(".car .car-photo").count() == 3 and adm.locator(".car .car-price").count() == 3)
    tags = adm.locator(".car .car-tag.right").all_inner_texts()
    check("as admin: the stage shows on the photo of cars that aren't live", sorted(t.strip().lower() for t in tags) == ["awaiting approval", "rejected"], tags)  # small capitals since 29 Oct 2026
    check("as admin: no Saved only filter (saving is off in the admin view)", adm.locator("input[name=saved]").count() == 0)
    check("as admin: a clear line says this is the admin view", adm.locator(".admin-preview").is_visible() and "Nothing here approves or publishes" in adm.inner_text(".admin-preview"))
    check("as admin: the area bar shows Back to Admin", adm.locator(".areabar a", has_text="Back to Admin").count() >= 1 or adm.locator("a", has_text="Back to Admin").count() >= 1)
    shot(adm, "2-admin-marketplace")
    adm.locator(".car", has_text="Forester").click(); adm.wait_for_timeout(1500)
    check("as admin: clicking a car opens its admin page, not the buyer flow", "#/admin/car/" in adm.url, adm.url)
    go(adm, "#/")
    check("as admin: the home page shows every car too", adm.locator(".car").count() == 3)
    check("viewing as admin changed no car's status", sql("select id, status from listings order by id") == before)
    go(adm, "#/browse"); adm.locator("a", has_text="Back to Admin").first.click(); adm.wait_for_timeout(1500)
    check("Back to Admin returns to the admin area", "#/admin" in adm.url, adm.url)

    # ---------- BA-0004: Saaz cars don't need the logbook ----------
    go(adm, "#/sell/new")
    check("admin on the sell form: told to list Saaz's own cars as Saaz cars", adm.locator("[data-ref=saaz-car-hint]").is_visible())
    shot(adm, "3-sell-form-saaz-pointer")
    adm.locator("[data-ref=saaz-car-hint] a").click(); adm.wait_for_timeout(1500)
    check("the link opens the Saaz car form", "saaz=1" in adm.url, adm.url)
    sel = page(); signin(sel, "seller@x.test"); go(sel, "#/sell/new")
    check("sellers don't see the Saaz pointer", sel.locator("[data-ref=saaz-car-hint]").count() == 0)
    check("no script errors", not errors, errors[:3])
    br.close()
print(f"\n{ok} passed, {bad} failed")
