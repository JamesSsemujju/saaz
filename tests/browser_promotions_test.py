"""Browser test for Promotions (part 23) on the local stack (3 Nov 2026).
Usage: python3 tests/browser_promotions_test.py <site url> <width>   (fresh database; it adds its own people)
Covers: /giveaway/ with the switch off; an admin creates a draw, fills it, opens it, adds a tracked link and a code, switches
promotions on; a visitor sees the page and is asked to sign in; a buyer enters from the tracked link (source recorded, profile
details filled in, T&C needed, one entry); markup typed into an entry stays text in Admin; the admin exports CSV (file name with
the date range, logged), closes, draws with a witness, tells the winner (inbox notice); no sideways scroll; no script errors.
SHOTS=<dir> saves screenshots."""
import sys, os, json, time, base64, hashlib, hmac, struct, psycopg2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import admin_session
from playwright.sync_api import sync_playwright
SITE, W = sys.argv[1], int(sys.argv[2])
db = psycopg2.connect(host="/var/tmp/saazpg", port=5433, user="postgres", dbname="sb"); db.autocommit = True; cur = db.cursor()
def sql(q, a=()): cur.execute(q, a or None); return cur.fetchall() if cur.description else None
def user(e, n, mobile=None):
    return sql("insert into auth.users (email, raw_user_meta_data, email_confirmed_at) values (%s,%s,now()) returning id", (e, json.dumps({"name": n, "country": "UG", "mobile": mobile})))[0][0]
