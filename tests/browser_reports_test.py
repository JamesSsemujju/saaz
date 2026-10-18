"""Browser test for Admin > Reports (slice 1) on the local stack, at one width.
Usage: python3 tests/browser_reports_test.py <site url> <width>
Needs the data from tests/db_reports_test.py (run it on a fresh database first; this test does not change report data)."""
import sys, os, re, csv, io, json, time, base64, hashlib, hmac, struct, psycopg2
from playwright.sync_api import sync_playwright
SITE, W = sys.argv[1], int(sys.argv[2])
db = psycopg2.connect(host="/var/tmp/saazpg", port=5433, user="postgres", dbname="sb"); db.autocommit = True; cur = db.cursor()
def sql(q, a=()): cur.execute(q, a or None); return cur.fetchall() if cur.description else None
SECRET = "JBSWY3DPEHPK3PXP"
sql("update auth.mfa_factors set secret=%s where user_id=(select id from auth.users where email='admin@saaz.test')", (SECRET,))
def totp(secret):
    k = base64.b32decode(secret); h = hmac.new(k, struct.pack(">Q", int(time.time()) // 30), hashlib.sha1).digest(); o = h[-1] & 15
    return "%06d" % ((struct.unpack(">I", h[o:o + 4])[0] & 0x7fffffff) % 1000000)
ok = bad = 0
def check(n, c, x=""):
    global ok, bad
    if c: ok += 1; print("PASS", f"{n} @{W}")
    else: bad += 1; print("FAIL", f"{n} @{W}", str(x)[:300])
errors = []
with sync_playwright() as p:
    br = p.chromium.launch()
    def page():
        ctx = br.new_context(viewport={"width": W, "height": 800 if W >= 768 else 760}, accept_downloads=True); pg = ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(str(e)))
        return pg
    def go(pg, h): pg.goto("about:blank"); pg.goto(SITE + h); pg.wait_for_timeout(1200)
    def signin(pg, email):
        go(pg, "#/signin"); pg.check("input[name=as][value=seller]"); pg.fill("input[name=email]", email); pg.fill("input[name=password]", "demo1234"); pg.click("form button"); pg.wait_for_timeout(1500)
    def sideways(pg): return pg.evaluate("() => document.documentElement.scrollWidth > innerWidth + 1")

    sel = page(); signin(sel, "s1@x.test"); go(sel, "#/admin/reports/inventory")
    check("a seller gets Page not found for reports", "Page not found" in sel.inner_text("#view"))
    adm = page(); signin(adm, "admin@saaz.test"); go(adm, "#/admin/reports/inventory")
    check("reports are hidden until the admin passes the authenticator", "Page not found" in adm.inner_text("#view"))
    go(adm, "#/admin/verify"); adm.fill("input[name=password]", "demo1234"); adm.click("#pf button"); adm.wait_for_timeout(1200)
    adm.fill("input[name=code]", totp(SECRET)); adm.click("#cf button"); adm.wait_for_timeout(1800)
    go(adm, "#/admin")
    nav = adm.inner_text(".adminside") if W >= 1024 else adm.inner_text(".adminjump")
    check("Reports is one item in the admin navigation", "Reports" in nav, nav)
    go(adm, "#/admin/reports"); adm.wait_for_timeout(800)
    check("Reports opens Inventory", "#/admin/reports/inventory" in adm.url, adm.url)
    check("the heading is the question", adm.inner_text("main h1") == "What is on the site right now, and is it healthy?", adm.inner_text("main h1"))
    check("the time zone is stated on screen", "East Africa Time" in adm.inner_text(".sechead"))
    if W >= 1024:
        check("the left rail lists the reports in order, then the glossary", [x.strip() for x in adm.locator(".adminside a").all_inner_texts()] == ["‹ Admin", "Inventory", "Listing funnel", "Glossary"], adm.locator(".adminside a").all_inner_texts())
    tiles = {t.split("\n")[1]: t.split("\n")[0] for t in adm.locator(".rkpis a").all_inner_texts()}
    check("key numbers: live now 3, pending 1, stale 2, no photos 1", tiles.get("Live now") == "3" and tiles.get("Pending now") == "1" and tiles.get("Not updated in 30 days") == "2" and tiles.get("No photos") == "1", tiles)
    check("each key number shows its definition", "buyers can see right now" in (adm.locator(".rkpis a", has_text="Live now").get_attribute("title") or ""))
    adm.locator(".rkpis a", has_text="Live now").click(); adm.wait_for_timeout(1200)
    check("a key number opens its rows (3 live)", adm.locator(".rtable tbody tr").count() == 3 and "Showing: Live now" in " ".join(adm.inner_text(".rdrill").split()), adm.inner_text(".rtable")[:200])
    check("the drilled rows link to the car", adm.locator(".rtable tbody tr a[href^='#/admin/car/']").count() == 3)
    adm.click(".rdrill a"); adm.wait_for_timeout(1000)
    adm.select_option("#rgroup", "make"); adm.wait_for_timeout(1200)
    cells = adm.locator(".rtable tbody tr").all_inner_texts()
    check("group by make: Toyota 5", any(re.search(r"Toyota\s+5", c) for c in cells), cells)
    adm.locator(".rtable tbody tr", has_text="Toyota").locator("a").click(); adm.wait_for_timeout(1200)
    check("a group count opens the same number of rows", adm.locator(".rtable tbody tr").count() == 5 and "make=Toyota" in adm.url, adm.url)
    def sort_by(label, col, desc):
        if W >= 768: adm.locator(".rtable thead a", has_text=label).first.click()
        else: adm.select_option("#rsort", f"{col}:{1 if desc else 0}")
        adm.wait_for_timeout(1200)
    sort_by("Price", "price", True)
    first = adm.locator(".rtable tbody tr").first.inner_text(); sort_by("Price", "price", False)
    first2 = adm.locator(".rtable tbody tr").first.inner_text()
    check("column headers sort both ways", "45,000,000" in first and "30,000,000" in first2, (first, first2))
    before = sql("select count(*) from audit_log where action='report exported'")[0][0]
    with adm.expect_download() as d: adm.click("#rexport")
    dl = d.value; name = dl.suggested_filename; path = dl.path(); txt = open(path, encoding="utf-8-sig").read()
    lines = list(csv.reader(io.StringIO(txt)))
    check("export file name has the report, period and filters", re.fullmatch(r"Saaz_Inventory_\d{4}-\d\d-\d\d_to_\d{4}-\d\d-\d\d_make-Toyota\.csv", name) is not None, name)
    check("export first row states the period and the filters", lines[0][1].startswith("Period ") and "East Africa Time" in lines[0][1] and "Make=Toyota" in lines[0][2], lines[0])
    ui_cols = [re.sub(r" [▲▼]$", "", x.strip()) for x in adm.locator(".rtable thead th").all_text_contents()] if W >= 768 else None
    check("export columns use the same names as the screen", lines[1][0] == "Ref" and (ui_cols is None or lines[1] == ui_cols), (lines[1], ui_cols))
    check("export has every row behind the view (5)", len(lines) - 2 == 5, len(lines))
    adm.wait_for_timeout(500)
    check("the export is recorded with who and what", sql("select count(*) from audit_log where action='report exported'")[0][0] == before + 1 and
          sql("select detail->'filters'->>'make', actor_id = (select id from auth.users where email='admin@saaz.test') from audit_log where action='report exported' order by id desc limit 1")[0] == ("Toyota", True))
    # filters persist between reports
    if W >= 1024: adm.locator(".adminside a", has_text="Listing funnel").click()
    else: adm.select_option(".adminjump select", label="Listing funnel")
    adm.wait_for_timeout(1500)
    check("filters follow you to the next report", "#/admin/reports/funnel" in adm.url and "make=Toyota" in adm.url and adm.locator("#rbar select[name=make]").input_value() == "Toyota", adm.url)
    check("funnel heading is its question", adm.inner_text("main h1") == "Do listings get seen and acted on?")
    check("funnel shows two trend charts, one measure each", adm.locator(".rchart svg").count() == 2)
    adm.check("#rbar input[name=cmp]"); adm.select_option("#rbar select[name=range]", "7"); adm.click("#rbar button"); adm.wait_for_timeout(1500)
    check("compare: previous period line and legend", adm.locator(".rchart path.prev").count() == 2 and adm.locator(".rlegend").count() == 2)
    ft = {t.split("\n")[1]: t for t in adm.locator(".rkpis a").all_inner_texts()}
    check("funnel key numbers for Toyota, 7 days: views 18, enquiries 2", ft["Views"].startswith("18") and ft["Enquiries"].startswith("2") and "Previous" in ft["Views"], ft)
    sort_by("Enquiry rate", "enquiry_rate", True)
    check("top performers: sort by enquiry rate", "Enquiry rate" in adm.locator(".rtable thead th[aria-sort]").text_content() and "sort=enquiry_rate" in adm.url)
    check("the reason is visible on a weak listing", "above similar cars" in adm.inner_text(".rtable"))
    go(adm, "#/admin/reports/funnel?range=custom&from=2020-01-01&to=2020-01-07")
    check("empty state says what it means", "No views in this period." in adm.inner_text("#view"), adm.inner_text("#view")[:400])
    go(adm, "#/admin/reports/glossary")
    check("glossary defines the numbers", "Enquiry rate" in adm.inner_text(".rgloss") and "per 100 views" in adm.inner_text(".rgloss"))
    go(adm, "#/admin/reports/inventory?range=30")
    check("no sideways scroll", not sideways(adm))
    if W < 768:
        check("phones: table rows are cards with labels", adm.evaluate("() => getComputedStyle(document.querySelector('.rtable tbody tr')).display") == "block" and
              adm.evaluate("() => getComputedStyle(document.querySelector('.rtable td'), '::before').content").strip('"') == "Ref")
        check("phones: charts fit the screen", (go(adm, "#/admin/reports/funnel?range=30") or True) and adm.evaluate("() => document.querySelector('.rchart svg').getBoundingClientRect().right <= innerWidth"))
    go(adm, "#/admin/cars"); check("existing admin pages still work", "Cars with a Saaz inspection" in adm.inner_text("#view"))
    SHOTS = os.environ.get("SHOTS", "."); os.makedirs(SHOTS, exist_ok=True)
    for h, n in [("#/admin/reports/inventory?range=30", "inventory"), ("#/admin/reports/funnel?range=30&cmp=1", "funnel")]:
        go(adm, h); adm.screenshot(path=f"{SHOTS}/{n}_{W}.png", full_page=True)
    check("no script errors", not errors, errors[:3])
    br.close()
print(f"\n{ok} passed, {bad} failed")
