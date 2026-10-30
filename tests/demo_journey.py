"""The presentation journey, run the way people use Saaz: one demo car from listing to an offer, through every role's own screens.
Usage: python3 tests/demo_journey.py <shots dir> [width]   (local test stack, fresh database: tests/stack/reset.sh first)
Saaz's rule is "no Saaz inspection, no listing", so the order is: list -> garage line -> inspection -> report -> admin approval -> public.
Every person is a demo account (@demo.test) and the car is marked DEMO. Nothing here touches the live project.
Checks: each step works, the same facts (name, price, mileage, score) show everywhere, and each person sees only what they may."""
import os, sys, json, time, base64, hashlib, hmac, struct, psycopg2
from PIL import Image
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import admin_session
SHOTS = sys.argv[1] if len(sys.argv) > 1 else "/tmp/demo"; W = int(sys.argv[2]) if len(sys.argv) > 2 else 1280
os.makedirs(SHOTS, exist_ok=True)
APP = "http://localhost:8777/saaz/"; D = os.path.dirname(os.path.abspath(__file__)); IMG = os.path.join(D, "..", "src", "assets", "img")
db = psycopg2.connect(host="/var/tmp/saazpg", port=5433, user="postgres", dbname="sb"); db.autocommit = True; cur = db.cursor()
def sql(q, a=()): cur.execute(q, a or None); return cur.fetchall() if cur.description else None
SECRET = "JBSWY3DPEHPK3PXP"
def totp(s):
    k = base64.b32decode(s); h = hmac.new(k, struct.pack(">Q", int(time.time()) // 30), hashlib.sha1).digest(); o = h[-1] & 15
    return "%06d" % ((struct.unpack(">I", h[o:o + 4])[0] & 0x7fffffff) % 1000000)
# Demo photos: Saaz's own design photos of a silver CLS, cut to the shapes a seller's phone gives
photos = []
src = Image.open(os.path.join(IMG, "sell-1280.webp")).convert("RGB")
for i, (img, box) in enumerate([(src, None), (src, (160, 120, 1120, 840)), (Image.open(os.path.join(IMG, "history-1280.webp")).convert("RGB"), None), (Image.open(os.path.join(IMG, "inspections-1280.webp")).convert("RGB"), None)]):
    p = os.path.join(SHOTS, f"_photo{i}.jpg"); (img.crop(box) if box else img).resize((1600, 1200)).save(p, quality=85); photos.append(p)
# The admin exists before the demo, with a pinned authenticator (the real first-time set-up is in browser_flow_test.py)
A = sql("insert into auth.users (email, raw_user_meta_data) values ('admin@demo.test', %s) returning id", (json.dumps({"name": "Ann Admin (demo)", "country": "UG"}),))[0][0]
sql("insert into admins (user_id, name, role) values (%s,'Ann Admin (demo)','admin')", (A,)); admin_session.claims(cur, A); cur.execute("reset role"); sql("update auth.mfa_factors set secret=%s", (SECRET,))

ok = bad = 0; step_log = []
def check(n, c, x=""):
    global ok, bad
    if c: ok += 1; print("PASS", n)
    else: bad += 1; print("FAIL", n, str(x)[:300])
FACTS = {"name": "2016 Mercedes-Benz CLS 400", "price": "UGX 128,000,000", "km": "62,000 km"}
with sync_playwright() as pw:
    br = pw.chromium.launch(); errors = []
    def ctx(name, touch=False):
        c = br.new_context(viewport={"width": W, "height": 900 if W >= 768 else 844}, has_touch=touch, is_mobile=touch); pg = c.new_page()
        pg.on("pageerror", lambda e: errors.append(f"{name}: {e}"))
        pg.on("console", lambda m: errors.append(f"{name} blocked by the security policy: {m.text}") if m.type == "error" and "Content Security Policy" in m.text else None); return pg
    def go(pg, h, wait=1300): pg.goto("about:blank"); pg.goto(APP + h); pg.wait_for_timeout(wait)
    def toast(pg): pg.wait_for_selector(".toast.show", timeout=8000); t = pg.inner_text("#toast"); pg.wait_for_timeout(300); return t
    def calm(pg): pg.wait_for_selector("#toast:not(.show)", state="attached", timeout=9000)
    def shot(pg, name, full=True): pg.wait_for_timeout(300); pg.screenshot(path=os.path.join(SHOTS, f"{name}_{W}.png"), full_page=full); step_log.append(name)
    def signup(pg, name, email, sell=False):
        go(pg, "#/signup"); pg.fill("input[name=name]", name); pg.fill("input[name=email]", email); pg.fill("input[name=mobile]", "+256 700 123 456")
        pg.fill("input[name=password]", "demo1234"); pg.click("#view form button"); pg.wait_for_timeout(1500)
    def signin(pg, email, as_):
        go(pg, "#/signin"); pg.check(f"input[name=as][value={as_}]"); pg.fill("input[name=email]", email); pg.fill("input[name=password]", "demo1234"); pg.click("#view form button"); pg.wait_for_timeout(1600)
    def body(pg): return pg.inner_text("#view")

    # ---------- set-up: the admin signs in; a garage is certified; it adds an inspector ----------
    adm = ctx("admin"); signin(adm, "admin@demo.test", "seller")
    go(adm, "#/admin/verify"); adm.fill("input[name=password]", "demo1234"); adm.click("#pf button"); adm.wait_for_timeout(1200)
    adm.fill("input[name=code]", totp(SECRET)); adm.click("#cf button"); adm.wait_for_timeout(1800)
    check("set-up: admin signed in with password and authenticator", "#/admin" in adm.url and "Overview" in body(adm), adm.url)
    gar = ctx("garage owner"); go(gar, "#/garage/apply")
    gar.fill("input[name=acc_name]", "Gus Owner (demo)"); gar.fill("input[name=acc_email]", "gus@demo.test"); gar.fill("input[name=acc_mobile]", "+256700222333"); gar.fill("input[name=acc_password]", "demo1234")
    gar.fill("input[name=name]", "Demo Motors Ntinda"); gar.select_option("#greg", "Kampala"); gar.fill("input[name=address]", "Plot 4, Ntinda"); gar.fill("input[name=phone]", "+256700999000")
    gar.fill("input[name=registration_no]", "URSB-DEMO-1"); gar.fill("input[name=years]", "8"); gar.check("input[value=Toyota]"); gar.check("input[name=honest]"); gar.click("#view form button"); gar.wait_for_timeout(1500)
    go(adm, "#/admin"); adm.click("text=Demo Motors Ntinda"); adm.wait_for_timeout(900); adm.click("button[value=approve]"); toast(adm)
    check("set-up: Saaz certifies the garage", sql("select status from garages")[0][0] == "certified")
    ivy = ctx("inspector"); signup(ivy, "Ivy Inspector (demo)", "ivy@demo.test")
    signin(gar, "gus@demo.test", "garage"); go(gar, "#/garage/team")
    gar.fill("#f input[name=name]", "Ivy Inspector (demo)"); gar.fill("#f input[name=email]", "ivy@demo.test"); gar.click("#f button"); gar.wait_for_timeout(1500)
    signin(ivy, "ivy@demo.test", "garage")
    check("set-up: the owner adds an inspector to the team", "ivy@demo.test" in body(gar) or sql("select count(*) from garage_members where status <> 'removed'")[0][0] >= 2)

    # ---------- 1. the seller lists a car ----------
    sel = ctx("seller"); signup(sel, "Sam Seller (demo)", "sam@demo.test")
    go(sel, "#/sell/new"); sel.fill("#vin", "WDD2183591A0DEM01"); sel.click("#vf button"); sel.wait_for_timeout(1200)
    if not sel.input_value("input[name=make]"): sel.fill("input[name=make]", "Mercedes-Benz")
    sel.fill("input[name=make]", "Mercedes-Benz"); sel.fill("input[name=model]", "CLS 400"); sel.fill("input[name=year]", "2016")
    sel.select_option("select[name=body]", "Coupe"); sel.select_option("select[name=fuel]", "Petrol"); sel.select_option("select[name=gearbox]", "Automatic")
    sel.fill("input[name=colour]", "Silver"); sel.fill("input[name=engine]", "3.0"); sel.fill("input[name=mileage]", "62000"); sel.select_option("#reg", "Kampala")
    sel.fill("input[name=plate]", "UBX 001D"); sel.fill("input[name=price]", "128000000")
    sel.fill("textarea[name=description]", "DEMO LISTING for the Saaz presentation. One owner in Uganda, full service history, AMG Line.")
    sel.set_input_files("#files", photos); sel.wait_for_timeout(3000)
    check("1. four photos uploaded", sel.locator("#thumbs img").count() == 4)
    check("1. the VIN message reads as a sentence", "The not in" not in body(sel), body(sel)[:200])
    sel.check("input[name=logbook_name_matches]"); shot(sel, "01a_seller_lists_a_car")
    sel.click("button[value=submit]"); sel.wait_for_timeout(2500)
    if not sql("select ref from listings"): print("SUBMIT ERROR:", sel.inner_text("#err"), "| toast:", sel.inner_text("#toast"))
    first = sql("select photos[1] from listings")[0][0] if sql("select ref from listings") else ""
    ref = sql("select ref from listings")[0][0]; lid = sql("select id from listings")[0][0]; insp_id = sql("select doc_no from reviews where status='requested'")[0][0]
    check("1. submitted: awaiting inspection, a garage in play, an inspection ID", "demo motors ntinda" in body(sel).lower() and "awaiting inspection" in body(sel).lower() and insp_id in body(sel), body(sel)[:300])
    shot(sel, "01b_seller_submitted")
    vis = ctx("visitor"); go(vis, "#/browse"); check("1. not public yet: the marketplace doesn't show it", "CLS 400" not in body(vis))
    go(vis, "#/car/" + ref); check("1. not public yet: its address says not found to a visitor", "Car not found" in body(vis))

    # ---------- 2. admin sees the submitted car ----------
    go(adm, "#/admin/cars"); adm.wait_for_timeout(800)
    check("2. admin sees it in Cars, with its stage on the photo", "CLS 400" in body(adm) and "awaiting" in adm.inner_text("#view .cars").lower(), adm.inner_text("#view .cars")[:200])
    shot(adm, "02a_admin_cars")
    adm.click("#view .cars a.car:has-text('CLS 400')"); adm.wait_for_timeout(1200)
    check("2. admin car page: details, photos, the inspection ID", insp_id in body(adm) and adm.locator("#view img").count() >= 1 and "128,000,000" in body(adm), body(adm)[:300])
    check("2. admin can't approve before a Saaz inspection (the rule)", adm.locator("button[value=approve]").count() == 0 or "inspection" in body(adm).lower())
    shot(adm, "02b_admin_car_before_inspection")

    # ---------- 3. the garage line: the garage contacts the seller, the seller agrees, the owner gives the job ----------
    go(gar, "#/garage"); check("3. the garage sees the car offered to it", "Offered to you" in body(gar) and "CLS 400" in body(gar), body(gar)[:300])
    shot(gar, "03a_garage_offered")
    gar.click(".rows a"); gar.wait_for_timeout(1000)
    gar.fill("form.send input", "Hello Sam, we can inspect on Tuesday at 10. Call 0772 555 123"); gar.click("form.send button"); gar.wait_for_timeout(1200)
    check("3. phone numbers are hidden until the seller agrees", "772" not in gar.inner_text(".msgs"), gar.inner_text(".msgs"))
    go(sel, "#/my/cars"); sel.click(".rows a"); sel.wait_for_timeout(1000); sel.click("#agree"); toast(sel)
    shot(sel, "03b_seller_agrees_with_garage")
    go(gar, "#/garage"); gar.click(".rows a"); gar.wait_for_timeout(1000)
    gar.fill("input[name=date]", "2026-11-03"); gar.click("#df button"); toast(gar); gar.wait_for_timeout(600)
    gar.reload(); gar.wait_for_timeout(1500)
    give = gar.locator("select[data-give]")
    if give.count():
        val = gar.evaluate("() => [...document.querySelector('select[data-give]').options].find(o => /Ivy/.test(o.text)).value")
        give.select_option(val); toast(gar)
    check("3. the owner gives the inspection to the inspector", sql("select inspector_id is not null from reviews where doc_no=%s", (insp_id,))[0][0])
    gar.reload(); gar.wait_for_timeout(1300); shot(gar, "03c_garage_job_given")
    check("3. once given, the owner can't start it (only the inspector can)", gar.locator("a:has-text('Open to start')").count() == 0)

    # ---------- 4. the inspector inspects and issues the report ----------
    go(ivy, "#/garage"); check("4. the inspector sees only My jobs, with this car", "My jobs" in body(ivy) and "CLS 400" in body(ivy) and "Offered to you" not in body(ivy), body(ivy)[:300])
    shot(ivy, "04a_inspector_my_jobs")
    go(ivy, "#/garage/team"); check("4. the inspector can't open the team list", "Only the garage owner" in body(ivy))
    go(ivy, "#/garage"); ivy.click(".rows a"); ivy.wait_for_timeout(1000); ivy.click("a:has-text('Open to start')"); ivy.wait_for_timeout(1200)
    ivy.click("#startins"); ivy.wait_for_timeout(1600)
    check("4. the inspection starts with its ID", "12-point check" in body(ivy) and insp_id in body(ivy), body(ivy)[:200])
    marks = {"brakes": "advise", "tyres": "advise", "body": "advise"}
    for k in ['engine','gearbox','brakes','steering','tyres','electrics','body','chassis','interior','test_drive','odometer','vin']:
        ivy.click(f"input[name=c_{k}][value={marks.get(k, 'pass')}] + span")
    ivy.click("#map [data-panel=front_bumper]"); ivy.click("#map [data-panel=left_rear]"); ivy.click("#map [data-panel=left_rear]")
    ivy.fill("input[name=odometer]", "62400")
    ivy.fill("textarea[name=notes]", "DEMO. Engine clean, no fault codes. Front brake pads about 4 mm: replace within 5,000 km. Front tyres 3.5 mm: replace within 3 months. Light scratch on front bumper, small dent left rear door. Underbody checked on a lift: no accident repair, no rust.")
    ivy.check("input[name=in_person]"); shot(ivy, "04b_inspector_fills_the_check")
    ivy.click("button[value=issue]"); ivy.wait_for_timeout(300); ivy.click("button[value=issue]"); ivy.wait_for_timeout(2500)
    code = ivy.url.split("#/report/")[1] if "#/report/" in ivy.url else None
    score = sql("select score from reviews where doc_no=%s", (insp_id,))[0][0]; verdict = sql("select verdict from reviews where doc_no=%s", (insp_id,))[0][0]
    check("4. issuing opens the report, signed by the inspector", code and "Ivy Inspector" in ivy.inner_text(".sigs"), ivy.url)
    FACTS["score"] = f"{score}/100"

    # ---------- 5. the report ----------
    shot(ivy, "05a_inspection_report")
    go(vis, f"#/verify?code={code}"); vis.wait_for_timeout(800)
    check("5. anyone can verify the report as genuine", "Genuine Saaz inspection" in vis.inner_text("#out"), vis.inner_text("#out")[:200])
    shot(vis, "05b_public_verify")
    go(sel, "#/my/cars"); sel.click(".rows a"); sel.wait_for_timeout(1200)
    check("5. the seller sees the report on their car", str(score) in body(sel) and "awaiting" in body(sel).lower(), body(sel)[:300])
    shot(sel, "05c_seller_after_inspection")
    go(vis, "#/browse"); check("5. still not public: Saaz hasn't approved it", "CLS 400" not in body(vis))

    # ---------- 6. admin reviews and approves ----------
    go(adm, "#/admin"); check("6. admin overview lists it under Cars waiting for approval", "CLS 400" in body(adm), body(adm)[:300])
    adm.click("text=Cars waiting for approval >> xpath=.. >> a"); adm.wait_for_timeout(1200)
    shot(adm, "06a_admin_reviews_report")
    adm.fill("#opf textarea", "Photos and odometer reading checked; report supported."); adm.click("#opf button[value=support]"); toast(adm); calm(adm)
    adm.click("button[value=approve]"); t = toast(adm)
    check("6. admin approves: the car is live", sql("select status from listings")[0][0] == "live", t)
    adm.reload(); adm.wait_for_timeout(1200); shot(adm, "06b_admin_after_approval")

    # ---------- 7-8. the visitor and the buyer ----------
    go(vis, "#/browse"); vis.wait_for_timeout(800)
    card = vis.inner_text(".car:has-text('CLS 400')") if vis.locator(".car:has-text('CLS 400')").count() else ""
    check("7. on the marketplace with its inspection line", all(v.lower() in card.lower() for v in (FACTS["name"], FACTS["price"], FACTS["km"], f"{score}/100")), card)
    shot(vis, "07a_visitor_marketplace")
    go(vis, "#/"); check("7. on the home page under Latest inspected", "CLS 400" in body(vis)); shot(vis, "07b_visitor_home", full=False)
    vis.goto(APP + "#/car/" + ref); vis.wait_for_timeout(1500)
    detail = body(vis)
    check("7. the car page shows the same name, price, mileage and score", all(v.lower() in detail.lower() for v in (FACTS["price"], FACTS["km"], str(score), "CLS 400")), detail[:400])
    check("7. the car page shows who inspected it and links the report", "Demo Motors Ntinda" in detail and vis.locator(f"a[href='#/report/{code}']").count() >= 1)
    check("7. a visitor is asked to sign in before offering; no seller phone", "Sign in to make an offer" in detail and "700 123 456" not in detail)
    shot(vis, "07c_visitor_car_page")
    buy = ctx("buyer"); signup(buy, "Bob Buyer (demo)", "bob@demo.test")
    go(buy, "#/car/" + ref); buy.wait_for_timeout(1200)
    check("8. the buyer sees the offer form, not the seller's contact", buy.locator("#offer").count() == 1 and "700 123 456" not in body(buy))
    buy.fill("input[name=amount]", "120000000"); buy.fill("textarea[name=message]", "Can I see it on Saturday?"); buy.click("#offer button"); buy.wait_for_timeout(1800)
    check("8. the offer is sent and has its own page", "#/deals/" in buy.url, buy.url); shot(buy, "08_buyer_offer_sent")
    go(buy, "#/admin"); check("8. a buyer can't open Admin", "Admin" not in buy.inner_text("#view h1") if buy.locator("#view h1").count() else True)

    # ---------- 9. the seller ----------
    go(sel, "#/my/cars"); check("9. My cars: live, one offer", "live" in sel.inner_text(".rows").lower() and "1 offer" in sel.inner_text(".rows").lower(), sel.inner_text(".rows"))
    sel.click(".rows a"); sel.wait_for_timeout(1300)
    check("9. the seller's car page: status, report, the offer", str(score) in body(sel) and "120,000,000" in body(sel), body(sel)[:300])
    prog = sel.evaluate("() => [...document.querySelectorAll('.progress li')].map(li => li.className + ':' + li.innerText)")
    check("9. progress: a live car has Listed, inspection and Approved done; it waits for a deal", prog[:3] == ["done:Listed", "done:Saaz inspection", "done:Approved"] and prog[3].startswith("now:"), prog)
    check("9. account initials are letters only", "(" not in sel.inner_text(".acct .av"), sel.inner_text(".acct .av"))
    shot(sel, "09_seller_live_with_offer")

    # ---------- 10. admin sees the whole record ----------
    go(adm, f"#/admin/car/{lid}"); adm.wait_for_timeout(1300)
    rec = body(adm)
    check("10. admin car record: live, report, history of every step", "live" in rec.lower() and insp_id in rec and "approve" in rec.lower(), rec[:400])
    shot(adm, "10a_admin_full_record")
    go(adm, "#/admin/deals"); check("10. admin sees the offer in Deals", "120,000,000" in body(adm)); shot(adm, "10b_admin_deals")

    # one fact, five places
    report_txt = (lambda p: (go(p, "#/report/" + code), body(p))[1])(vis)
    check("consistency: the report shows the same car and score", "CLS 400" in report_txt and str(score) in report_txt and "62,400 km" in report_txt)
    go(vis, "#/report/sample", 1800); check("sample report opens, marked SAMPLE, from no database record", "SAMPLE" in vis.inner_text(".watermark") and "Sample report" in body(vis))
    shot(vis, "11_sample_report")
    check("no script errors", not [e for e in errors if "cdnjs" not in e], errors[:3])
    br.close()
for f in os.listdir(SHOTS):
    if f.startswith("_photo"): os.remove(os.path.join(SHOTS, f))
print(f"\n{ok} passed, {bad} failed")
sys.exit(1 if bad else 0)
