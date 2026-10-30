"""BA-0008 and BA-0009 (25 Oct 2026) on the local stack: the card grid, photo framing and the dropdowns.
Usage: SAAZ_TEST=<stack folder> python3 tests/browser_cards_test.py <site url>   (fresh database; it adds its own people and cars)
BA-0008: the grid picks its column count from the width (1 on phones, more on wider screens, never a card below the minimum),
a short list doesn't stretch its cards, rows stay equal with prices on one line, Admin, Cars fits more cars per row than before,
the home "Latest" grid shows whole rows, and each photo is framed by its real shape: near 4:3 fills the frame, portrait,
square and panorama photos are shown whole (nothing cropped, nothing stretched) over a blurred copy.
BA-0009: every dropdown has the same chevron with room of its own, text never runs under it, same height as the other fields.
Screenshots go to $SHOTS when set."""
import sys, os, json, time, datetime, base64, hashlib, hmac, struct, psycopg2
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import admin_session
from playwright.sync_api import sync_playwright
SITE = sys.argv[1]
STORE = os.path.join(os.environ.get("SAAZ_TEST", os.path.join(os.path.dirname(os.path.abspath(__file__)), "stack")), "storage", "car-photos", "t")
os.makedirs(STORE, exist_ok=True)
db = psycopg2.connect(host="/var/tmp/saazpg", port=5433, user="postgres", dbname="sb"); db.autocommit = True; cur = db.cursor()
def sql(q, a=()): cur.execute(q, a or None); return cur.fetchall() if cur.description else None
def user(e, n): return sql("insert into auth.users (email, raw_user_meta_data) values (%s,%s) returning id", (e, json.dumps({"name": n, "country": "UG"})))[0][0]
A = user("admin@saaz.test", "Ann Admin"); sql("insert into admins (user_id, name, role) values (%s,'Ann Admin','admin')", (A,))
SEL = user("seller@x.test", "Sam Seller")
SECRET = "JBSWY3DPEHPK3PXP"
admin_session.claims(cur, A); cur.execute("reset role"); sql("update auth.mfa_factors set secret=%s", (SECRET,))

# Photos of different shapes, each with a "car" (body plus two tyres) placed the way phone photos often are: low in the frame.
def photo(name, w, h):
    im = Image.new("RGB", (w, h), (170, 190, 205)); d = ImageDraw.Draw(im)
    d.rectangle([0, int(h * .62), w, h], fill=(110, 110, 105))                       # road
    cw, top = int(w * .7), int(h * .52); x0 = (w - cw) // 2
    d.rectangle([x0, top, x0 + cw, int(h * .78)], fill=(200, 30, 30))                 # body
    r = int(min(w, h) * .07)
    for cx in (x0 + cw * .22, x0 + cw * .78): d.ellipse([cx - r, int(h * .78) - r, cx + r, int(h * .78) + r], fill=(15, 15, 15))  # tyres
    im.save(os.path.join(STORE, name), "WEBP", quality=80); return "t/" + name
SHAPES = {"four3": photo("four3.webp", 960, 720), "portrait": photo("portrait.webp", 960, 1280), "wide": photo("wide.webp", 960, 540),
          "square": photo("square.webp", 960, 960), "near": photo("near.webp", 960, 760)}
MAKES = ["Toyota", "Subaru", "Honda", "Nissan", "Mazda", "Mitsubishi", "Mercedes-Benz", "Isuzu"]
def car(i, st, shape, model=None, region="Kampala"):
    vid = sql("insert into vehicles (vin, make, model) values (%s,%s,%s) returning id", ("JTCARD%011d" % i, MAKES[i % 8], model or "Model %d" % i))[0][0]
    sql("""insert into listings (vehicle_id, seller_id, country, region, status, make, model, year, fuel, gearbox, body, colour, engine, mileage, plate, currency, price,
           description, photos, logbook_name_matches, owner_authorised, live_at) values (%s,%s,'UG',%s,%s,%s,%s,2016,'Petrol','Automatic','Saloon','White','1.5',%s,%s,'UGX',%s,'Clean car',%s,true,true,%s)""",
        (vid, SEL, region, st, MAKES[i % 8], model or "Model %d" % i, 80000 + i * 1111, "UBP %03dP" % i, 25000000 + i * 3500000, [SHAPES[shape]],
         datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=i) if st == "live" else None))
