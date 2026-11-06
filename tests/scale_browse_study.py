"""Scale study (5 Nov 2026): how Buy cars, the home page and Admin, Cars behave as the number of live cars grows.
Usage: SAAZ_TEST=<stack folder> python3 tests/scale_browse_study.py <site url> [sizes]   (fresh database; adds its own cars)
sizes default to 24,100,500,1000,2500,5000,10000 and grow in steps (each step adds cars to the last).
For each size: database time and size of the car list, then a phone (390 px, CPU slowed 4x, a 4G-like link) and a laptop
(1280 px, no slowdown) open the home page, Buy cars, the last page and a make filter. phone_4g sends the list uncompressed over the slowed link (the local stack does not compress), so it is the worst case;
phone_cpu is the same phone with no network limit. Prints one line per size; writes
scale_results.json next to this file. Changes nothing outside the local test database."""
import sys, os, json, time, gzip, urllib.request, psycopg2
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import admin_session
SITE = sys.argv[1]
SIZES = [int(x) for x in (sys.argv[2] if len(sys.argv) > 2 else "24,100,500,1000,2500,5000,10000").split(",")]
STORE = os.path.join(os.environ["SAAZ_TEST"], "storage", "car-photos", "s"); os.makedirs(STORE, exist_ok=True)
db = psycopg2.connect(host="/var/tmp/saazpg", port=5433, user="postgres", dbname="sb"); db.autocommit = True; cur = db.cursor()
def sql(q, a=()): cur.execute(q, a or None); return cur.fetchall() if cur.description else None

# One seller, one admin, eight photos (all cars share them: the study is about counts, not pictures)
SEL = sql("insert into auth.users (email, raw_user_meta_data) values ('scale-seller@x.test','{\"name\":\"Scale Seller\",\"country\":\"UG\"}') returning id")[0][0]
ADM = sql("insert into auth.users (email, raw_user_meta_data) values ('scale-admin@x.test','{\"name\":\"Scale Admin\",\"country\":\"UG\"}') returning id")[0][0]
sql("insert into admins (user_id, name, role) values (%s,'Scale Admin','admin')", (ADM,))
for i in range(8):
    im = Image.new("RGB", (960, 720), (150 + i * 10, 180, 200)); d = ImageDraw.Draw(im)
    d.rectangle([0, 450, 960, 720], fill=(110, 110, 105)); d.rectangle([150, 360, 810, 560], fill=(40 + i * 25, 30, 30))
    im.save(os.path.join(STORE, "p%d.webp" % i), "WEBP", quality=75)

MAKES = "{Toyota,Subaru,Honda,Nissan,Mazda,Mitsubishi,Mercedes-Benz,Isuzu}"
BODIES = "{Saloon,SUV,Hatchback,Pickup,Van,Wagon}"
REGIONS = "{Kampala,Wakiso,Mukono,Entebbe,Jinja,Mbarara}"
def grow(to):
    have = sql("select count(*) from listings")[0][0]
    if to <= have: return
    sql("""insert into vehicles (vin, make, model)
           select 'SCALE' || lpad(g::text, 12, '0'), (%s::text[])[1 + g %% 8], 'Model ' || (g %% 12) from generate_series(%s, %s) g""", (MAKES, have, to - 1))
    sql("""insert into listings (vehicle_id, seller_id, country, region, status, make, model, year, fuel, gearbox, body, colour, engine, mileage, plate,
             currency, price, description, photos, logbook_name_matches, owner_authorised, live_at)
           select v.id, %s, 'UG', (%s::text[])[1 + g %% 6], 'live', v.make, v.model, 2008 + g %% 15, 'Petrol', 'Automatic', (%s::text[])[1 + g %% 6], 'White', '1.8',
             40000 + (g * 7919) %% 160000, 'UZZ ' || lpad(g::text, 6, '0'), 'UGX', 15000000 + ((g * 104729) %% 236) * 1000000,
             'Clean car, one owner, full service history at the dealer. Inspected by a Saaz garage.', array['s/p' || (g %% 8) || '.webp'], true, true,
             now() - make_interval(mins => g)
           from generate_series(%s, %s) g join vehicles v on v.vin = 'SCALE' || lpad(g::text, 12, '0')""", (SEL, REGIONS, BODIES, have, to - 1))
    # Real traffic: about 12 people looked at each car in the last week
    sql("""insert into listing_views (listing_id, viewer, day)
           select l.id, 'v' || n, current_date - (n %% 7) from listings l, generate_series(1, 12) n
           where l.vehicle_id in (select id from vehicles where vin >= 'SCALE' || lpad(%s::text, 12, '0')) on conflict do nothing""", (have,))
    sql("analyze listings; analyze listing_views")

def anon_list():
    req = urllib.request.Request("http://127.0.0.1:54330/rpc/browse_listings", data=b'{"p_country":"UG"}',
                                 headers={"Content-Type": "application/json", "Accept": "application/json"})
    t = time.time(); body = urllib.request.urlopen(req, timeout=120).read(); ms = (time.time() - t) * 1000
    return ms, len(body), len(gzip.compress(body, 6)), len(json.loads(body))
def admin_count():
    c = admin_session.claims(cur, ADM); cur.execute("select set_config('request.jwt.claims', %s, false)", (c,))
    cur.execute("set role authenticated"); n = sql("select count(*) from admin_listings('')")[0][0]; cur.execute("reset role"); return n

