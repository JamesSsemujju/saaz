"""Browser test for the open marketplace (part 26, 6 Nov 2026) on the local stack.
Usage: python3 tests/browser_open_market_test.py <site url> <width>   (fresh database; it adds its own people and cars)
Covers: with the switch off, Buy cars and the sell form are as before; on: the heading says what is listed, every card says
Inspected, Not inspected or Inspection expired, "Inspected only" filters, a Not inspected car page offers both paths
(offer as it is, ask for a Saaz inspection), asking works and the page then says an inspection is on its way, a failed
report stays on the car with its history, the sell form offers "List now, not inspected", Admin approves a car with
no inspection. No sideways scroll, no script errors. SHOTS=<dir> saves screenshots."""
import sys, os, json, time, base64, hashlib, hmac, struct, psycopg2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import admin_session
from playwright.sync_api import sync_playwright
SITE, W = sys.argv[1], int(sys.argv[2])
db = psycopg2.connect(host="/var/tmp/saazpg", port=5433, user="postgres", dbname="sb"); db.autocommit = True; cur = db.cursor()
def sql(q, a=()): cur.execute("reset role; select set_config('request.jwt.claims','',false)"); cur.execute(q, a or None); return cur.fetchall() if cur.description else None
def as_(uid, q, a=()):
    cur.execute("reset role; select set_config('request.jwt.claims',%s,false)", (admin_session.claims(cur, uid),)); cur.execute("set role authenticated")
    try: cur.execute(q, a or None); return cur.fetchall() if cur.description else None
    finally: cur.execute("reset role")
def user(e, n):
    return sql("insert into auth.users (email, raw_user_meta_data, email_confirmed_at) values (%s,%s,now()) returning id", (e, json.dumps({"name": n, "country": "UG"})))[0][0]
A = user("oadmin@saaz.test", "Ann Admin"); sql("insert into admins (user_id, name, role) values (%s,'Ann Admin','admin')", (A,))
S = user("oseller@x.test", "Sam Seller"); B = user("obuyer@x.test", "Bea Buyer"); O = user("oowner@g.test", "Olga Owner")
SECRET = "JBSWY3DPEHPK3PXP"
admin_session.claims(cur, A); cur.execute("reset role"); sql("update auth.mfa_factors set secret=%s", (SECRET,))
g = as_(O, "select apply_garage(%s)", (json.dumps({"name": "Ntinda Motors", "business_type": "garage", "country": "UG", "region": "Kampala", "address": "Plot 1",
        "phone": "+256 700 111222", "registration_no": "r", "honest_declaration": True}),))[0][0]
as_(A, "select admin_decide_garage(%s,'approve')", (g,))
KEYS = ['engine','gearbox','brakes','steering','tyres','electrics','body','chassis','interior','test_drive','odometer','vin']
def car(i, plate, model):
    return {"vin": "JTMPEN3FJ1K%06d" % i, "make": "Toyota", "model": model, "year": 2015, "fuel": "Petrol", "gearbox": "Automatic", "body": "SUV", "colour": "White",
            "engine": "2.0", "mileage": 84000, "plate": plate, "country": "UG", "region": "Kampala", "price": 95000000 + i * 1000000,
            "description": "Clean car, one owner in Uganda, full service history.", "photos": ["a.webp", "b.webp", "c.webp", "d.webp"], "logbook_name_matches": True}
def inspect(l, fail=False):
    c = sql("select id from conversations where listing_id=%s and status='in_play'", (l,))[0][0]
    as_(O, "select send_message(%s,'Hello, we can inspect Tuesday')", (c,)); as_(S, "select seller_respond(%s,true)", (c,))
    r = as_(O, "select start_review(%s)", (l,))[0][0]; checks = {k: "pass" for k in KEYS}
    if fail: checks["brakes"] = "fail"
    as_(O, "select save_review(%s,%s)", (r, json.dumps({"checks": checks, "odometer": 84500, "in_person": True, "notes": "Brake pads worn through." if fail else ""})))
    as_(O, "select issue_review(%s)", (r,))
def ref(l): return sql("select ref from listings where id=%s", (l,))[0][0]
# An inspected car (the usual path), switch off
L1 = as_(S, "select save_listing(%s)", (json.dumps(car(1, "UBA 101A", "Harrier")),))[0][0]
as_(S, "select submit_listing(%s)", (L1,)); inspect(L1); as_(A, "select admin_decide_listing(%s,'approve')", (L1,))

