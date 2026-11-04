"""Browser test for Notifications (part 24) on the local stack (3 Nov 2026).
Usage: python3 tests/browser_notify_test.py <site url> <width>   (fresh database; it adds its own people)
Covers: My account shows the mobile check; a code by SMS verifies the number (the code is read from the outbox, as the SMS
would carry it); message settings save; Admin, Outbox shows the sender state, SMS rows and their status, Send again; channels
per notice change; an SMS opt-out; Announcements: check who gets it, send (two taps), inbox notice, SMS only to the opted-in
person; no sideways scroll; no script errors. SHOTS=<dir> saves screenshots."""
import sys, os, json, time, base64, hashlib, hmac, struct, re, psycopg2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import admin_session
from playwright.sync_api import sync_playwright
SITE, W = sys.argv[1], int(sys.argv[2])
db = psycopg2.connect(host="/var/tmp/saazpg", port=5433, user="postgres", dbname="sb"); db.autocommit = True; cur = db.cursor()
def sql(q, a=()): cur.execute(q, a or None); return cur.fetchall() if cur.description else None
def user(e, n, mobile=None, verified=False):
    u = sql("insert into auth.users (email, raw_user_meta_data, email_confirmed_at) values (%s,%s,now()) returning id", (e, json.dumps({"name": n, "country": "UG"})))[0][0]
    sql("update profiles set mobile=%s, phone_verified=%s where id=%s", (mobile, verified, u)); return u
