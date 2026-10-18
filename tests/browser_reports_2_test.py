"""Browser test for Admin > Reports: Inspections and garages, Deals and sales, on the local stack at one width.
Usage: python3 tests/browser_reports_2_test.py <site url> <width>
Needs the data from tests/db_reports_2_test.py (run it on a fresh database first)."""
import sys, os, re, csv, io, time, base64, hashlib, hmac, struct, psycopg2
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
def tiles(pg): return {t.split("\n")[1]: t.split("\n")[0] for t in pg.locator(".rkpis a").all_inner_texts()}
with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={"width": W, "height": 800 if W >= 768 else 760}, accept_downloads=True); adm = ctx.new_page()
    adm.on("pageerror", lambda e: errors.append(str(e)))
    def go(h): adm.goto("about:blank"); adm.goto(SITE + h); adm.wait_for_timeout(1300)
    go("#/signin"); adm.check("input[name=as][value=seller]"); adm.fill("input[name=email]", "admin@saaz.test"); adm.fill("input[name=password]", "demo1234"); adm.click("form button"); adm.wait_for_timeout(1500)
    go("#/admin/verify"); adm.fill("input[name=password]", "demo1234"); adm.click("#pf button"); adm.wait_for_timeout(1200)
    adm.fill("input[name=code]", totp(SECRET)); adm.click("#cf button"); adm.wait_for_timeout(1800)

    go("#/admin/reports/inspections?range=7")
    check("inspections: the heading is the question", adm.inner_text("main h1") == "Are cars inspected quickly, and which garages need attention?")
    t = tiles(adm)
    check("inspections key numbers: requested 3, issued 3, open 2, waiting 1, time-outs 1, time-out rate 50%",
          (t.get("Requested"), t.get("Issued"), t.get("Open now"), t.get("Waiting over 7 days"), t.get("Time-outs"), t.get("Time-out rate")) == ("3", "3", "2", "1", "1", "50%"), t)
    check("inspections trend: requested and issued, one chart each", adm.locator(".rchart").count() == 2 and "Inspections requested per day" in adm.inner_text(".rtrend"))
    adm.select_option("#rgroup", "garage"); adm.wait_for_timeout(1300)
    rowtxt = adm.locator(".rtable tbody tr", has_text="Ntinda Motors").inner_text()
    check("by garage: Ntinda's row shows its numbers", "Ntinda Motors" in rowtxt and "5" in rowtxt, rowtxt)
    cells = adm.locator(".rtable tbody tr", has_text="Ntinda Motors").locator("td")
    issued_cell = [i for i in range(cells.count()) if cells.nth(i).get_attribute("data-label") == "Issued"][0]
    cells.nth(issued_cell).locator("a").click(); adm.wait_for_timeout(1300)
    check("a garage's issued count opens its 2 inspections", adm.locator(".rtable tbody tr").count() == 2 and "garage=" in adm.url and "flag=issued" in adm.url, adm.url)
    go("#/admin/reports/inspections?range=7")
    adm.locator(".rkpis a", has_text="Time-outs").first.click(); adm.wait_for_timeout(1300)
    check("time-outs open the garage line turns", adm.locator(".rtable tbody tr").count() == 1 and "1 garage line turn" in adm.inner_text(".rtable .count"), adm.inner_text(".rtable")[:200])
    adm.locator(".rtable tbody a").first.click(); adm.wait_for_timeout(1500)
    check("a row opens the car's admin page", "#/admin/car/" in adm.url)

    go("#/admin/reports/deals?range=7")
    check("deals: the heading is the question", adm.inner_text("main h1") == "Do offers become sales, and how far below asking do they agree?")
    t = tiles(adm)
    check("deals key numbers: offers 4, agreed 2, completed 1, 50% to agreement, median gap 6.3%", (t.get("Offers"), t.get("Agreed"), t.get("Completed"), t.get("Offer to agreement"), t.get("Median gap")) == ("4", "2", "1", "50%", "6.3%"), t)
    adm.select_option("#rgroup", "model"); adm.wait_for_timeout(1300)
    pr = adm.locator(".rtable tbody tr", has_text="Toyota Premio").inner_text()
    check("what Saaz has learned: Toyota Premio, 4 deals, median 7.3%, quarters 6.5% to 8.1%", all(x in pr for x in ["4", "7.3%", "6.5%", "8.1%"]), pr)
    with adm.expect_download() as d: adm.click("#rexport")
    dl = d.value; lines = list(csv.reader(io.StringIO(open(dl.path(), encoding="utf-8-sig").read())))
    check("grouped export: file name and the learned columns", re.fullmatch(r"Saaz_DealsAndSales_\d{4}-\d\d-\d\d_to_\d{4}-\d\d-\d\d_by-model\.csv", dl.suggested_filename) is not None and lines[1][:3] == ["Model", "Agreed deals", "Median gap"], (dl.suggested_filename, lines[1]))
    check("grouped export rows match the screen", any(r[0] == "Toyota Premio" and r[1] == "4" and r[2] == "7.3%" for r in lines[2:]), lines[2:])
    go("#/admin/reports/deals?range=7")
    adm.locator("a", has_text="Expected prices for cars on sale").click(); adm.wait_for_timeout(1300)
    h = adm.locator(".rtable tbody tr", has_text="Honda Fit").inner_text()
    check("cars on sale get an expected agreed price from the learning (Honda: UGX 23,300,000, all cars, 5 deals)", "23,300,000" in h and "All cars, 5 deals" in h, h)
    adm.locator(".rkpis a", has_text="Agreed").first.click(); adm.wait_for_timeout(1300)
    rows = adm.locator(".rtable tbody tr").all_inner_texts()
    check("agreed deals show the usual gap and how this one compares", any("Toyota Premio, 4 deals" in r and "+0.2 points" in r for r in rows), rows)
    # filters follow you between reports
    go("#/admin/reports/deals?range=30"); adm.select_option("#rbar select[name=make]", "Toyota"); adm.click("#rbar button"); adm.wait_for_timeout(1300)
    if W >= 1024: adm.locator(".adminside a", has_text="Inventory").click()
    else: adm.select_option(".adminjump select", label="Inventory")
    adm.wait_for_timeout(1500)
    check("a make chosen on Deals is still chosen on Inventory", "make=Toyota" in adm.url and adm.locator("#rbar select[name=make]").input_value() == "Toyota", adm.url)
    go("#/admin/reports/inspections?range=custom&from=2020-01-01&to=2020-01-07")
    check("empty state says what it means", "No inspections requested in this period." in adm.inner_text("#view"), adm.inner_text("#view")[:300])
    go("#/admin/reports/deals?range=30")
    check("no sideways scroll", not adm.evaluate("() => document.documentElement.scrollWidth > innerWidth + 1"))
    if W < 768: check("phones: rows are labelled cards", adm.evaluate("() => getComputedStyle(document.querySelector('.rtable tbody tr')).display") == "block")
    SH = os.environ.get("SHOTS", "."); os.makedirs(SH, exist_ok=True)
    for h2, n in [("#/admin/reports/inspections?range=30&group=garage", "inspections"), ("#/admin/reports/deals?range=30&group=model", "deals")]:
        go(h2); adm.screenshot(path=f"{SH}/{n}_{W}.png", full_page=True)
    check("no script errors", not errors, errors[:3])
    br.close()
print(f"\n{ok} passed, {bad} failed")