def totp(secret):
    k = base64.b32decode(secret); h = hmac.new(k, struct.pack(">Q", int(time.time()) // 30), hashlib.sha1).digest(); o = h[-1] & 15
    return "%06d" % ((struct.unpack(">I", h[o:o + 4])[0] & 0x7fffffff) % 1000000)
ok = bad = 0
def check(n, c, x=""):
    global ok, bad
    if c: ok += 1; print("PASS", f"{n} @{W}")
    else: bad += 1; print("FAIL", f"{n} @{W}", str(x)[:400])
errors = []; SHOTS = os.environ.get("SHOTS"); tag = "Desktop" if W >= 1024 else "Phone"
with sync_playwright() as p:
    br = p.chromium.launch()
    def page():
        ctx = br.new_context(viewport={"width": W, "height": 900}); pg = ctx.new_page(); pg.on("pageerror", lambda e: errors.append(str(e))); return pg
    def shot(pg, name):
        if SHOTS: pg.screenshot(path=os.path.join(SHOTS, f"Saaz_OpenMarket_{name}_{tag}_2026-11-06.png"), full_page=False)
    def go(pg, h): pg.goto("about:blank"); pg.goto(SITE + h); pg.wait_for_timeout(1300)
    def signin(pg, email, as_="buyer"):
        go(pg, "#/signin"); pg.check(f"input[name=as][value={as_}]"); pg.fill("input[name=email]", email); pg.fill("input[name=password]", "demo1234"); pg.click("form button"); pg.wait_for_timeout(1500)
    def elevate(pg):
        go(pg, "#/admin/verify"); pg.fill("input[name=password]", "demo1234"); pg.click("#pf button"); pg.wait_for_timeout(1200)
        pg.fill("input[name=code]", totp(SECRET)); pg.click("#cf button"); pg.wait_for_timeout(1800)
    def no_sideways(pg): return pg.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1")

    # 1. Switch off: as before
    v = page(); go(v, "#/browse")
    check("off: heading as before", v.inner_text(".sechead h1") == "Saaz certified cars")
    check("off: no Inspected only filter", v.locator("#flt input[name=insp]").count() == 0)
    s = page(); signin(s, "oseller@x.test", "seller"); go(s, "#/sell/new"); s.wait_for_timeout(800)
    check("off: the sell form has no List now button", s.locator("button[value=list]").count() == 0)

    # 2. Switch on: a seller lists now, Admin approves it
    sql("update settings set value='true'::jsonb where key='open_market'")
    L2 = as_(S, "select save_listing(%s)", (json.dumps(car(2, "UBA 102A", "Premio")),))[0][0]
    s2 = page(); signin(s2, "oseller@x.test", "seller"); go(s2, "#/my/edit/" + L2); s2.wait_for_timeout(1000)
    check("on: the sell form offers List now, not inspected", s2.locator("button[value=list]").count() == 1 and "marked Not inspected" in s2.inner_text("#f"))
    s2.click("button[value=list]"); s2.wait_for_timeout(2500)
    check("List now sends the car to Saaz approval, no garage line", sql("select status from listings where id=%s", (L2,))[0][0] == "awaiting_approval"
          and sql("select count(*) from conversations where listing_id=%s", (L2,))[0][0] == 0)
    check("the seller's page says it goes on sale Not inspected", "marked Not inspected" in s2.inner_text("#view"), s2.inner_text("#view")[:300])
    a = page(); signin(a, "oadmin@saaz.test", "buyer"); elevate(a); go(a, "#/admin/car/" + L2); a.wait_for_timeout(1000)
    btn = a.locator("#dec button[value=approve]")
    check("Admin: approve button says Not inspected", btn.count() == 1 and "Not inspected" in btn.inner_text() and btn.is_enabled())
    btn.click(); a.wait_for_timeout(2000)
    check("approved: live", sql("select status from listings where id=%s", (L2,))[0][0] == "live")
    # A third car: the seller's own inspection fails, Saaz approves it anyway (shown, with the report)
    L3 = as_(S, "select save_listing(%s)", (json.dumps(car(3, "UBA 103A", "Wish")),))[0][0]
    as_(S, "select submit_listing(%s)", (L3,)); inspect(L3, fail=True)
    go(a, "#/admin/car/" + L3); a.wait_for_timeout(1000)
    check("Admin: a failed report can be approved, with a note", a.locator("#dec button[value=approve]").is_enabled() and "failed safety" in a.inner_text("#view"))
    a.click("#dec button[value=approve]"); a.wait_for_timeout(2000)
    # The first car's inspection expires (it stays on sale)
    sql("update reviews set valid_until = current_date - 1 where id = (select current_review_id from listings where id=%s)", (L1,))

    # 3. Buy cars
    v = page(); go(v, "#/browse"); v.wait_for_timeout(500)
    check("on: the heading says what is listed", v.inner_text(".sechead h1") == "Cars on Saaz" and "buy it as it is" in v.inner_text(".sechead p"))
    cards = {c.get_attribute("data-ref-key"): c.locator(".car-insp").inner_text().lower() for c in v.locator("[data-ref=results-grid] .car").all()}
    check("cards: Not inspected, Fail, Inspection expired", "not inspected" in cards.get(ref(L2), "") and "fail" in cards.get(ref(L3), "") and "inspection expired" in cards.get(ref(L1), ""), cards)
    shot(v, "BuyCars")
    v.check("#flt input[name=insp]"); v.click("#flt .go"); v.wait_for_timeout(1200)
    keys = [c.get_attribute("data-ref-key") for c in v.locator("[data-ref=results-grid] .car").all()]
    check("Inspected only shows only cars with a valid inspection", keys == [ref(L3)], keys)
    check("Inspected only: heading back to Saaz certified cars", v.inner_text(".sechead h1") == "Saaz certified cars")
    go(v, "#/"); check("home: Latest cars, honest lede", "Latest cars" in v.inner_text("[data-ref=latest-cars]") and "Each car shows whether" in v.inner_text("[data-ref=home-hero]"))

    # 4. A Not inspected car page: both paths
    go(v, "#/car/" + ref(L2))
    check("visitor: Not inspected card", "not inspected" in v.inner_text("[data-ref=inspection-card]").lower())
    check("visitor: sign in to ask for an inspection", v.locator("a:has-text('Sign in to ask for a Saaz inspection')").count() == 1)
    b = page(); signin(b, "obuyer@x.test"); go(b, "#/car/" + ref(L2)); b.wait_for_timeout(600)
    check("buyer: can make an offer on it as it is", b.locator("#offer").count() == 1)
    check("buyer: can ask for a Saaz inspection, paid to the garage", b.locator("#askinsp").count() == 1 and "pay the garage directly" in b.inner_text("[data-ref=ask-inspection]"))
    shot(b, "NotInspectedCar")
    b.click("#askinsp"); b.wait_for_timeout(2500)
    check("asking makes a buyer inspection and puts a garage in play", sql("select count(*) from reviews where listing_id=%s and requested_by=%s", (L2, B))[0][0] == 1
          and sql("select count(*) from conversations where listing_id=%s and status='in_play'", (L2,))[0][0] == 1)
    check("the page then says an inspection is on its way", b.locator("[data-ref=inspection-booked]").count() == 1 and b.locator("#askinsp").count() == 0)
    go(v, "#/browse"); check("its card: inspection booked", "inspection booked" in v.locator(f"[data-ref-key='{ref(L2)}'] .car-insp").inner_text().lower())

    # 5. The failed car: report and history on its page
    go(v, "#/car/" + ref(L3))
    check("failed car: Fail on the inspection card, still on sale", "fail" in v.inner_text("[data-ref=inspection-card]").lower() and "Sign in to make an offer" in v.inner_text("[data-ref=price-panel]"))
    h = v.inner_text("[data-ref=inspection-history]") if v.locator("[data-ref=inspection-history]").count() else ""
    check("failed car: history lists the Fail with its report", "fail" in h.lower() and "Report" in h and "pass or fail" in h, h)
    go(v, "#/car/" + ref(L1))
    check("expired car: Expired on its card, and an inspection can be asked for", "expired" in v.inner_text("[data-ref=inspection-card]").lower() and v.locator("a:has-text('Sign in to ask for a Saaz inspection')").count() == 1)
    shot(v, "FailedHistory")
    for pg in (v, b, a): check("no sideways scroll", no_sideways(pg))
    check("no script errors", not errors, errors[:3])
    br.close()
print(f"\n{ok} passed, {bad} failed")