A = user("nadmin@saaz.test", "Ann Admin"); sql("insert into admins (user_id, name, role) values (%s,'Ann Admin','admin')", (A,))
U = user("nuser@x.test", "Uma User", "0772 123456")
Wv = user("nwant@x.test", "Wes Wants", "+256772777777", True)
sql("insert into notify_prefs (user_id, news_sms) values (%s, true)", (Wv,))
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
errors = []; SHOTS = os.environ.get("SHOTS"); tag = "Desktop" if W >= 1024 else "Phone"
with sync_playwright() as p:
    br = p.chromium.launch()
    def page():
        ctx = br.new_context(viewport={"width": W, "height": 900}); pg = ctx.new_page(); pg.on("pageerror", lambda e: errors.append(str(e))); return pg
    def shot(pg, name):
        if SHOTS: pg.screenshot(path=os.path.join(SHOTS, f"Saaz_BuildQueue_Notifications_{name}_{tag}_2026-11-03.png"), full_page=True)
    def go(pg, h): pg.goto("about:blank"); pg.goto(SITE + h); pg.wait_for_timeout(1300)
    def signin(pg, email, as_="buyer"):
        go(pg, "#/signin"); pg.check(f"input[name=as][value={as_}]"); pg.fill("input[name=email]", email); pg.fill("input[name=password]", "demo1234"); pg.click("form button"); pg.wait_for_timeout(1500)
    def elevate(pg):
        go(pg, "#/admin/verify"); pg.fill("input[name=password]", "demo1234"); pg.click("#pf button"); pg.wait_for_timeout(1200)
        pg.fill("input[name=code]", totp(SECRET)); pg.click("#cf button"); pg.wait_for_timeout(1800)
    def no_sideways(pg): return pg.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1")

    # 1. My account: check the mobile
    u = page(); signin(u, "nuser@x.test"); go(u, "#/account"); u.wait_for_timeout(800)
    t = u.inner_text("[data-ref=account-messages]")
    check("account shows the mobile, not verified", "0772 123456" in t and "Not verified" in t, t)
    u.click("#pcsend"); u.wait_for_timeout(1300)
    body = sql("select body from outbox where user_id=%s and kind='phone_code'", (U,))
    check("a code SMS is queued for the number", body and "your code is" in body[0][0], body)
    code = re.search(r"code is (\d{6})", body[0][0]).group(1)
    check("the code field appears", u.locator("#pccheck").is_visible())
    u.fill("#pccheck input[name=code]", "000000" if code != "000000" else "111111"); u.click("#pccheck button"); u.wait_for_timeout(1000)
    check("a wrong code says how many tries are left", "tries left" in u.inner_text("#pcerr"))
    u.fill("#pccheck input[name=code]", code); u.click("#pccheck button"); u.wait_for_timeout(1800)
    check("the right code verifies the number", sql("select phone_verified from profiles where id=%s", (U,))[0][0] and "Verified" in u.inner_text("[data-ref=account-messages]"))
    shot(u, "Account")
    u.uncheck("#npf input[name=alerts_sms]"); u.check("#npf input[name=news_sms]"); u.click("#npf button"); u.wait_for_timeout(1300)
    check("message settings saved", sql("select alerts_sms, news_sms from notify_prefs where user_id=%s", (U,)) == [(False, True)])
    check("no sideways scroll (account)", no_sideways(u))

    # 2. Admin outbox
    sql("select notify(%s,'offer_received','New offer of UGX 40,000,000 on your Toyota',null,'{app,sms}')", (Wv,))
    sql("select notify(%s,'offer_received','New offer for Uma',null,'{app,sms}')", (U,))
    ad = page(); signin(ad, "nadmin@saaz.test", "seller"); elevate(ad); go(ad, "#/admin/outbox")
    t = ad.inner_text(".adminmain")
    check("outbox says the sender has never run", "never run" in t, t[:300])
    check("the SMS to Wes waits to send", "New offer of UGX 40,000,000" in t and "Waiting to send".lower() in t.lower())
    check("Uma's SMS shows why it wasn't sent", "Turned off SMS alerts" in t)
    check("phone codes are hidden from admins", code not in t and "hidden" in t)
    sql("update outbox set status='failed', reason='403 InvalidPhoneNumber' where user_id=%s and kind='offer_received'", (Wv,))
    go(ad, "#/admin/outbox?status=failed&channel=sms")
    ad.click("[data-retry]"); ad.wait_for_timeout(1300)
    check("Send again puts a failed SMS back in the queue", sql("select status from outbox where user_id=%s and kind='offer_received'", (Wv,))[0][0] == "queued")
    go(ad, "#/admin/outbox")
    shot(ad, "Outbox")
    ad.check("input[data-kind='offer_received'][data-ch='email']"); ad.click("[data-kindsave='offer_received']"); ad.wait_for_timeout(1300)
    check("channels per notice saved", sql("select channels from notify_kinds where kind='offer_received'") == [(["app", "sms", "email"],)])
    ad.fill("#optf input[name=mobile]", "0772 888888"); ad.fill("#optf input[name=reason]", "Called Saaz on 3 Nov to stop SMS"); ad.click("#optf button"); ad.wait_for_timeout(1300)
    check("SMS opt-out added", sql("select mobile from sms_optout") == [("+256772888888",)])
    check("no sideways scroll (outbox)", no_sideways(ad))

    # 3. Announcements
    go(ad, "#/admin/announce")
    ad.fill("#anf textarea[name=body]", "New inspected Harriers this week. See them on Saaz."); ad.check("#anf input[name=sms]")
    check("counter shows characters and SMS parts", "1 SMS part" in ad.inner_text("#ancount"))
    check("Send stays off until checked", ad.is_disabled("#ansend"))
    ad.click("#anprev"); ad.wait_for_timeout(1300)
    r = ad.inner_text("#anres")
    check("check shows inbox count and SMS count", "people get it" in r and re.search(r"\b2\b\s*get an SMS", r.replace("\n", " ")) is not None, r)
    check("check says the cost is unknown without a price", "Cost unknown" in r)
    shot(ad, "Announce")
    ad.click("#ansend"); ad.wait_for_timeout(200); ad.click("#ansend"); ad.wait_for_timeout(1800)
    check("sent: inbox notices for everyone", sql("select count(*) from notifications where kind='announcement'")[0][0] == sql("select count(*) from profiles")[0][0])
    sms = sql("select user_id from outbox where kind='announcement' and status='queued' order by user_id")
    check("SMS queued only for the opted-in, verified people", sorted(x[0] for x in sms) == sorted([U, Wv]), sms)
    check("the announcement is listed as sent", "New inspected Harriers" in ad.inner_text(".adminmain section:last-of-type"))
    go(u, "#/inbox")
    check("the person sees it in their inbox", "New inspected Harriers" in u.inner_text("#view"))
    check("inbox note no longer says SMS isn't connected", "aren't connected yet" not in u.inner_text("#view"))
    check("no sideways scroll (announce)", no_sideways(ad))
    check("no script errors", not errors, errors[:3])
    br.close()
print(f"\n{ok} passed, {bad} failed")
sys.exit(1 if bad else 0)
