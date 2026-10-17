"""Browser test of the whole marketplace flow at phone width, against the local Supabase stand-in."""
import os, sys, json, psycopg2
from PIL import Image
from playwright.sync_api import sync_playwright
D = os.path.dirname(os.path.abspath(__file__))
APP = "http://localhost:8777/saaz/app/"
W = int(sys.argv[1]) if len(sys.argv) > 1 else 390
photos = []
for i, c in enumerate([(200, 40, 40), (40, 120, 200), (30, 160, 80), (220, 180, 30)]):
    p = os.path.join(D, f"p{i}.jpg"); Image.new("RGB", (1600, 1200), c).save(p); photos.append(p)
db = psycopg2.connect(host="/var/tmp/saazpg", port=5433, user="postgres", dbname="sb"); db.autocommit = True
def sql(q, a=()):
    c = db.cursor(); c.execute(q, a or None); return c.fetchall() if c.description else None
ok = bad = 0
import base64, hashlib, hmac, struct, time
def totp(secret, t=None):
    k = base64.b32decode(secret + "=" * (-len(secret) % 8)); c = int((t or time.time()) // 30)
    h = hmac.new(k, struct.pack(">Q", c), hashlib.sha1).digest(); o = h[-1] & 15
    return "%06d" % ((struct.unpack(">I", h[o:o + 4])[0] & 0x7fffffff) % 1000000)
def check(name, cond, extra=""):
    global ok, bad
    if cond: ok += 1; print("PASS", name)
    else: bad += 1; print("FAIL", name, extra)

with sync_playwright() as pw:
    br = pw.chromium.launch()
    errors = []
    def ctx(name):
        c = br.new_context(viewport={"width": W, "height": 860})
        pg = c.new_page()
        pg.on("pageerror", lambda e: errors.append(f"{name}: {e}"))
        pg.on("console", lambda m: errors.append(f"{name} console: {m.text}") if m.type == "error" and "favicon" not in m.text and "cdnjs" not in m.text and "ERR_" not in m.text and "Failed to load resource" not in m.text else None)
        return pg
    def overflow(pg, label):
        r = pg.evaluate("""()=>{const w=innerWidth;const bad=[...document.querySelectorAll('body *')].filter(e=>{const b=e.getBoundingClientRect();return b.width&&b.right>w+1&&!e.closest('.tablewrap,.tabs,.appnav,.faststrip,.msgs,.report .micro,.report .waves,.report .ribbon')}).map(e=>e.tagName+'.'+e.className).slice(0,4);return {sw:document.documentElement.scrollWidth>w,bad}}""")
        check(f"no sideways scroll: {label}", not r["sw"] and not r["bad"], r)
    def go(pg, h): pg.goto("about:blank"); pg.goto(APP + h); pg.wait_for_timeout(800)
    def toast(pg): pg.wait_for_selector(".toast.show", timeout=6000); t = pg.inner_text("#toast"); pg.wait_for_timeout(200); return t
    def signup(pg, name, email, country="UG"):
        go(pg, "#/signup"); pg.fill("input[name=name]", name); pg.fill("input[name=email]", email)
        pg.fill("input[name=mobile]", "+256 700 111 222"); pg.fill("input[name=password]", "demo1234"); pg.click("form button"); pg.wait_for_timeout(1200)
    def signin(pg, email, as_):
        go(pg, "#/signin"); pg.check(f"input[name=as][value={as_}]"); pg.fill("input[name=email]", email); pg.fill("input[name=password]", "demo1234"); pg.click("form button"); pg.wait_for_timeout(1500)

    # Admin
    adm = ctx("admin"); signup(adm, "Ann Admin", "admin@saaz.test")
    sql("insert into public.admins (user_id, name) select id, 'Ann Admin' from auth.users where email='admin@saaz.test'")
    # The normal sign-in has no Admin choice, and Admin looks like a missing page without the authenticator
    go(adm, "#/signin"); check("normal sign-in offers no Admin", adm.locator("input[name=as][value=admin]").count() == 0 and "Admin" not in adm.inner_text("#view"))
    signin(adm, "admin@saaz.test", "buyer")
    go(adm, "#/admin"); check("admin pages hidden after password only", "Page not found" in adm.inner_text("#view"), adm.inner_text("#view")[:200])
    adm.click("#acct summary"); check("no Admin area in the menu after password only", adm.locator(".acctmenu [data-mode=admin]").count() == 0)
    adm.click("#signout"); adm.wait_for_timeout(800)
    # Staff sign-in: password, add the authenticator, approve it from the SQL Editor, sign in again with a code
    def staff(code_from_key=None):
        go(adm, "#/ops-7q4k"); adm.fill("input[name=email]", "admin@saaz.test"); adm.fill("input[name=password]", "demo1234"); adm.click("#pf button"); adm.wait_for_timeout(1200)
    staff()
    key = adm.inner_text(".key code").strip(); check("staff page shows a QR code and key", adm.locator("img.qr").count() == 1 and len(key) >= 16)
    adm.fill("input[name=code]", "000000" if totp(key) != "000000" else "111111"); adm.click("#cf button"); adm.wait_for_timeout(800)
    check("wrong code refused", "Wrong code" in adm.inner_text("#cerr"), adm.inner_text("#view")[:200])
    adm.fill("input[name=code]", totp(key)); adm.click("#cf button"); adm.wait_for_timeout(1500)
    check("authenticator added, waiting for approval", "Authenticator added" in adm.inner_text("#view"), adm.inner_text("#view")[:300])
    pin = open(os.path.join(os.environ.get("SAAZ_REPO", os.path.join(D, "..")), "supabase", "marketplace_10b_pin_admin_authenticator.sql")).read().replace("ssemujjujames@saazinvestmentsltd.com", "admin@saaz.test")
    sql(pin)
    adm.click("#so"); adm.wait_for_timeout(800)
    staff(); check("second sign-in asks only for the code", adm.locator("img.qr").count() == 0 and adm.locator("input[name=code]").count() == 1)
    adm.fill("input[name=code]", totp(key)); adm.click("#cf button"); adm.wait_for_timeout(1800)
    check("admin lands on overview", "#/admin" in adm.url and adm.locator("text=Garage applications").count() == 1, adm.url)
    check("admin sign-in in the activity log", sql("select count(*) from audit_log where action='admin signed in with authenticator'")[0][0] == 1)
    overflow(adm, "admin overview")

    # Garage applies with a new account in the same form
    gar = ctx("garage"); go(gar, "#/garage/apply")
    gar.fill("input[name=acc_name]", "Gus Owner"); gar.fill("input[name=acc_email]", "gus@garage.test"); gar.fill("input[name=acc_mobile]", "+256700222333"); gar.fill("input[name=acc_password]", "demo1234")
    gar.fill("input[name=name]", "Kampala Motors"); gar.select_option("#greg", "Kampala"); gar.fill("input[name=address]", "Plot 4, Ntinda"); gar.fill("input[name=phone]", "+256700999000")
    gar.fill("input[name=registration_no]", "URSB-123"); gar.fill("input[name=years]", "8"); gar.check("input[value=Toyota]"); gar.check("input[name=honest]")
    overflow(gar, "garage apply"); gar.click("form button"); gar.wait_for_timeout(1500)
    check("garage application sent", gar.locator("text=Application sent").count() == 1, gar.inner_text("#view")[:300])
    go(gar, "#/garage"); check("garage blocked until certified", "with Saaz" in gar.inner_text("#view"))

    go(adm, "#/admin"); adm.click("text=Kampala Motors"); adm.wait_for_timeout(800)
    adm.click("button[value=approve]"); t = toast(adm); check("admin approves garage", "owner is told" in t, t)

    # Seller lists a car
    sel = ctx("seller"); signup(sel, "Sam Seller", "sam@x.test")
    go(sel, "#/sell/new"); sel.fill("#vin", "JTEBU3FJ10K123456"); sel.click("#vf button"); sel.wait_for_timeout(1000)
    check("VIN decode: new to Saaz, partial decode", "New to Saaz" in sel.inner_text("#rest") and sel.input_value("input[name=make]") == "Toyota", sel.inner_text("#rest")[:200])
    sel.fill("input[name=model]", "Harrier"); sel.fill("input[name=year]", "2015"); sel.select_option("select[name=body]", "SUV"); sel.fill("input[name=colour]", "White")
    sel.fill("input[name=mileage]", "84000"); sel.select_option("#reg", "Kampala"); sel.fill("input[name=plate]", "UBA 123X"); sel.fill("input[name=price]", "95000000")
    sel.fill("textarea[name=description]", "Clean Harrier, one owner in Uganda, full service history at the dealer.")
    sel.set_input_files("#files", photos); sel.wait_for_timeout(2500)
    check("4 photos uploaded and shrunk", sel.locator("#thumbs img").count() == 4)
    sizes = [os.path.getsize(os.path.join(D, "..", "sbtest", "storage", "car-photos", *p.split("/"))) for p in []]
    sel.check("input[name=logbook_name_matches]"); overflow(sel, "list a car")
    sel.click("button[value=submit]"); sel.wait_for_timeout(2000)
    check("submitted: car page shows garage in play", "Kampala Motors" in sel.inner_text("#view") and "Awaiting inspection" in sel.inner_text("#view"), sel.inner_text("#view")[:400])
    stored = sql("select photos from listings")[0][0]
    fsz = [os.path.getsize(os.path.join(D, "..", "sbtest", "storage", "car-photos", p)) for p in stored]
    check("photos about 30 KB each (under 45 KB)", all(s < 45000 for s in fsz), fsz)
    check("seller can't agree before garage messages", sel.is_disabled("#agree"))
    overflow(sel, "my car")

    # Garage contacts seller
    signin(gar, "gus@garage.test", "garage")
    check("garage dashboard shows the car offered", "Offered to you" in gar.inner_text("#view") and "Harrier" in gar.inner_text("#view"), gar.inner_text("#view")[:300])
    overflow(gar, "garage dashboard")
    gar.click(".rows a"); gar.wait_for_timeout(900)
    gar.fill("form.send input", "Hello, we can review on Tuesday. Call 0772 123 456"); gar.click("form.send button"); gar.wait_for_timeout(1000)
    check("contact hidden before agreement", "772" not in gar.inner_text(".msgs") and "hidden until you agree" in gar.inner_text(".msgs"), gar.inner_text(".msgs"))
    overflow(gar, "garage job")
    go(sel, "#/my/cars"); sel.click(".rows a"); sel.wait_for_timeout(900)
    sel.click("#agree"); t = toast(sel); check("seller agrees", "Agreed" in t, t)

    # Garage writes and issues the review
    go(gar, "#/garage"); gar.click(".rows a"); gar.wait_for_timeout(800)
    gar.fill("input[name=date]", "2026-10-20"); gar.click("#df button"); toast(gar)
    gar.click("#start"); gar.wait_for_timeout(1200)
    check("review editor opens", "12-point check" in gar.inner_text("#view"))
    keys = ['engine','gearbox','brakes','steering','tyres','electrics','body','chassis','interior','test_drive','odometer','vin']
    for k in keys: gar.click(f"input[name=c_{k}][value={'advise' if k=='tyres' else 'pass'}] + span")
    gar.click("#map [data-panel=bonnet]"); gar.wait_for_timeout(200)
    check("live score preview: 96, conditional", "96/100" in gar.inner_text("#pv") and "Conditional" in gar.inner_text("#pv"), gar.inner_text("#pv"))
    gar.fill("input[name=odometer]", "84500"); gar.fill("textarea[name=notes]", "Front tyres at 3 mm, replace within 3 months. Small scratch on bonnet.")
    gar.check("input[name=in_person]"); overflow(gar, "review editor")
    gar.click("button[value=issue]"); gar.wait_for_timeout(300); gar.click("button[value=issue]"); gar.wait_for_timeout(2000)
    check("issue goes to the report document", "#/report/" in gar.url and "Saaz inspection report" in gar.inner_text("#view"), gar.url)
    code = gar.url.split("#/report/")[1]
    check("report shows score, rosette and signature", gar.locator(".rosette path").count() >= 3 and "Gus Owner" in gar.inner_text(".sigs"))
    overflow(gar, "report")

    # Verify page (public)
    pub = ctx("public"); go(pub, "#/verify?code=" + code); pub.wait_for_timeout(1000)
    check("public verify: genuine", "Genuine Saaz inspection" in pub.inner_text("#out"), pub.inner_text("#out")[:200])
    overflow(pub, "verify")

    # Admin approves
    go(adm, "#/admin"); adm.click("text=Cars waiting for approval >> xpath=.. >> a"); adm.wait_for_timeout(1000)
    overflow(adm, "admin car")
    adm.click("button[value=approve]"); t = toast(adm); check("admin approves listing", "seller is told" in t, t)

    # Buyer
    buy = ctx("buyer"); signup(buy, "Bob Buyer", "bob@x.test")
    go(buy, "#/browse"); check("browse shows the live car with review", "Harrier" in buy.inner_text("#view") and "96/100" in buy.inner_text("#view"), buy.inner_text("#view")[:300])
    overflow(buy, "browse")
    buy.click(".car"); buy.wait_for_timeout(1200); overflow(buy, "car page")
    go(sel, "#/my/cars"); sel.click(".rows a"); sel.wait_for_timeout(900)
    sel.fill("input[name=min_pct]", "90"); sel.check("input[name=auto_reject][value='1']"); sel.check("input[name=no_trade_in]"); sel.click("#rules button"); toast(sel)
    go(buy, "#/browse"); buy.click(".car"); buy.wait_for_timeout(1000)
    buy.fill("input[name=amount]", "80000000"); buy.click("#offer button"); buy.wait_for_timeout(1000)
    msg = buy.inner_text("#oerr"); check("auto-reject tells rule, never the minimum", "below the seller's minimum" in msg and "90" not in msg and "85" not in msg, msg)
    buy.fill("input[name=amount]", "90000000"); buy.fill("textarea[name=message]", "Can I see it Saturday?"); buy.click("#offer button"); buy.wait_for_timeout(1500)
    check("offer sent, deal page", "#/deals/" in buy.url, buy.url); overflow(buy, "deal page")
    go(sel, "#/my/cars"); check("my cars shows demand counts", "views this week" in sel.inner_text(".rows") and "1 open" in sel.inner_text(".rows"), sel.inner_text(".rows"))
    sel.click(".rows a"); sel.wait_for_timeout(1000)
    check("seller demand panel", "Auto-rejected offers" in sel.inner_text("#view") and sel.locator(".bars .bar").count() == 14)
    sel.click("ul.list a:has-text(\"UGX 90,000,000\")"); sel.wait_for_timeout(900)
    sel.fill("#cf input", "93000000"); sel.click("#cf button"); toast(sel)
    buy.reload(); buy.wait_for_timeout(1200); buy.click("button[data-a=accept]"); buy.wait_for_timeout(1200)
    check("deal agreed, contacts shared", "Contact details" in buy.inner_text("#view") and "+256 700 111 222" in buy.inner_text("#view"), buy.inner_text("#view")[:400])
    go(adm, "#/admin/deals"); adm.click(".tbl a"); adm.wait_for_timeout(900)
    b = adm.locator("button[data-a=complete]"); b.click(); adm.wait_for_timeout(200); b.click(); t = toast(adm)
    check("admin completes sale", sql("select status from listings")[0][0] == "sold", t)
    go(pub, "#/selling"); pub.wait_for_timeout(800)
    check("what's selling lists the model", "Toyota Harrier" in pub.inner_text("#view"))
    overflow(pub, "what's selling")
    for t in ["cars", "saaz", "vehicles", "reviews", "garages", "users", "deals", "conversations", "audit", "outbox", "settings", "selling"]:
        go(adm, "#/admin/" + t); adm.wait_for_timeout(500)
        check(f"admin tab {t} loads", "Couldn't load" not in adm.inner_text("#view"), adm.inner_text("#view")[:200]); overflow(adm, "admin " + t)
    go(sel, "#/inbox"); check("seller inbox has notices", sel.locator(".list li").count() >= 5)
    # New: per-thing history, required asterisks, links from emails
    uid = sql("select id from auth.users where email='sam@x.test'")[0][0]
    go(adm, "#/admin/user/" + str(uid)); adm.wait_for_timeout(800)
    t = adm.inner_text("#view")
    check("admin user page with its own history", "History of this account" in t and "Cars they listed" in t and "submitted" in t, t[:300]); overflow(adm, "admin user")
    gid = sql("select id from garages limit 1")[0][0]
    go(adm, "#/admin/garage/" + str(gid)); adm.wait_for_timeout(1200)
    check("garage page shows its own history", "History of this garage" in adm.inner_text("#view") and "applied" in adm.inner_text("#ghist"), adm.inner_text("#view")[-300:])
    go(adm, "#/admin/audit"); adm.wait_for_timeout(1000)
    check("all activity links each row to what it touched", adm.locator(".tbl a[href^='#/admin/car/']").count() > 0 and adm.locator(".tbl a[href^='#/admin/user/']").count() > 0)
    go(pub, "#/signup"); pub.wait_for_timeout(400)
    check("required fields marked with *", pub.locator("label .req").count() == 4, pub.locator("label .req").count())
    go(adm, "#/admin/garage-new"); adm.wait_for_timeout(500)
    check("direct-add reason explained", "Why are you adding this garage directly" in adm.inner_text("#view"))
    sys.path.insert(0, os.path.join(D, "..", "sbtest")); import importlib.util
    spec = importlib.util.spec_from_file_location("fk", os.path.join(D, "..", "sbtest", "fakesb_jwt.py")); fk = importlib.util.module_from_spec(spec); spec.loader.exec_module(fk)
    gus = sql("select id from auth.users where email='gus@garage.test'")[0][0]
    inv = ctx("invite"); inv.goto(APP + "#access_token=" + fk.jwt(gus, "gus@garage.test") + "&refresh_token=r-" + str(gus) + "&expires_in=3600&expires_at=9999999999&token_type=bearer&type=invite"); inv.wait_for_timeout(2500)
    check("invite link opens 'Set your password'", "#/reset?first=1" in inv.url and "Set your password" in inv.inner_text("#view"), inv.url + " " + inv.inner_text("#view")[:200])
    inv.fill("input[name=password]", "demo1234"); inv.click("form button"); inv.wait_for_timeout(1500)
    check("after setting the password, a garage invitee lands on the garage dashboard", "#/garage" in inv.url and "Offered to you" in inv.inner_text("#view"), inv.url)
    # "review" is now "inspection" everywhere people read
    for pg_, h in [(sel, "#/my/cars"), (pub, "#/how"), (pub, "#/verify"), (adm, "#/admin/reviews")]:
        go(pg_, h); pg_.wait_for_timeout(500)
        txt = pg_.inner_text("#view").lower()
        check(f"no 'review' wording on {h}", " review" not in txt and "reviewed" not in txt, [l for l in txt.splitlines() if "review" in l][:3])
    # Sign up as a seller lands on My cars
    nsel = ctx("newseller"); go(nsel, "#/signup"); nsel.check("input[name=as][value=seller]"); nsel.fill("input[name=name]", "Sara Seller"); nsel.fill("input[name=email]", "sara@x.test")
    nsel.fill("input[name=mobile]", "+256 700 000 111"); nsel.fill("input[name=password]", "demo1234"); nsel.click("form button"); nsel.wait_for_timeout(1500)
    check("sign-up as seller lands on My cars", "#/my/cars" in nsel.url and "My cars" in nsel.inner_text("#view"), nsel.url)
    # Uganda only, East Africa Time, no account enumeration
    for h in ["#/signup", "#/browse", "#/selling", "#/garage/apply"]:
        go(pub, h); pub.wait_for_timeout(300)
        check(f"no Kenya or country chooser on {h}", "Kenya" not in pub.content() and "KES" not in pub.inner_text("body") and pub.locator("select[name=country]").count() == 0)
    go(sel, "#/sell/new"); sel.fill("#vin", "JN1TBNT37F0012345"); sel.click("#vf button"); sel.wait_for_timeout(900)
    check("sell form is Uganda only, prices in UGX", sel.locator("select[name=country]").count() == 0 and "Asking price (UGX)" in sel.inner_text("#rest"))
    go(sel, "#/my/cars"); sel.click(".rows a"); sel.wait_for_timeout(900)
    check("times shown in East Africa Time", " EAT" in sel.inner_text(".timeline"))
    x = ctx("dup"); signup(x, "Someone Else", "sam@x.test")
    t = x.inner_text("#err"); check("sign-up doesn't reveal an existing account", "already has an account" not in t and "couldn't create an account" in t, t)
    go(sel, "#/account"); sel.fill("#pw input[name=password]", "newpass123"); sel.fill("#pw input[name=again]", "newpass124"); sel.click("#pw button"); sel.wait_for_timeout(300)
    check("password change checks both entries match", "don't match" in sel.inner_text("#pwerr"))
    adm.set_viewport_size({"width": 1280, "height": 860}); go(adm, "#/admin/cars"); adm.wait_for_timeout(800)
    check("admin side menu grouped by work", adm.locator(".adminside .navgroup").count() == 7 and adm.locator(".adminside a[aria-current=page]").inner_text() == "Cars")
    adm.set_viewport_size({"width": W, "height": 860})
    check("no script errors", not errors, errors[:5])
    br.close()
print(f"\n{ok} passed, {bad} failed")
