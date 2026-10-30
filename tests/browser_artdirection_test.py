"""29 Oct 2026 art direction on the local stack: type, header, home search on the picture, quick searches, the Saaz-drawn
dropdown list, and the inspection in the car page's price panel.
Usage: python3 tests/browser_artdirection_test.py <site url>   (fresh database; it adds its own cars)"""
import sys, json, datetime, psycopg2
from playwright.sync_api import sync_playwright
SITE = sys.argv[1]
db = psycopg2.connect(host="/var/tmp/saazpg", port=5433, user="postgres", dbname="sb"); db.autocommit = True; cur = db.cursor()
def sql(q, a=()): cur.execute(q, a or None); return cur.fetchall() if cur.description else None
SEL = sql("insert into auth.users (email, raw_user_meta_data) values ('seller@x.test', %s) returning id", (json.dumps({"name": "Sam", "country": "UG"}),))[0][0]
CARS = [("Toyota", "Harrier", "SUV", 96000000), ("Toyota", "Premio", "Saloon", 38000000), ("Subaru", "Forester", "SUV", 60000000),
        ("Mercedes-Benz", "E 300", "Saloon", 145000000), ("Nissan", "X-Trail", "SUV", 75000000), ("Mazda", "Demio", "Hatchback", 22000000)]
for i, (mk, md, bd, pr) in enumerate(CARS):
    vid = sql("insert into vehicles (vin, make, model) values (%s,%s,%s) returning id", ("JTART%012d" % i, mk, md))[0][0]
    sql("""insert into listings (vehicle_id, seller_id, country, region, status, make, model, year, fuel, gearbox, body, colour, engine, mileage, plate, currency, price,
           description, photos, logbook_name_matches, owner_authorised, live_at) values (%s,%s,'UG','Kampala','live',%s,%s,2016,'Petrol','Automatic',%s,'White','1.5',80000,%s,'UGX',%s,'Clean',%s,true,true,%s)""",
        (vid, SEL, mk, md, bd, "UBA %03dA" % i, pr, ["a.webp"], datetime.datetime.now(datetime.timezone.utc)))
ok = bad = 0
def check(n, c, x=""):
    global ok, bad
    if c: ok += 1; print("PASS", n)
    else: bad += 1; print("FAIL", n, str(x)[:400])
