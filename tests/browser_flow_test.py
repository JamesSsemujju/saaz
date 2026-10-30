"""Browser test of the whole marketplace flow at phone width, against the local Supabase stand-in."""
import os, sys, json, psycopg2  # 29 Oct 2026: status words are shown in small capitals, so wording checks ignore case
from PIL import Image
from playwright.sync_api import sync_playwright
D = os.path.dirname(os.path.abspath(__file__))
APP = "http://localhost:8777/saaz/"  # one entry point: the site root
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
    # The normal sign-in has no Admin choice, and Admin looks like a missing page without the extra checks
    go(adm, "#/signin"); check("normal sign-in offers no Admin", adm.locator("input[name=as][value=admin]").count() == 0 and "Admin" not in adm.inner_text("#view"))
    signin(adm, "admin@saaz.test", "buyer")
    go(adm, "#/admin"); check("admin pages hidden after password only", "Page not found" in adm.inner_text("#view"), adm.inner_text("#view")[:200])
    adm.click("#acct summary"); check("admin signed in as buyer: no Admin panel in the menu", adm.locator(".acctmenu .adminentry").count() == 0)
    adm.click("#signout"); adm.wait_for_timeout(1200)
    # Admin signs in through the seller side; the account menu then has Admin panel
    signin(adm, "admin@saaz.test", "seller")
    adm.click("#acct summary"); check("admin signed in as seller: Admin panel in the menu", adm.locator(".acctmenu .adminentry").count() == 1)
    go(adm, "#/admin"); check("menu entry alone gives no access", "Page not found" in adm.inner_text("#view"))
    def admin_entry(password="demo1234"):
        go(adm, "#/my/cars"); adm.click("#acct summary"); adm.click(".acctmenu .adminentry"); adm.wait_for_timeout(700)
        adm.fill("input[name=password]", password); adm.click("#pf button"); adm.wait_for_timeout(1200)
    admin_entry("wrong-password")
    check("wrong password refused and counted", "Wrong password" in adm.inner_text("#perr") and "tries left" in adm.inner_text("#perr"), adm.inner_text("#view")[:200])
    check("failed password recorded", sql("select count(*) from audit_log where action='admin check failed: password'")[0][0] == 1)
    adm.fill("input[name=password]", "demo1234"); adm.click("#pf button"); adm.wait_for_timeout(1200)
    key = adm.inner_text(".key code").strip(); check("first time: QR code and key", adm.locator("img.qr").count() == 1 and len(key) >= 16)
    adm.fill("input[name=code]", "000000" if totp(key) != "000000" else "111111"); adm.click("#cf button"); adm.wait_for_timeout(800)
    check("wrong code refused", "Wrong code" in adm.inner_text("#cerr"), adm.inner_text("#view")[:200])
    adm.fill("input[name=code]", totp(key)); adm.click("#cf button"); adm.wait_for_timeout(1500)
    check("authenticator added, waiting to be pinned", "Authenticator added" in adm.inner_text("#view"), adm.inner_text("#view")[:300])
    go(adm, "#/admin"); check("unpinned authenticator gives no access", "Page not found" in adm.inner_text("#view"))
    pin = open(os.path.join(os.environ.get("SAAZ_REPO", os.path.join(D, "..")), "supabase", "marketplace_10b_pin_admin_authenticator.sql")).read().replace("ssemujjujames@saazinvestmentsltd.com", "admin@saaz.test")
    sql(pin)
    # The session that just proved the pinned authenticator is an admin session: the menu takes it straight to Admin
    go(adm, "#/my/cars"); adm.click("#acct summary")
    check("while the admin session lasts, Admin is an area in the menu (no second check)", adm.locator(".acctmenu a[data-mode=admin]").count() == 1 and adm.locator(".acctmenu .adminentry").count() == 0)
    adm.click("#signout"); adm.wait_for_timeout(1200); signin(adm, "admin@saaz.test", "seller")
    admin_entry(); check("next time: password then only the code", adm.locator("img.qr").count() == 0 and adm.locator("input[name=code]").count() == 1)
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
    check("submitted: car page shows garage in play", "Kampala Motors" in sel.inner_text("#view") and "awaiting inspection" in sel.inner_text("#view").lower(), sel.inner_text("#view")[:400])
    sel.wait_for_timeout(800)
    insp_id = sql("select doc_no from reviews where scope='general' and status='requested'")[0][0]
    check("seller gets the inspection ID on submitting", insp_id in sel.inner_text("#insps") and "requested" in sel.inner_text("#insps").lower(), sel.inner_text("#insps")[:200])
    # Track an inspection: lookup first, sign-in only after a match, nothing private before that
    trk = ctx("tracker"); go(trk, "#/track")
    trk.fill("#tf input", "SZR-2026-999999"); trk.click("#tf button"); trk.wait_for_timeout(900)
    check("unknown ID: told so, no sign-in prompt, nothing about any car", "No inspection has this ID" in trk.inner_text("#terr") and trk.locator("#lf").count() == 0 and "Harrier" not in trk.inner_text("#view"))
    trk.fill("#tf input", insp_id.lower()); trk.click("#tf button"); trk.wait_for_timeout(900)
    check("known ID: sign-in prompt appears, still nothing about the car", trk.locator("#lf").count() == 1 and "Harrier" not in trk.inner_text("#view"))
    go(trk, "#/inspection/" + insp_id); check("opening the inspection page signed out sends you back to the lookup", "#/track" in trk.url, trk.url)
    trk.wait_for_timeout(800); trk.fill("#lf input[name=email]", "sam@x.test"); trk.fill("#lf input[name=password]", "demo1234"); trk.click("#lf button"); trk.wait_for_timeout(1800)
    check("seller signs in from the prompt and sees their inspection", "#/inspection/" + insp_id in trk.url and "General inspection" in trk.inner_text("#view") and "Requested" in trk.inner_text("#view"), trk.inner_text("#view")[:300])
    check("seller has no start button", trk.locator("#startins").count() == 0)
    overflow(trk, "inspection page")
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
    check("job page lists the car's inspections with their IDs", insp_id in gar.inner_text("#view"))
    gar.click("a:has-text('Open to start')"); gar.wait_for_timeout(1000)
    check("owner opens the inspection: start button, no sign-in again", gar.locator("#startins").count() == 1 and gar.locator("#lf").count() == 0, gar.inner_text("#view")[:300])
    sql("update reviews set status='cancelled' where doc_no=%s", (insp_id,))
    gar.click("#startins"); gar.wait_for_timeout(1200)
    check("an inspection cancelled after opening is refused at start", "cancelled" in gar.inner_text("#toast").lower() and "#/garage/review/" not in gar.url, gar.inner_text("#toast"))
    sql("update reviews set status='requested' where doc_no=%s", (insp_id,))
    gar.reload(); gar.wait_for_timeout(1000); gar.click("#startins"); gar.wait_for_timeout(1500)
    check("the inspection keeps its ID when it starts", "Inspection ID" in gar.inner_text("#view") and insp_id in gar.inner_text(".lead"), gar.inner_text(".lead"))
    check("status is in progress", sql("select status from reviews where doc_no=%s", (insp_id,))[0][0] == "draft")
    check("review editor opens", "12-point check" in gar.inner_text("#view"))
    keys = ['engine','gearbox','brakes','steering','tyres','electrics','body','chassis','interior','test_drive','odometer','vin']
    for k in keys: gar.click(f"input[name=c_{k}][value={'advise' if k=='tyres' else 'pass'}] + span")
    gar.click("#map [data-panel=bonnet]"); gar.wait_for_timeout(200)
    check("live score preview: 96, conditional", "96/100" in gar.inner_text("#pv") and "conditional" in gar.inner_text("#pv").lower(), gar.inner_text("#pv"))
    gar.fill("input[name=odometer]", "84500"); gar.fill("textarea[name=notes]", "Front tyres at 3 mm, replace within 3 months. Small scratch on bonnet.")
    gar.check("input[name=in_person]"); overflow(gar, "review editor")
    gar.click("button[value=issue]"); gar.wait_for_timeout(300); gar.click("button[value=issue]"); gar.wait_for_timeout(2000)
    check("issue goes to the report document", "#/report/" in gar.url and "Saaz inspection report" in gar.inner_text("#view"), gar.url)
    code = gar.url.split("#/report/")[1]
    check("the report keeps the inspection ID", insp_id in gar.inner_text("#view"))
    go(gar, "#/garage"); check("garage dashboard opens inspections by ID", gar.locator("#oid").count() == 1)
    gar.fill("#oid input", insp_id.lower()); gar.click("#oid button"); gar.wait_for_timeout(1200)
    check("opening by ID goes to the inspection, completed, with its report", "#/inspection/" + insp_id in gar.url and "Completed" in gar.inner_text("#view") and gar.locator("a:has-text('Open the report')").count() == 1, gar.url)
    go(gar, "#/report/" + code); gar.wait_for_timeout(1000)
    check("report shows score, rosette and signature", gar.locator(".rosette path").count() >= 3 and "Gus Owner" in gar.inner_text(".sigs"))
    overflow(gar, "report")

    # Verify page (public)
    pub = ctx("public"); go(pub, "#/verify?code=" + code); pub.wait_for_timeout(1000)
    check("public verify: genuine", "Genuine Saaz inspection" in pub.inner_text("#out"), pub.inner_text("#out")[:200])
    overflow(pub, "verify")

    # Admin approves
    go(adm, "#/admin"); adm.click("text=Cars waiting for approval >> xpath=.. >> a"); adm.wait_for_timeout(1000)
    overflow(adm, "admin car")
    check("admin car page: support or object, no void", "Saaz view of this report" in adm.inner_text("#view") and adm.locator("#vf").count() == 0)
    check("admin car page lists every inspection with its ID", insp_id in adm.inner_text("#insps"), adm.inner_text("#insps")[:200])
    adm.fill("#opf textarea", "Odometer photo is blurry, please confirm"); adm.click("#opf button[value=object]"); t = toast(adm)
    check("Saaz objects with a reason", "Objection recorded" in t, t)
    adm.wait_for_function("!document.querySelector('#toast').classList.contains('show')", timeout=8000)
    adm.click("button[value=approve]"); t = toast(adm); check("approval blocked while Saaz objects", "Saaz objected" in t, t)
    go(gar, "#/report/" + code); gar.wait_for_timeout(1000)
    check("garage sees the objection on the report", "Saaz objected" in gar.inner_text(".opinions"), gar.inner_text("#view")[-300:])
    gar.fill("#gr textarea", "Odometer read 84,500 km, clear photo sent by WhatsApp"); gar.click("#gr button"); t = toast(gar); check("garage replies to Saaz", "Reply sent" in t, t)
    adm.reload(); adm.wait_for_timeout(1200)
    adm.wait_for_function("!document.querySelector('#toast').classList.contains('show')", timeout=8000)
    adm.fill("#opf textarea", "Clear photo received, report supported"); adm.click("#opf button[value=support]"); toast(adm)
    adm.wait_for_function("!document.querySelector('#toast').classList.contains('show')", timeout=8000)
    adm.click("button[value=approve]"); t = toast(adm); check("admin approves listing", "seller is told" in t, t)
    go(pub, "#/verify?code=" + code); pub.wait_for_timeout(1000)
    check("public check shows what Saaz said", "Saaz supports this report" in pub.inner_text("#out") and "Saaz objected" in pub.inner_text("#out"))
    # Admin acts for the seller: price change with a reason, and the seller sees it
    adm.reload(); adm.wait_for_timeout(1200)
    adm.click("#afs form:has(input[name=price]) button"); t = toast(adm); check("acting needs a reason first", "reason first" in t, t)
    adm.wait_for_function("!document.querySelector('#toast').classList.contains('show')", timeout=8000)
    adm.fill("#afs textarea[name=reason]", "Seller phoned, asked us to raise the price")
    adm.fill("#afs input[name=price]", "96000000"); adm.click("#afs form:has(input[name=price]) button"); t = toast(adm)
    check("admin changed the price for the seller", "changed the asking price" in t and sql("select price from listings")[0][0] == 96000000, t)
    go(sel, "#/inbox"); check("seller told, with the reason", "raise the price" in sel.inner_text("#view"), sel.inner_text("#view")[:300])
    lid = sql("select id from listings")[0][0]; go(sel, "#/my/cars/" + str(lid)); sel.wait_for_timeout(800)
    check("seller's car history shows the team and the reason", "Our team" in sel.inner_text("#view") and "raise the price" in sel.inner_text("#view"))
    overflow(adm, "admin act for seller")

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
    go(adm, "#/deals/" + buy.url.split("#/deals/")[1]); adm.wait_for_timeout(900)
    check("admin deal page has act-for-seller and act-for-buyer panels", adm.locator("#afs").count() == 1 and adm.locator("#afb").count() == 1)
    overflow(adm, "admin deal act for")
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
    isid = sql("insert into auth.sessions (user_id, aal) values (%s,'aal1') returning id", (gus,))[0][0]
    inv = ctx("invite"); inv.goto(APP + "#access_token=" + fk.jwt(gus, "gus@garage.test", isid) + "&refresh_token=r-" + str(isid) + "&expires_in=3600&expires_at=9999999999&token_type=bearer&type=invite"); inv.wait_for_timeout(2500)
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
    # Admin Cars page: the marketplace's own cards, every status; previews stay private
    import admin_session
    c0 = db.cursor(); sara = sql("select id from auth.users where email='sara@x.test'")[0][0]
    c0.execute("select set_config('request.jwt.claims',%s,false)", (admin_session.claims(c0, sara),)); c0.execute("set role authenticated")
    c0.execute("select save_listing(%s)", (json.dumps({"vin": "JN1TBNT37F0099999", "make": "Nissan", "model": "X-Trail", "year": 2016, "fuel": "Petrol", "gearbox": "Automatic", "body": "SUV", "colour": "Grey", "engine": "2.0",
        "mileage": 91000, "plate": "UBC 789Z", "country": "UG", "region": "Kampala", "price": 60000000, "description": "Draft car for the preview test, details to follow.", "photos": [], "owner_authorised": True}),))
    c0.execute("reset role"); draft_ref = sql("select ref from listings where make='Nissan'")[0][0]
    sql("update listings set status='live' where status='sold'")  # test only: put the sold car back on sale to compare cards
    go(adm, "#/admin/cars"); adm.wait_for_timeout(1200)
    n_admin = adm.locator("#view .cars a.car").count(); check("admin Cars page is the listings page with every car", n_admin == 2, n_admin)
    check("same heading and filters as the marketplace, plus status", "Cars with a Saaz inspection" in adm.inner_text("#view") and adm.locator("#flt select[name=status]").count() == 1 and adm.locator("#flt select[name=make]").count() == 1)
    check("the draft carries its status on the photo", "draft" in adm.inner_text("#view .cars").lower())
    go(pub, "#/browse"); pub.wait_for_timeout(1000)
    grab = "() => { const c = [...document.querySelectorAll('.cars a.car')].find(x => x.textContent.includes('Harrier')); return c ? c.innerHTML.replace(/href=\"[^\"]*\"/g, '') : null }"
    a_card = adm.evaluate(grab); p_card = pub.evaluate(grab)
    check("a live car's card is identical in admin and on the marketplace", a_card is not None and a_card == p_card, (a_card, p_card))
    check("the draft is not on the marketplace", "X-Trail" not in pub.inner_text("#view"))
    sql("update listings set status='sold' where make='Toyota'")
    go(pub, "#/car/" + draft_ref); pub.wait_for_timeout(900); check("opening the draft directly as a visitor: not found", "Car not found" in pub.inner_text("#view"), pub.inner_text("#view")[:120])
    go(adm, "#/admin/cars"); adm.wait_for_timeout(1000); adm.click("#view .cars a.car:has-text('X-Trail')"); adm.wait_for_timeout(1000)
    check("clicking an admin card opens the car's management page", "#/admin/car/" in adm.url and "Act for the seller" in adm.inner_text("#view"), adm.url)
    overflow(adm, "admin cars")
    # Garage invite stages: Invited, then Accepted; separate from the garage's certification
    go(gar, "#/garage/team"); gar.wait_for_timeout(800)
    check("team page shows the garage's certification separately", "Certified by Saaz" in gar.inner_text("#view"), gar.inner_text("#view")[:200])
    gar.fill("#f input[name=name]", "Ivy Inspector"); gar.fill("#f input[name=email]", "ivy@garage.test"); gar.click("#f button"); gar.wait_for_timeout(1500)
    go(gar, "#/garage/team"); gar.wait_for_timeout(800)
    row = gar.locator("ul.team li:has-text('ivy@garage.test')").inner_text(); check("new member shows Invited", "invited" in row.lower() and "accepted" not in row.lower(), row)
    ivy = ctx("ivy"); signup(ivy, "Ivy Inspector", "ivy@garage.test"); signin(ivy, "ivy@garage.test", "garage")
    go(gar, "#/garage/team"); gar.wait_for_timeout(800)
    row = gar.locator("ul.team li:has-text('ivy@garage.test')").inner_text(); check("after signing in: Accepted", "accepted" in row.lower(), row)
    go(ivy, "#/garage"); ivy.wait_for_timeout(900)
    check("inspector sees only My jobs, no offered cars, no Team tab", "My jobs" in ivy.inner_text("#view") and "Offered to you" not in ivy.inner_text("#view") and ivy.locator(".areabar a[href='#/garage/team']").count() == 0)
    go(ivy, "#/garage/team"); ivy.wait_for_timeout(700); check("inspector can't open the team list", "Only the garage owner" in ivy.inner_text("#view"), ivy.inner_text("#view")[:200])
    go(adm, "#/admin/team"); adm.wait_for_timeout(900)
    check("admin sees the Saaz team page", "Saaz team" in adm.inner_text("#view") and "admin@saaz.test" in adm.inner_text("#view") and adm.locator("#sf").count() == 1)
    # Ordinary seller and buyer: no Admin panel; admin pages and functions closed to them
    sel.click("#acct summary"); check("ordinary seller: no Admin panel in the menu", sel.locator(".acctmenu .adminentry").count() == 0); sel.click("#acct summary")
    go(sel, "#/admin/verify"); check("ordinary seller: admin check page looks missing", "Page not found" in sel.inner_text("#view"))
    go(sel, "#/admin/cars"); check("ordinary seller: admin pages look missing", "Page not found" in sel.inner_text("#view"))
    r = sel.evaluate("() => Saaz.rpc('admin_set_setting', {p_key: 'garage_response', p_value: '1 day'}).then(() => 'ok', e => e.message)")
    check("ordinary seller: admin function refused by the database", r == "Admins only.", r)
    go(buy, "#/browse"); buy.click("#acct summary"); check("buyer: no Admin panel in the menu", buy.locator(".acctmenu .adminentry").count() == 0); buy.click("#acct summary")
    # Staying in Admin: the admin decides when to leave; the marketplace can be viewed without leaving
    go(adm, "#/admin")
    check("Admin bar: view the marketplace, or leave Admin", adm.locator(".areabar a", has_text="View marketplace as admin").count() == 1 and adm.locator("#leaveadmin2").count() == 1)
    adm.locator(".areabar a", has_text="View marketplace as admin").click(); adm.wait_for_timeout(1300)
    check("viewing the marketplace keeps Admin: a bar back to Admin", "#/browse" in adm.url and "Viewing the marketplace as admin" in adm.inner_text(".areabar") and adm.locator(".areabar a[href='#/admin']").count() == 1)
    adm.click("#acct summary"); check("the menu still shows Admin as the current area", "you're here" in adm.locator(".acctmenu a[data-mode=admin]").inner_text()); adm.click("#acct summary")
    views_before = sql("select count(*) from listing_views")[0][0]
    car_ref, car_status = sql("select ref, status from listings order by created_at limit 1")[0]
    sql("update listings set status='live' where ref=%s", (car_ref,))  # live for this check, so a buyer's look would count
    adm.evaluate("(h) => { location.hash = h; }", "#/car/" + car_ref); adm.wait_for_timeout(1500)  # inside the app, as a click would
    check("a car viewed as admin: a link to manage it, offers and saves off", adm.locator(".areabar a", has_text="Manage this car").count() == 1 and "offers and saves are off" in adm.inner_text("#view")
          and adm.locator("#offer").count() == 0 and adm.locator("#save").count() == 0)
    check("Saaz staff looking at a car is not counted as demand", sql("select count(*) from listing_views")[0][0] == views_before)
    sql("update listings set status=%s where ref=%s", (car_status, car_ref))
    adm.locator(".areabar a", has_text="Back to Admin").click(); adm.wait_for_timeout(1300)
    check("Back to Admin returns to the overview", adm.url.endswith("#/admin") and adm.locator(".adminside").count() == 1)
    go(adm, "#/admin/no-such-page")
    check("a missing Admin page keeps the Admin menu", "Page not found" in adm.inner_text("#view") and adm.locator(".adminside, .adminjump").count() >= 1)
    go(adm, "#/admin/reports/inventory?range=custom&from=2026-10-10&to=2026-10-01")
    check("a report that fails keeps the reports menu and the way back to Admin", "Couldn't load this page" in adm.inner_text("#view") and adm.locator(".adminside a[href='#/admin'], .adminjump option[value='#/admin']").count() >= 1, adm.inner_text("#view")[:200])
    go(adm, "#/admin"); adm.click("#leaveadmin2"); adm.wait_for_timeout(1300)
    check("Leave Admin goes to the marketplace with no Admin bar", "#/browse" in adm.url and adm.locator(".areabar").count() == 0)
    adm.click("#acct summary"); adm.locator(".acctmenu a[data-mode=admin]").click(); adm.wait_for_timeout(1300)
    check("back into Admin from the menu while the admin session lasts", adm.url.endswith("#/admin") and adm.locator(".adminside").count() == 1)

    # Sign-out, every role: straight to the public listings, session gone, protected pages and functions closed
    for name_, pg_, email_, protected in [("buyer", buy, "bob@x.test", "#/offers"), ("seller", sel, "sam@x.test", "#/my/cars"), ("garage", gar, "gus@garage.test", "#/garage"), ("admin", adm, "admin@saaz.test", "#/admin")]:
        go(pg_, "#/account"); pg_.evaluate("(h) => { location.hash = h; }", protected); pg_.wait_for_timeout(900)  # two signed-in pages in this tab's history
        tok = pg_.evaluate("() => Saaz.state.session && Saaz.state.session.access_token")
        pg_.click("#acct summary"); pg_.click("#signout"); pg_.wait_for_timeout(1500)
        check(f"{name_}: sign-out lands on the public listings", pg_.url.rstrip("/") + "/" == APP or pg_.url.startswith(APP + "#/browse"), pg_.url)
        check(f"{name_}: no sign-in page after sign-out", "#/signin" not in pg_.url and "Latest inspected" in pg_.inner_text("#view"), pg_.inner_text("#view")[:120])
        check(f"{name_}: signed out in the header", pg_.locator("#acct").count() == 0 and pg_.locator(".appright a[href='#/signin']").count() == 1)
        check(f"{name_}: every session of the account ended", sql("select count(*) from auth.sessions s join auth.users u on u.id=s.user_id where u.email=%s", (email_,))[0][0] == 0)
        pg_.go_back(); pg_.wait_for_timeout(900)
        txt = pg_.inner_text("#view"); check(f"{name_}: browser Back to a protected page shows no content", "Sign in to see this page" in txt and "#/account" in pg_.url, pg_.url + " " + txt[:160])
        r = pg_.evaluate("(t) => fetch('http://127.0.0.1:54321/rest/v1/rpc/update_profile', {method:'POST', headers:{'Content-Type':'application/json', apikey:'LOCALANON', Authorization:'Bearer '+t}, body: JSON.stringify({p_name:'X Y', p_country:'UG', p_mobile:''})}).then(r => r.json()).then(j => j.message || 'ok')", tok)
        check(f"{name_}: the old token is refused by the database", "session ended" in r, r)
    check("no script errors", not errors, errors[:5])
    br.close()
print(f"\n{ok} passed, {bad} failed")
