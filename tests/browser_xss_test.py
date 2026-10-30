"""Stored script injection: every text a person can type is filled with markup, then every role's screens are opened.
Passes when the markup shows as text everywhere (nothing of it becomes a page element) and no injected code runs.
Run straight after tests/demo_journey.py (it uses the demo accounts and car)."""
import base64, hashlib, hmac, struct, sys, time, psycopg2
from playwright.sync_api import sync_playwright
APP = "http://localhost:8777/saaz/"; SECRET = "JBSWY3DPEHPK3PXP"
db = psycopg2.connect(host="/var/tmp/saazpg", port=5433, user="postgres", dbname="sb"); db.autocommit = True; cur = db.cursor()
def sql(q, a=()): cur.execute(q, a or None); return cur.fetchall() if cur.description else None
X = "\"'><img data-xss src=x onerror=\"window.__xss=1\"><svg data-xss onload=\"window.__xss=2\"></svg><b data-xss>"
J = "javascript:window.__xss=3"
# Every free-text field a buyer, seller, garage or admin can fill
for q in ["update profiles set name = name || %s", "update listings set description = description || %s, colour = colour || %s, admin_note = coalesce(admin_note,'') || %s",
          "update messages set body = body || %s", "update reviews set notes = coalesce(notes,'') || %s", "update garages set name = name || %s, address = address || %s",
          "update notifications set body = body || %s", "update deal_events set message = coalesce(message,'') || %s", "update review_opinions set reason = reason || %s",
          "update listings set model = model || %s"]:
    try: sql(q, (X,) * q.count("%s"))
    except psycopg2.Error as e: print("skip:", q[:40], e.diag.message_primary)
# The database refuses a link that isn't a Saaz page (part 21). Then the rule is lifted for this run, to prove the inbox checks too.
try: sql("update notifications set link = %s where id in (select id from notifications limit 1)", (J,)); db_refused = False
except psycopg2.Error: db_refused = True
CON = sql("select pg_get_constraintdef(oid) from pg_constraint where conname = 'notifications_link_is_saaz_page'")
if CON: sql("alter table notifications drop constraint notifications_link_is_saaz_page")
sql("update notifications set link = %s where id in (select id from notifications limit 3)", (J,))
car = sql("select id, ref from listings where model like '%%data-xss%%' limit 1")[0]; deal = sql("select id from deals limit 1"); code = sql("select verify_code from reviews where verify_code is not null limit 1")
conv = sql("select id from conversations limit 1"); garage = sql("select id from garages limit 1")[0][0]; user = sql("select id from profiles limit 1")[0][0]
PUB = ["#/browse", f"#/car/{car[1]}", "#/", f"#/report/{code[0][0]}" if code else None]
ROLES = {("bob@demo.test", "buyer"): ["#/offers", "#/inbox", "#/account", f"#/deals/{deal[0][0]}" if deal else None, "#/browse?saved=1"],
         ("sam@demo.test", "seller"): ["#/my/cars", f"#/my/cars/{car[0]}", "#/inbox", f"#/deals/{deal[0][0]}" if deal else None],
         ("gus@demo.test", "garage"): ["#/garage", "#/garage/team", f"#/garage/job/{conv[0][0]}" if conv else None, "#/inbox"],
         ("ivy@demo.test", "garage"): ["#/garage", "#/inbox"],
         ("admin@demo.test", "seller"): ["#/admin", "#/admin/cars", f"#/admin/car/{car[0]}", "#/admin/garages", f"#/admin/garage/{garage}", "#/admin/users", f"#/admin/user/{user}",
            "#/admin/deals", "#/admin/reviews", "#/admin/audit", "#/admin/outbox", "#/admin/conversations", "#/admin/reports", "#/inbox"]}
def totp(s):
    k = base64.b32decode(s); h = hmac.new(k, struct.pack(">Q", int(time.time()) // 30), hashlib.sha1).digest(); o = h[-1] & 15
    return "%06d" % ((struct.unpack(">I", h[o:o + 4])[0] & 0x7fffffff) % 1000000)
ok = bad = 0
def check(n, c, x=""):
    global ok, bad
    if c: ok += 1; print("PASS", n)
    else: bad += 1; print("FAIL", n, x)
with sync_playwright() as pw:
    br = pw.chromium.launch()
    def look(pg, who, h):
        pg.goto("about:blank"); pg.goto(APP + h); pg.wait_for_timeout(1400)
        n = pg.locator("[data-xss]").count(); ran = pg.evaluate("() => window.__xss || null")
        shown = X[:12] in pg.inner_text("body")
        js = pg.locator("a[href^='javascript:']").count()
        check(f"{who} {h}: markup stays text", n == 0 and ran is None and js == 0, {"elements": n, "ran": ran, "javascript links": js})
        return shown
    # Policy off for this test, so it proves the escaping itself (the policy is a second line, tested in browser_csp_test.py)
    c = br.new_context(viewport={"width": 1280, "height": 900}, bypass_csp=True); pg = c.new_page(); seen = False
    for h in [x for x in PUB if x]: seen = look(pg, "visitor", h) or seen
    c.close()
    for (email, as_), hs in ROLES.items():
        c = br.new_context(viewport={"width": 1280, "height": 900}, bypass_csp=True); pg = c.new_page()
        pg.goto(APP + "#/signin"); pg.wait_for_timeout(900); pg.check(f"input[name=as][value={as_}]"); pg.fill("input[name=email]", email); pg.fill("input[name=password]", "demo1234"); pg.click("#view form button"); pg.wait_for_timeout(1600)
        if email.startswith("admin"):
            pg.goto(APP + "#/admin/verify"); pg.wait_for_timeout(900); pg.fill("input[name=password]", "demo1234"); pg.click("#pf button"); pg.wait_for_timeout(1200)
            pg.fill("input[name=code]", totp(SECRET)); pg.click("#cf button"); pg.wait_for_timeout(1800)
        for h in [x for x in hs if x]: seen = look(pg, email.split("@")[0], h) or seen
        c.close()
    check("the injected text was really on screen somewhere (the test reached it)", seen)
    check("the database refuses a notification link that isn't a Saaz page", db_refused)
    if CON:
        sql("update notifications set link = '#/inbox' where link !~ '^#/'")
        sql("alter table notifications add constraint notifications_link_is_saaz_page " + CON[0][0])
    br.close()
print(f"\n{ok} passed, {bad} failed"); sys.exit(1 if bad else 0)
