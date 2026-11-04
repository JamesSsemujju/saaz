"""Browser test for BA-0013, Custom audience on Admin, Announcements (part 25), on the local stack (4 Nov 2026).
Usage: python3 tests/browser_custom_audience_test.py <site url> <width>   (fresh database; adds its own people and cars)
Covers: Custom shows the filter panel; filters plus a person found by name and added; removing and re-adding a person;
the check shows the count and sample names; changing a filter makes you check again; sending reaches exactly that audience;
the Sent list says how it was chosen; the other audiences still work; no sideways scroll; no script errors."""
import sys, os, json, time, base64, hashlib, hmac, struct, psycopg2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import admin_session
from playwright.sync_api import sync_playwright
SITE, W = sys.argv[1], int(sys.argv[2])
db = psycopg2.connect(host="/var/tmp/saazpg", port=5433, user="postgres", dbname="sb"); db.autocommit = True; cur = db.cursor()
def sql(q, a=()): cur.execute(q, a or None); return cur.fetchall() if cur.description else None
def user(e, n, mobile=None, verified=False):
    u = sql("insert into auth.users (email, raw_user_meta_data, email_confirmed_at) values (%s,%s,now()) returning id", (e, json.dumps({"name": n, "country": "UG"})))[0][0]
    sql("update profiles set mobile=%s, phone_verified=%s where id=%s", (mobile, verified, u)); return u
A = user("cadmin@saaz.test", "Ann Admin"); sql("insert into admins (user_id, name, role) values (%s,'Ann Admin','admin')", (A,))
S1 = user("cs1@x.test", "Sam Harrier Seller", "+256772200001", True)
S2 = user("cs2@x.test", "Sue Premio Seller", "+256772200002", True)
B2 = user("cb2@x.test", "Bea Picked", "+256772200003", True)
for i, (s, mk, md) in enumerate([(S1, "Toyota", "Harrier"), (S2, "Toyota", "Premio")]):
    v = sql("insert into vehicles (vin, make, model) values (%s,%s,%s) returning id", ("JTBRCA%011d" % i, mk, md))[0][0]
    sql("""insert into listings (vehicle_id, seller_id, country, region, status, make, model, year, fuel, gearbox, body, colour, engine, mileage, plate, currency, price,
           description, photos, logbook_name_matches, owner_authorised) values (%s,%s,'UG','Kampala','live',%s,%s,2015,'Petrol','Automatic','SUV','White','2.0',80000,%s,'UGX',50000000,'Clean car',%s,true,true)""",
        (v, s, mk, md, "UBD %03dD" % i, ["a.webp"]))
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
errors = []; SHOTS = os.environ.get("SHOTS")
with sync_playwright() as p:
    br = p.chromium.launch(); ctx = br.new_context(viewport={"width": W, "height": 900}); ad = ctx.new_page(); ad.on("pageerror", lambda e: errors.append(str(e)))
    def go(h): ad.goto("about:blank"); ad.goto(SITE + h); ad.wait_for_timeout(1300)
    go("#/signin"); ad.check("input[name=as][value=seller]"); ad.fill("input[name=email]", "cadmin@saaz.test"); ad.fill("input[name=password]", "demo1234"); ad.click("form button"); ad.wait_for_timeout(1500)
    go("#/admin/verify"); ad.fill("input[name=password]", "demo1234"); ad.click("#pf button"); ad.wait_for_timeout(1200)
    ad.fill("input[name=code]", totp(SECRET)); ad.click("#cf button"); ad.wait_for_timeout(1800)
    go("#/admin/announce")
    check("custom panel hidden at first", ad.locator("#ancustom").is_hidden())
    ad.select_option("#anf select[name=audience]", "custom")
    check("choosing Custom shows the filter panel", ad.locator("#ancustom").is_visible())
    ad.check("#anf input[name=r_sellers]"); ad.fill("#anf input[name=models]", "harrier")
    ad.fill("#anpq", "bea"); ad.click("#anpfind"); ad.wait_for_timeout(900)
    check("search finds the person", "Bea Picked" in ad.inner_text("#anpres"))
    ad.click("#anpres [data-pick]"); ad.wait_for_timeout(300)
    check("added person shows as a chip", "bea picked" in ad.inner_text("#anpicked").lower())
    ad.click("[data-unpick]"); ad.wait_for_timeout(200)
    check("the chip can be removed", "Nobody added" in ad.inner_text("#anpicked"))
    ad.fill("#anpq", "bea"); ad.click("#anpfind"); ad.wait_for_timeout(900); ad.click("#anpres [data-pick]"); ad.wait_for_timeout(300)
    ad.fill("#anf textarea[name=body]", "New inspected Harriers this week on Saaz.")
    ad.click("#anprev"); ad.wait_for_timeout(1300)
    r = ad.inner_text("#anres")
    check("check counts the custom audience (Harrier seller + Bea)", r.strip().startswith("2 people get it"), repr(r))
    check("check shows sample names", "Sam Harrier Seller" in r and "Bea Picked" in r and "Sue" not in r, r)
    if SHOTS: ad.screenshot(path=os.path.join(SHOTS, "Saaz_BuildQueue_BA-0013_%s_2026-11-04.png" % ("Desktop" if W >= 1024 else "Phone")), full_page=True)
    check("Send is on after the check", ad.is_enabled("#ansend"))
    ad.fill("#anf input[name=models]", "harrier, premio")
    ad.locator("#anf input[name=models]").dispatch_event("change"); ad.wait_for_timeout(200)
    check("changing a filter turns Send off until checked again", ad.is_disabled("#ansend"))
    ad.fill("#anf input[name=models]", "harrier"); ad.locator("#anf input[name=models]").dispatch_event("change")
    ad.click("#anprev"); ad.wait_for_timeout(1300)
    ad.click("#ansend"); ad.wait_for_timeout(200); ad.click("#ansend"); ad.wait_for_timeout(1800)
    got = {x[0] for x in sql("select user_id from notifications where kind='announcement' and body='New inspected Harriers this week on Saaz.'")}
    check("sent to exactly the custom audience", got == {S1, B2}, got)
    t = ad.inner_text(".adminmain section:last-of-type")
    check("Sent list says how the audience was chosen", "Custom" in t and "harrier" in t.lower() and "1 named" in t, t[:300])
    check("no sideways scroll", ad.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1"))
    ad.select_option("#anf select[name=audience]", "sellers"); ad.fill("#anf textarea[name=body]", "A message to every seller on Saaz."); ad.click("#anprev"); ad.wait_for_timeout(1300)
    check("other audiences still work", "2 people get it" in ad.inner_text("#anres"), ad.inner_text("#anres"))
    check("no script errors", not errors, errors[:3])
    br.close()
print(f"\n{ok} passed, {bad} failed")
sys.exit(1 if bad else 0)