errors = []
with sync_playwright() as p:
    br = p.chromium.launch()
    def page(w, touch=False):
        ctx = br.new_context(viewport={"width": w, "height": 900}, has_touch=touch, is_mobile=touch)
        pg = ctx.new_page(); pg.on("pageerror", lambda e: errors.append(str(e))); return pg
    def go(pg, h, wait=1800): pg.goto("about:blank"); pg.goto(SITE + h); pg.wait_for_timeout(wait)

    pg = page(1280); go(pg, "#/")
    t = pg.evaluate("""async () => { await document.fonts.ready; const cs = s => getComputedStyle(document.querySelector(s));
      return { h1: cs('h1.display').fontFamily, body: cs('body').fontFamily, it: cs('h1.display i').fontStyle,
               serif: document.fonts.check('72px "Instrument Serif"'), sans: document.fonts.check('16px "Instrument Sans"'),
               loaded: [...document.fonts].filter(f => f.status === 'loaded').map(f => f.family + ' ' + f.weight + ' ' + f.style) }; }""")
    check("titles in Instrument Serif, with the italic word", "Instrument Serif" in t["h1"] and t["it"] == "italic", t)
    check("everything else in Instrument Sans", t["body"].startswith('"Instrument Sans"'), t["body"])
    check("both fonts load from the site itself", t["serif"] and t["sans"] and any("Instrument Serif" in f for f in t["loaded"]), t["loaded"])

    # header: Sell a car is a link like the others, not a box
    s = pg.evaluate("() => { const a = document.querySelector('[data-ref=sell-btn]'), cs = getComputedStyle(a); return [cs.backgroundColor, cs.borderRadius, cs.borderTopWidth, cs.color]; }")
    check("header: Sell a car has no box (no fill, no border, no pill)", s[0] in ("rgba(0, 0, 0, 0)", "transparent") and s[2] == "0px", s)

    # home search: on the picture, no panel
    h = pg.evaluate("""() => { const f = document.querySelector('[data-ref=home-search]'), cs = getComputedStyle(f), b = f.querySelector('.btn.go'), bs = getComputedStyle(b);
      const ctl = [...f.querySelectorAll('select,input')].map(e => [getComputedStyle(e).backgroundColor, getComputedStyle(e).borderTopWidth]);
      const bottoms = [...f.querySelectorAll('label')].map(l => Math.round(l.getBoundingClientRect().bottom)).concat([Math.round(b.getBoundingClientRect().bottom)]);
      return { panel: cs.backgroundColor, ctl, btnBg: bs.backgroundColor, btnBorder: bs.borderTopWidth, arrow: getComputedStyle(b, '::after').maskImage || getComputedStyle(b, '::after').webkitMaskImage, bottoms, text: b.innerText }; }""")
    check("home search: no white panel behind the fields", h["panel"] in ("rgba(0, 0, 0, 0)", "transparent"), h["panel"])
    check("home search: fields have no box of their own", all(c[0] in ("rgba(0, 0, 0, 0)", "transparent") and c[1] == "0px" for c in h["ctl"]), h["ctl"])
    check("home search: the action is the arrow link, not a block", h["btnBg"] in ("rgba(0, 0, 0, 0)", "transparent") and h["btnBorder"] == "0px" and "svg" in (h["arrow"] or ""), h)
    check("home search: fields and action share one bottom edge", len(set(h["bottoms"])) == 1, h["bottoms"])
    check("home search: counts the real cars", h["text"].strip() == "Search 6 cars", h["text"])

    # quick searches: built from the cars there are
    q = pg.evaluate("() => [...document.querySelectorAll('[data-ref=quick-search] a')].map(a => [a.innerText.trim(), a.getAttribute('href')])")
    check("quick search: the two commonest bodies, then the price ceilings that narrow the list", [x[0] for x in q] == ["SUV", "Saloon", "Under UGX 40m", "Under UGX 80m"], q)
    pg.click("[data-ref=quick-search] a:has-text('SUV')"); pg.wait_for_timeout(1500)
    check("quick search: SUV opens the results with that filter (3 cars)", "body=SUV" in pg.url and "3 cars" in pg.locator(".count").inner_text(), [pg.url, pg.locator(".count").inner_text()])
    go(pg, "#/"); pg.click("[data-ref=quick-search] a:has-text('Under UGX 40m')"); pg.wait_for_timeout(1500)
    check("quick search: Under UGX 40m shows only cars at or under 40m (2 cars)", "max=40000000" in pg.url and "2 cars" in pg.locator(".count").inner_text(), pg.locator(".count").inner_text())

    # the dropdown list on a mouse screen
    go(pg, "#/")
    sel = pg.locator("[data-ref=home-search] select[name=body]"); sel.click(); pg.wait_for_timeout(200)
    d = pg.evaluate("""() => { const l = document.querySelector('.dd'); if (!l) return null; const cs = getComputedStyle(l), on = l.querySelector('[aria-selected=true]');
      return { n: l.children.length, bg: cs.backgroundColor, on: on && on.innerText, tick: !!(on && on.querySelector('svg')), expanded: document.querySelector('select[name=body]').getAttribute('aria-expanded') }; }""")
    check("dropdown: Saaz draws the open list (dark on the picture), with every choice", d and d["n"] == 4 and d["bg"] != "rgb(255, 255, 255)" and d["expanded"] == "true", d)
    check("dropdown: the chosen line carries the tick", d and d["on"] == "Any body" and d["tick"], d)
    pg.locator(".dd li", has_text="Hatchback").click(); pg.wait_for_timeout(150)
    check("dropdown: a click chooses it and closes the list", sel.evaluate("s => s.value") == "Hatchback" and pg.locator(".dd").count() == 0)
    sel.focus(); pg.keyboard.press("ArrowDown"); pg.wait_for_timeout(100)   # opens on Hatchback (the current choice)
    opened = pg.locator(".dd").count() == 1
    pg.keyboard.press("ArrowDown"); pg.keyboard.press("Enter"); pg.wait_for_timeout(150)   # the next one down
    check("dropdown: keyboard opens on the current choice, moves and chooses", opened and sel.evaluate("s => s.value") == "SUV", sel.evaluate("s => s.value"))
    sel.focus(); pg.keyboard.press("ArrowDown"); pg.wait_for_timeout(100); pg.keyboard.press("Escape"); pg.wait_for_timeout(100)
    check("dropdown: Escape closes without changing", pg.locator(".dd").count() == 0 and sel.evaluate("s => s.value") == "SUV")
    pg.click("[data-ref=home-search] .btn.go"); pg.wait_for_timeout(1500)
    check("search: the chosen body is searched", "body=SUV" in pg.url and "3 cars" in pg.locator(".count").inner_text(), [pg.url, pg.locator(".count").inner_text()])
    # the results filters use the same list, light on the light page
    pg.locator("#flt select[name=make]").click(); pg.wait_for_timeout(200)
    bg = pg.evaluate("() => document.querySelector('.dd') && getComputedStyle(document.querySelector('.dd')).backgroundColor")
    check("results filters: the same list, light on a light page", bg == "rgb(255, 255, 255)", bg)
    pg.keyboard.press("Escape")

    # phones keep their own picker
    ph = page(390, touch=True); go(ph, "#/")
    n = ph.evaluate("() => document.querySelectorAll('select[aria-haspopup]').length")
    check("phones: the phone's own picker (Saaz list not attached)", n == 0, n)
    ph.locator("[data-ref=home-search] select[name=make]").select_option("Toyota"); ph.click("[data-ref=home-search] .btn.go"); ph.wait_for_timeout(1500)
    check("phones: search still works", "make=Toyota" in ph.url and "2 cars" in ph.locator(".count").inner_text(), ph.locator(".count").inner_text())
    go(ph, "#/"); hts = ph.evaluate("() => [...document.querySelectorAll('[data-ref=home-search] select, [data-ref=home-search] input, [data-ref=home-search] .btn.go, [data-ref=quick-search] a')].map(e => Math.round(e.getBoundingClientRect().height))")
    check("phones: every search control and quick search is at least 44 px tall", min(hts) >= 44, hts)
    check("phones: no sideways scroll", ph.evaluate("() => document.documentElement.scrollWidth <= innerWidth"))

    check("no script errors", not errors, errors[:3])
    br.close()
print(f"\n{ok} passed, {bad} failed")
sys.exit(1 if bad else 0)