A = user("padmin@saaz.test", "Ann Admin"); sql("insert into admins (user_id, name, role) values (%s,'Ann Admin','admin')", (A,))
B = user("pbuyer@x.test", "Bea Buyer", "+256772000111"); B2 = user("pbuyer2@x.test", "Ben Second")
sql("update profiles set mobile='+256772000111' where id=%s", (B,))
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
errors = []
SHOTS = os.environ.get("SHOTS")
with sync_playwright() as p:
    br = p.chromium.launch()
    def page():
        ctx = br.new_context(viewport={"width": W, "height": 900}, accept_downloads=True)
        pg = ctx.new_page(); pg.on("pageerror", lambda e: errors.append(str(e))); return pg
    def shot(pg, name):
        if SHOTS: pg.screenshot(path=os.path.join(SHOTS, name), full_page=True)
    def go(pg, h): pg.goto("about:blank"); pg.goto(SITE + h); pg.wait_for_timeout(1300)
    def signin(pg, email, as_="buyer"):
        go(pg, "#/signin"); pg.check(f"input[name=as][value={as_}]"); pg.fill("input[name=email]", email); pg.fill("input[name=password]", "demo1234"); pg.click("form button"); pg.wait_for_timeout(1500)
    def elevate(pg):
        go(pg, "#/admin/verify"); pg.fill("input[name=password]", "demo1234"); pg.click("#pf button"); pg.wait_for_timeout(1200)
        pg.fill("input[name=code]", totp(SECRET)); pg.click("#cf button"); pg.wait_for_timeout(1800)
    def no_sideways(pg): return pg.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1")

    # 1. Switch off: the short link says nothing is running
    vis = page(); vis.goto(SITE + "giveaway/"); vis.wait_for_timeout(1800)
    check("/giveaway/ opens the current promotion page", "#/promotions/current" in vis.url, vis.url)
    check("switch off: 'No promotion running right now'", "No promotion running" in vis.inner_text("#view"))

    # 2. Admin sets up the draw
    ad = page(); signin(ad, "padmin@saaz.test", "seller"); elevate(ad)
    go(ad, "#/admin/promotions")
    check("Promotions is in the Admin menu", ad.locator(".adminside a[href='#/admin/promotions']").count() == 1 or ad.locator("select[data-jump] option[value='#/admin/promotions']").count() == 1)
    check("the switch shows Off", "off" in ad.inner_text(".pagehead").lower())
    ad.fill("#pnew input[name=title]", "Win a car"); ad.fill("#pnew input[name=slug]", "win-a-car"); ad.click("#pnew button"); ad.wait_for_timeout(1800)
    check("draft created and opened", "/admin/promotion/" in ad.url and "draft" in ad.inner_text(".pagehead").lower(), ad.url)
    ad.fill("#pd input[name=prize]", "A Toyota Premio (placeholder)")
    ad.fill("#pd textarea[name=summary]", "One entry per person. Draw after entries close.")
    ad.fill("#pd input[name=opens_at]", "2026-11-01T09:00"); ad.fill("#pd input[name=closes_at]", "2030-12-31T23:59")
    ad.fill("#pd input[name=permit_no]", "LGRB-TEST-1"); ad.fill("#pd input[name=terms_version]", "v1")
    ad.fill("#pd textarea[name=terms]", "1. Placeholder terms.\n2. One entry per person.")
    ad.click("#pd button"); ad.wait_for_timeout(1500)
    row = sql("select opens_at at time zone 'Africa/Kampala', permit_no from promotions where slug='win-a-car'")[0]
    check("details saved, times read as East Africa Time", str(row[0]).startswith("2026-11-01 09:00") and row[1] == "LGRB-TEST-1", row)
    ad.fill("#plink input[name=channel]", "radio"); ad.fill("#plink input[name=label]", "Radio spot"); ad.click("#plink button"); ad.wait_for_timeout(1300)
    ad.fill("#pcode input[name=code]", "garage1"); ad.fill("#pcode input[name=label]", "Kampala Motors"); ad.click("#pcode button"); ad.wait_for_timeout(1300)
    check("tracked link listed with its address", "?src=radio" in ad.inner_text("body"))
    check("code stored in capitals", sql("select code from promo_codes")[0][0] == "GARAGE1")
    ad.click("#popen"); ad.wait_for_timeout(200); ad.click("#popen"); ad.wait_for_timeout(1500)
    check("opened with two taps", "open" in ad.inner_text(".pagehead").lower() and sql("select status from promotions")[0][0] == "open")
    go(ad, "#/admin/promotions"); ad.click("#psw button"); ad.wait_for_timeout(1500)
    check("switched on", "on" == ad.inner_text(".pagehead .chip").strip().lower())

    # 3. Visitor from the tracked link
    vis.goto(SITE + "giveaway/?src=radio"); vis.wait_for_timeout(1800)
    t = vis.inner_text("#view")
    check("visitor sees the promotion, prize and closing time", "Win a car" in t and "Toyota Premio" in t and "Entries close" in t, t[:300])
    check("visitor sees the permit and the scam warning", "LGRB-TEST-1" in t and "never asks for money" in t)
    check("visitor is asked to sign in, no form", vis.locator("#pf").count() == 0 and vis.locator("a[href='#/signin']").count() >= 1)
    check("terms readable before signing in", vis.locator("details.terms").count() == 1)
    check("no sideways scroll (visitor)", no_sideways(vis))

    # 4. Buyer enters
    bu = page(); signin(bu, "pbuyer@x.test"); go(bu, "#/promotions/current?src=radio")
    check("form filled from the profile", bu.input_value("#pf input[name=name]") == "Bea Buyer" and bu.input_value("#pf input[name=mobile]") == "+256772000111")
    shot(bu, "Saaz_BuildQueue_Promotions_Entry_%s_2026-11-03.png" % ("Desktop" if W >= 1024 else "Phone"))
    bu.fill("#pf input[name=current_car]", "Toyota Premio 2008"); bu.fill("#pf input[name=dream_car]", "Toyota Harrier")
    bu.click("#pf button"); bu.wait_for_timeout(800)
    check("T&C tick needed (browser stops the form)", sql("select count(*) from promo_entries")[0][0] == 0)
    bu.check("#pf input[name=terms]"); bu.check("#pf input[name=marketing_ok]"); bu.click("#pf button"); bu.wait_for_timeout(1800)
    check("entry accepted, 'You're in' shown", bu.locator("#promodone").count() == 1, bu.inner_text("#view")[:200])
    e = sql("select source, marketing_ok, whatsapp_ok, mobile from promo_entries where user_id=%s", (B,))
    check("source and consent recorded as chosen", e and e[0][0] == "radio" and e[0][1] is True and e[0][2] is False, e)
    check("no sideways scroll (buyer)", no_sideways(bu))
    b2 = page(); signin(b2, "pbuyer2@x.test"); go(b2, "#/promotions/win-a-car")
    b2.fill("#pf input[name=mobile]", "0701 234567"); b2.fill("#pf input[name=current_car]", "None")
    b2.fill("#pf input[name=dream_car]", "<img src=x id=pwn onerror=alert(1)>"); b2.check("#pf input[name=terms]"); b2.click("#pf button"); b2.wait_for_timeout(1800)
    check("second buyer entered (direct)", sql("select source from promo_entries where user_id=%s", (B2,)) == [("direct",)])

    # 5. Admin: entries, export, close, draw, tell the winner
    pid = sql("select id from promotions")[0][0]
    go(ad, "#/admin/promotion/%s" % pid)
    check("admin sees 2 entries", "Entries 2" in ad.inner_text("body").replace("\n", " "))
    check("markup in an entry stays text", ad.locator("#pwn").count() == 0 and "<img src=x" in ad.inner_text("body"))
    check("report counts sources", "radio" in ad.inner_text(".rgrid"))
    shot(ad, "Saaz_BuildQueue_Promotions_Admin_%s_2026-11-03.png" % ("Desktop" if W >= 1024 else "Phone"))
    with ad.expect_download() as dl: ad.click("#pexport")
    f = dl.value; body = open(f.path(), encoding="utf-8-sig").read()
    check("CSV name has the slug and date range", f.suggested_filename == "Promotions_win-a-car_Entries_2026-11-01_to_2030-12-31.csv", f.suggested_filename)
    check("CSV has both entries and the header", body.count("\n") >= 3 and "Bea Buyer" in body and "Next car" in body, body[:200])
    check("export recorded in the history", sql("select count(*) from audit_log where action='promotion entries exported'")[0][0] == 1)
    ad.click(".row [data-to=closed]"); ad.wait_for_timeout(200); ad.click(".row [data-to=closed]"); ad.wait_for_timeout(1500)
    check("entries closed", sql("select status from promotions")[0][0] == "closed")
    ad.fill("#pdraw input[name=witness]", "Test witness, LGRB"); ad.click("#pdraw button"); ad.wait_for_timeout(200); ad.click("#pdraw button"); ad.wait_for_timeout(1800)
    check("draw ran and shows the seed", "Seed" in ad.inner_text("body") and sql("select count(*) from promo_results")[0][0] == 2)
    win = sql("select e.user_id from promo_results r join promo_entries e on e.id=r.entry_id where r.role='winner'")[0][0]
    ad.click("[data-res][data-to=contacted]"); ad.wait_for_timeout(200); ad.click("[data-res][data-to=contacted]"); ad.wait_for_timeout(1500)
    check("telling the winner sends their inbox notice", sql("select count(*) from notifications where user_id=%s and kind='promotion_winner'", (win,))[0][0] == 1)
    check("no sideways scroll (admin)", no_sideways(ad))
    wpg = bu if win == B else b2; go(wpg, "#/inbox")
    check("winner sees the notice in the inbox", "You were drawn in Win a car" in wpg.inner_text("#view"))
    check("no script errors", not errors, errors[:3])
    br.close()
print(f"\n{ok} passed, {bad} failed")
sys.exit(1 if bad else 0)