FAST4G = {"offline": False, "latency": 150, "downloadThroughput": 1_600_000 / 8 * 4, "uploadThroughput": 750_000 / 8}   # about 6.4 Mbit/s down
READY = "() => { const v = document.querySelector('#view'), g = document.querySelector('[data-ref=results-grid]'); return v && !v.classList.contains('is-busy') && g && !g.dataset.stale && g.querySelector('.car'); }"
def measure(b, prof, n):
    w = 1280 if prof == "laptop" else 390
    ctx = b.new_context(viewport={"width": w, "height": 900 if w == 1280 else 844}); p = ctx.new_page(); errs = []
    p.on("pageerror", lambda e: errs.append(str(e)))
    def slow(pg):
        c = ctx.new_cdp_session(pg); c.send("Performance.enable")
        if prof != "laptop": c.send("Emulation.setCPUThrottlingRate", {"rate": 4})
        if prof == "phone_4g": c.send("Network.enable"); c.send("Network.emulateNetworkConditions", FAST4G)
        return c
    cdp = slow(p); out = {}
    def stale(): p.evaluate("document.querySelectorAll('[data-ref=results-grid]').forEach(g => g.dataset.stale = 1)")
    def ready(t): p.wait_for_function(READY, timeout=180000); return round((time.time() - t) * 1000)
    t = time.time(); p.goto(SITE + "#/"); p.wait_for_selector("[data-ref=latest-cars] .car", timeout=180000); out["home_ms"] = round((time.time() - t) * 1000)
    out["home_button"] = p.inner_text("#hs .go")
    t = time.time(); p.click("[data-ref=latest-cars] a[href='#/browse']"); out["browse_ms"] = ready(t)          # Buy cars from the home page (list already loaded)
    q = ctx.new_page(); slow(q); t = time.time(); q.goto(SITE + "#/browse"); q.wait_for_function(READY, timeout=180000)
    out["browse_cold_ms"] = round((time.time() - t) * 1000); q.close()                              # a Buy cars link opened from WhatsApp
    out["count"] = p.inner_text(".count")
    m = {x["name"]: x["value"] for x in cdp.send("Performance.getMetrics")["metrics"]}
    out["heap_mb"] = round(m.get("JSHeapUsedSize", 0) / 1e6, 1); out["dom_nodes"] = int(m.get("Nodes", 0))
    out["pager_items"] = p.locator("[data-ref=pager] a, [data-ref=pager] span").count()
    out["sideways"] = p.evaluate("document.documentElement.scrollWidth > innerWidth + 1")
    last = max(1, -(-n // 24))
    stale(); t = time.time(); p.goto(SITE + "#/browse?page=%d" % last); out["last_ms"] = ready(t)
    out["last_cards"] = p.locator("[data-ref=results-grid] .car").count(); out["last_label"] = p.inner_text(".count")
    stale(); t = time.time(); p.select_option("#flt select[name=make]", "Toyota"); p.click("#flt .go"); out["filter_ms"] = ready(t); out["filter_count"] = p.inner_text(".count")
    # Back from a car after the list is older than 20 seconds (it is fetched again): the old list shows at once, greyed, then the fresh one
    p.goto(SITE + "#/browse"); p.wait_for_function(READY, timeout=180000)
    p.evaluate("window.scrollTo({top: 1200, behavior: 'instant'})"); time.sleep(0.3); y0 = p.evaluate("scrollY")
    p.evaluate("[...document.querySelectorAll('[data-ref=results-grid] .car')].find(c => c.getBoundingClientRect().top > 60).click()")
    p.wait_for_url("**#/car/**"); p.wait_for_selector("[data-ref=results-grid]", state="detached", timeout=180000); time.sleep(0.3)
    p.evaluate("Saaz._rc = {}")
    t = time.time(); p.go_back(); p.wait_for_selector("[data-ref=results-grid] .car", timeout=180000); out["back_seen_ms"] = round((time.time() - t) * 1000)
    out["back_ready_ms"] = ready(t); time.sleep(0.4); y1 = p.evaluate("scrollY"); out["back_spot"] = [round(y0), round(y1)]
    if n in (1000, 10000) and prof == "phone_4g": p.screenshot(path=os.path.join(os.environ.get("SHOTS", "/tmp"), "scale_%d_phone.png" % n))
    out["errors"] = errs[:3]
    ctx.close(); return out

rows = []
with sync_playwright() as pw:
    b = pw.chromium.launch()
    for n in SIZES:
        grow(n)
        ms, raw, gz, got = anon_list()
        db_ms = sql("select extract(milliseconds from clock_timestamp() - now()) from (select count(*) from browse_listings('UG')) x")[0][0]
        r = {"cars": n, "api_ms": round(ms), "db_ms": round(float(db_ms)), "raw_kb": raw // 1024, "gzip_kb": gz // 1024, "returned": got, "admin_cars": admin_count()}
        for prof in ("phone_4g", "phone_cpu", "laptop"): r[prof] = measure(b, prof, n)
        rows.append(r); print(json.dumps(r), flush=True)
    b.close()
json.dump(rows, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "scale_results.json"), "w"), indent=1)