order = ["four3", "portrait", "wide", "square", "near"]
car(0, "live", "four3", "CLS-Class (CLS 400) AMG Line Premium Plus", "Wakiso")    # a long name
for i in range(1, 30): car(i, "live" if i < 24 else "awaiting_approval", order[i % 5])
def totp(secret):
    k = base64.b32decode(secret); h = hmac.new(k, struct.pack(">Q", int(time.time()) // 30), hashlib.sha1).digest(); o = h[-1] & 15
    return "%06d" % ((struct.unpack(">I", h[o:o + 4])[0] & 0x7fffffff) % 1000000)
ok = bad = 0
def check(n, c, x=""):
    global ok, bad
    if c: ok += 1; print("PASS", n)
    else: bad += 1; print("FAIL", n, str(x)[:500])
errors = []
GRID = """() => { const g = document.querySelector('[data-ref=results-grid]') || document.querySelector('.cars'); if (!g) return null;
  const cards = [...g.querySelectorAll('.car')].filter(c => !c.hidden), r = c => c.getBoundingClientRect();
  const cols = getComputedStyle(g).gridTemplateColumns.split(' ').filter(Boolean).length;
  const rows = {}; cards.forEach(c => { const y = Math.round(r(c).top); (rows[y] = rows[y] || []).push(c); });
  const rowInfo = Object.values(rows).map(rs => ({ n: rs.length, h: [...new Set(rs.map(c => Math.round(r(c).height)))],
    price: [...new Set(rs.map(c => Math.round(r(c.querySelector('.car-price')).top)))] }));
  return { cols, w: Math.round(r(g).width), card: Math.round(r(cards[0]).width), minCard: Math.min(...cards.map(c => r(c).width)),
           n: cards.length, rows: rowInfo, scroll: document.documentElement.scrollWidth > innerWidth + 1,
           cardH: Math.round(r(cards[0]).height), photoH: Math.round(r(cards[0].querySelector('.car-photo')).height) }; }"""
FRAMES = """() => [...document.querySelectorAll('.car .car-photo')].filter(b => b.querySelector('img') && !b.closest('[hidden]')).map(b => {
  const i = b.querySelector('img'), br = b.getBoundingClientRect(), cs = getComputedStyle(i);
  const fit = cs.objectFit, ir = i.naturalWidth / i.naturalHeight, fr = br.width / br.height;
  // the drawn picture's box inside the frame
  let dw, dh; if (fit === 'contain') { if (ir > fr) { dw = br.width; dh = br.width / ir; } else { dh = br.height; dw = br.height * ir; } }
  else { if (ir > fr) { dh = br.height; dw = br.height * ir; } else { dw = br.width; dh = br.width / ir; } }
  const ib = i.getBoundingClientRect(), pinned = Math.abs(ib.width - br.width) < 1 && Math.abs(ib.height - br.height) < 1 && Math.abs(ib.top - br.top) < 1;
  return { src: i.getAttribute('src').split('/').pop(), pinned, boxH: Math.round(ib.height), frameH: Math.round(br.height), whole: b.classList.contains('whole'), fit, ir: +ir.toFixed(3), fr: +fr.toFixed(3),
           cropY: +Math.max(0, 1 - br.height / dh).toFixed(3), cropX: +Math.max(0, 1 - br.width / dw).toFixed(3),
           stretched: Math.abs((dw / dh) - ir) > 0.01, bg: getComputedStyle(b, '::before').backgroundImage !== 'none' && b.classList.contains('whole'),
           filled: getComputedStyle(b, '::before').content !== 'none' || !b.classList.contains('whole') }; })"""
with sync_playwright() as p:
    br = p.chromium.launch()
    def page(w):
        ctx = br.new_context(viewport={"width": w, "height": 900 if w >= 768 else 780})
        pg = ctx.new_page(); pg.on("pageerror", lambda e: errors.append(str(e))); return pg
    def go(pg, h, wait=1500): pg.goto("about:blank"); pg.goto(SITE + h); pg.wait_for_timeout(wait)
    def shot(pg, name, full=False):
        if os.environ.get("SHOTS"): pg.screenshot(path=os.path.join(os.environ["SHOTS"], name + ".png"), full_page=full)

    # ---------- BA-0008: the grid fits the width ----------
    expect = {360: 1, 390: 1, 430: 1, 768: 3, 1024: 4, 1280: 5, 1440: 5}   # 208 px minimum card
    for w, want in expect.items():
        pg = page(w); go(pg, "#/browse"); g = pg.evaluate(GRID)
        check(f"results @{w}: {want} column(s)", g and g["cols"] == want, g)
        check(f"results @{w}: no card below the minimum (208 px, or the whole width on phones)", g and (g["minCard"] >= 207.5 or (want == 1 and g["minCard"] >= g["w"] - 1)), g)
        check(f"results @{w}: every row equal, prices on one line", g and all(len(r["h"]) == 1 and len(r["price"]) == 1 for r in g["rows"]), g and g["rows"])
        check(f"results @{w}: no sideways scroll", g and not g["scroll"])
        check(f"results @{w}: 24 cars on the page", g and g["n"] == 24, g and g["n"])
        clip = pg.evaluate("() => [...document.querySelectorAll('.car .car-meta, .car .demand')].filter(e => e.scrollWidth > e.clientWidth + 1 || e.scrollHeight > e.clientHeight + 1).map(e => e.innerText)")
        check(f"results @{w}: specs and demand lines show in full (nothing cut off)", not clip, clip[:3])
        if w == 1280: shot(pg, "results_1280"); r1280 = g
        if w == 390: shot(pg, "results_390"); r390 = g
        pg.context.close()
    check("1280: at least 5 cars per row on the results page (was 4)", r1280["cols"] >= 5, r1280)
    check("390: photo stays 4:3", abs(r390["photoH"] - r390["card"] * 3 / 4) <= 1, r390)

    # a short list keeps the same card size (cards never grow when there are few)
    pg = page(1280); go(pg, "#/browse?make=Mercedes-Benz"); g = pg.evaluate(GRID)
    check("few cars: the cards keep their size instead of stretching", g and g["n"] >= 1 and abs(g["card"] - r1280["card"]) <= 1, [g, r1280["card"]])
    pg.context.close()

    # ---------- BA-0008: photo framing ----------
    pg = page(1280); go(pg, "#/browse", 2500); fr = pg.evaluate(FRAMES)
    by = {}; [by.setdefault(f["src"], f) for f in fr]
    check("every shape of photo is on the page", set(by) >= {"four3.webp", "portrait.webp", "wide.webp", "square.webp", "near.webp"}, list(by))
    check("every photo is held to its frame (before: a tall photo's box ran past the frame and lost its bottom)", all(f["pinned"] for f in fr), [f for f in fr if not f["pinned"]][:2])
    check("no photo is stretched or squeezed", all(not f["stretched"] for f in fr), [f for f in fr if f["stretched"]][:2])
    f = by.get("four3.webp", {}); check("a 4:3 photo fills the frame, nothing cropped", f.get("fit") == "cover" and not f.get("whole") and f.get("cropY", 1) <= 0.01 and f.get("cropX", 1) <= 0.01, f)
    f = by.get("near.webp", {}); check("a photo close to 4:3 fills the frame, at most a thin edge cropped (under 6%)", f.get("fit") == "cover" and f.get("cropY", 1) < 0.06, f)
    for s in ("portrait.webp", "square.webp", "wide.webp"):
        f = by.get(s, {}); check(f"{s.split('.')[0]} photo shown whole: tyres and bumpers not cut off", f.get("whole") and f.get("fit") == "contain" and f.get("cropY", 1) <= 0.001 and f.get("cropX", 1) <= 0.001, f)
        check(f"{s.split('.')[0]} photo: the frame is filled by a blurred copy of the same photo", f.get("bg") and f.get("filled"), f)
    # before the fix: a portrait photo in cover lost 44% of its height (22% under the tyres)
    pv = pg.evaluate("""() => { const b = [...document.querySelectorAll('.car-photo.whole')].find(x => x.querySelector('img').src.includes('portrait'));
      const i = b.querySelector('img'), r = b.getBoundingClientRect(), ir = i.naturalWidth / i.naturalHeight;
      const drawnH = getComputedStyle(i).objectFit === 'contain' ? Math.min(r.height, r.width / ir) : Math.max(r.height, r.width / ir);
      return Math.round(Math.min(r.height, drawnH) / drawnH * 100); }""")
    check("portrait photo: the whole height is visible (was 56%)", pv >= 99, pv)
    pg.evaluate("() => document.querySelector('[data-ref=results-grid]').scrollIntoView()"); shot(pg, "photos_1280")
    # hover still works on a whole photo
    pg.locator(".car-photo.whole").first.hover(); pg.wait_for_timeout(450)
    tr = pg.evaluate("() => getComputedStyle(document.querySelector('.car:hover .car-photo img') || document.body).transform")
    check("BA-0001 hover still zooms a whole photo", tr not in ("none", None), tr)
    # the long name keeps 2 lines and doesn't push the price
    g = pg.evaluate(GRID); check("a long name stays on 2 lines; the row's prices still line up", all(len(r["price"]) == 1 for r in g["rows"]), g["rows"])
    pg.context.close()

    # ---------- BA-0008: home shows whole rows ----------
    for w in (390, 768, 1024, 1280):
        pg = page(w); go(pg, "#/", 2000)
        h = pg.evaluate("""() => { const g = document.querySelector('[data-rows]'), cards = [...g.children], vis = cards.filter(c => !c.hidden);
          const cols = getComputedStyle(g).gridTemplateColumns.split(' ').filter(Boolean).length, m = document.querySelector('[data-ref=latest-cars] .sechead a');
          return { cols, vis: vis.length, more: m && !m.hidden && m.innerText }; }""")
        check(f"home @{w}: latest cars fill whole rows", h["cols"] == 1 and h["vis"] == 8 or h["cols"] > 1 and h["vis"] % h["cols"] == 0 and h["vis"] == h["cols"] * 2, h)
        check(f"home @{w}: 'See all' is there when more cars exist", bool(h["more"]) and "24" in h["more"], h)
        if w == 1280: shot(pg, "home_1280")
        pg.context.close()
    pg = page(1280); go(pg, "#/", 1500); pg.set_viewport_size({"width": 1024, "height": 900}); pg.wait_for_timeout(400)
    h = pg.evaluate("() => { const g = document.querySelector('[data-rows]'); return [getComputedStyle(g).gridTemplateColumns.split(' ').length, [...g.children].filter(c => !c.hidden).length]; }")
    check("home: resizing the window keeps whole rows", h[1] == h[0] * 2, h); pg.context.close()

    # ---------- admin: Admin, Cars ----------
    def admin(w):
        pg = page(w)
        go(pg, "#/signin"); pg.check("input[name=as][value=seller]"); pg.fill("input[name=email]", "admin@saaz.test"); pg.fill("input[name=password]", "demo1234"); pg.click("form button"); pg.wait_for_timeout(1500)
        go(pg, "#/admin/verify"); pg.fill("input[name=password]", "demo1234"); pg.click("#pf button"); pg.wait_for_timeout(1200)
        pg.fill("input[name=code]", totp(SECRET)); pg.click("#cf button"); pg.wait_for_timeout(1800)
        go(pg, "#/admin/cars", 2200)
        if os.environ.get("SHOTS"): pg.screenshot(path=os.path.join(os.environ["SHOTS"], f"debug_admin_{w}.png"))
        return pg
    for w, want in ((1280, 4), (1024, 3), (390, 1)):
        pg = admin(w); g = pg.evaluate(GRID)
        check(f"Admin, Cars @{w}: {want}+ cars per row" + (" (was 3)" if w == 1280 else ""), g and g["cols"] >= want, g)
        check(f"Admin, Cars @{w}: rows equal, prices on one line", g and all(len(r["h"]) == 1 and len(r["price"]) == 1 for r in g["rows"]), g and g["rows"])
        clip = pg.evaluate("() => [...document.querySelectorAll('.car .car-meta, .car .demand')].filter(e => e.scrollWidth > e.clientWidth + 1 || e.scrollHeight > e.clientHeight + 1).map(e => e.innerText)")
        check(f"Admin, Cars @{w}: specs and demand lines show in full", not clip, clip[:3])
        check(f"Admin, Cars @{w}: stage badge still on cars that aren't live", pg.locator(".car .car-tag.right").count() >= 1)
        check(f"Admin, Cars @{w}: cards still open the admin page", (pg.locator(".car").first.get_attribute("href") or "").startswith("#/admin/car/"))

        # ---------- BA-0009: the dropdowns ----------
        d = pg.evaluate("""() => { const f = document.querySelector('[data-ref=filter-panel]'), ss = [...f.querySelectorAll('select')], inp = f.querySelector('input[name=max]');
          const c = document.createElement('canvas').getContext('2d');
          return ss.map(s => { const cs = getComputedStyle(s); c.font = cs.font;
            const longest = Math.max(...[...s.options].map(o => c.measureText(o.text).width)), cur = c.measureText(s.options[s.selectedIndex].text).width;
            return { name: s.name, appearance: cs.appearance, chevron: cs.backgroundImage.includes('svg'), padR: parseFloat(cs.paddingRight), padL: parseFloat(cs.paddingLeft),
              h: s.getBoundingClientRect().height, inH: inp.getBoundingClientRect().height, bottom: Math.round(s.getBoundingClientRect().bottom), inBottom: Math.round(inp.getBoundingClientRect().bottom),
              room: s.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight), cur, longest, ell: cs.textOverflow }; }); }""")
        check(f"dropdowns @{w}: the browser's own arrow replaced by one chevron", all(x["appearance"] == "none" and x["chevron"] for x in d), d)
        check(f"dropdowns @{w}: the arrow has its own room (24 px or more) and the text lines up with its label (29 Oct 2026: fields are a value over a hairline)", all(x["padR"] >= 24 and x["padL"] == 0 for x in d), d)
        check(f"dropdowns @{w}: the chosen text fits without touching the arrow", all(x["cur"] <= x["room"] for x in d), d)
        check(f"dropdowns @{w}: a longer choice ends in an ellipsis instead of running under the arrow", all(x["ell"] == "ellipsis" for x in d), d)
        check(f"dropdowns @{w}: same height as the price field", all(x["h"] == x["inH"] for x in d), d)
        rows = pg.evaluate("""() => { const o = {}; [...document.querySelectorAll('[data-ref=filter-panel] select, [data-ref=filter-panel] input, [data-ref=filter-panel] .btn')].forEach(e => {
          const r = e.closest('label') ? e.closest('label').getBoundingClientRect() : e.getBoundingClientRect(); (o[Math.round(r.top)] = o[Math.round(r.top)] || []).push(Math.round(e.getBoundingClientRect().bottom)); });
          return Object.values(o).map(b => [...new Set(b)].length); }""")
        check(f"dropdowns @{w}: every control in a filter row shares one bottom edge", all(n == 1 for n in rows), rows)
        st = pg.locator("select[name=status]"); st.select_option("changes_requested"); pg.wait_for_timeout(150)
        room = pg.evaluate("() => { const s = document.querySelector('select[name=status]'), cs = getComputedStyle(s), c = document.createElement('canvas').getContext('2d'); c.font = cs.font; return [c.measureText(s.options[s.selectedIndex].text).width, s.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight)]; }")
        check(f"dropdowns @{w}: 'Changes requested' (the longest status) fits", room[0] <= room[1], room)
        st.select_option(""); pg.click("[data-ref=filter-panel] .btn"); pg.wait_for_timeout(1500)
        check(f"Admin, Cars @{w}: the filter still works (Every status shows all 30)", "30 cars" in pg.locator(".count").inner_text(), pg.locator(".count").inner_text())
        if w == 1280:
            pg.evaluate("() => window.scrollTo(0, 0)"); shot(pg, "admin_cars_1280")
        if w == 1024: pg.locator("[data-ref=filter-panel]").screenshot(path=os.path.join(os.environ["SHOTS"], "filters_1024.png")) if os.environ.get("SHOTS") else None
        pg.context.close()
    # the home search and the results filters use the same dropdown
    pg = page(390); go(pg, "#/browse")
    d = pg.evaluate("() => [...document.querySelectorAll('select')].map(s => getComputedStyle(s).appearance === 'none' && getComputedStyle(s).backgroundImage.includes('svg'))")
    check("dropdowns @390: same dropdown on the public filters", d and all(d), d)
    check("dropdowns @390: 48 px tall (touch target)", pg.evaluate("() => document.querySelector('select').getBoundingClientRect().height") == 48)
    pg.context.close()
    check("no script errors", not errors, errors[:3])
    br.close()
print(f"\n{ok} passed, {bad} failed")
sys.exit(1 if bad else 0)
