"""layout_audit.py: renders the three templates (and the static pages that share them) at every test width,
saves a screenshot with the 12/4 column grid drawn over it, and checks the layout rules.

Usage: python3 tests/layout_audit.py <site url> <car ref> <out dir> [--signed-in]
  --signed-in (local test stack only, after tests/browser_flow_test.py): also renders the seller, garage, buyer
  and admin pages, signed in as the test accounts, at 390 and 1280.
Rules checked at each width:
  no sideways scroll; header logo, page heading and first card share one left edge;
  cards in a row have equal height and their inspection lines, prices and names start at the same y (specs follow the name);
  inputs, selects and buttons in a filter or search row share one height and one bottom edge;
  at 430 px and below every control is at least 44 px tall;
  home: the search is on the first screen; listing: price and contact are within two screens.
"""
import sys, json
from playwright.sync_api import sync_playwright
SITE, REF, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
WIDTHS = [360, 390, 430, 768, 1024, 1280, 1440]
PAGES = [("home", SITE + "#/"), ("results", SITE + "#/browse"), ("listing", SITE + "#/car/" + REF),
         ("static-cars", SITE + "preview/cars/"), ("static-car", None), ("module", SITE + "inspections/")]
OVERLAY = """() => { const o = document.createElement('div'); o.id='gridov';
  o.innerHTML = "<div class='wrap' style='height:100%'><div class='grid' style='height:100%'>" + Array.from({length:12}, (_, i) => "<i class='c" + i + "'></i>").join('') + "</div></div>";
  o.setAttribute('style','position:fixed;inset:0;pointer-events:none;z-index:9999');
  const s = document.createElement('style'); s.textContent = "#gridov .grid>i{grid-column:auto;background:rgba(255,0,80,.10);outline:1px solid rgba(255,0,80,.25)} @media(max-width:767px){#gridov .grid>i:nth-child(n+5){display:none}}";
  document.head.appendChild(s); document.body.appendChild(o); }"""
CHECKS = r"""(kind) => {
  const out = [], W = innerWidth, H = innerHeight, vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== 'hidden'; };
  const top = e => e.getBoundingClientRect().top + scrollY;
  if (document.documentElement.scrollWidth > W + 1) out.push('sideways scroll: page is ' + document.documentElement.scrollWidth + 'px wide');
  const logo = document.querySelector('.apphead .logo'); const L = logo && logo.getBoundingClientRect().left;
  const edge = [...document.querySelectorAll('main h1:not(.car-title), .sechead h2, .cars>.car:first-child, .listing>.gallery, .filters, .crumbs')].filter(vis);
  // the listing panel starts on column 9: check it lines up with the grid instead of the logo
  const bb = document.querySelector('.listing>.buybox'), g = document.querySelector('.listing>.gallery');
  if (bb && g && W >= 1024) { const gr = g.getBoundingClientRect().right, gap = parseFloat(getComputedStyle(document.querySelector('.listing')).columnGap); if (Math.abs(bb.getBoundingClientRect().left - gr - gap) > 1) out.push('price panel is not on the grid'); }
  if (bb && W >= 1024) { const wr = document.querySelector('.apphead .appright').getBoundingClientRect().right; if (Math.abs(bb.getBoundingClientRect().right - wr) > 1) out.push('price panel right edge ' + Math.round(bb.getBoundingClientRect().right) + ' != header right ' + Math.round(wr)); }
  const side = document.querySelector('.adminside'), main = document.querySelector('.adminmain');
  if (side && main && vis(side)) { const gap = parseFloat(getComputedStyle(main.parentElement).columnGap); if (Math.abs(main.getBoundingClientRect().left - side.getBoundingClientRect().right - gap) > 1) out.push('admin page is not on the grid next to the side menu'); }
  edge.forEach(e => { if (side && vis(side) && e.closest('.adminmain')) return; const l = e.getBoundingClientRect().left; if (Math.abs(l - L) > 1) out.push('left edge ' + Math.round(l) + ' != logo ' + Math.round(L) + ': ' + (e.className || e.tagName)); });
  document.querySelectorAll('.cars').forEach(g => {
    const rows = {}; [...g.children].filter(vis).forEach(c => { const k = Math.round(top(c)); (rows[k] = rows[k] || []).push(c); });
    Object.values(rows).forEach(r => {
      const hs = r.map(c => c.getBoundingClientRect().height); if (Math.max(...hs) - Math.min(...hs) > 1) out.push('card heights differ in a row: ' + hs.map(Math.round));
      ['.car-insp', '.car-price', '.car-name'].forEach(sel => { const ys = r.map(c => c.querySelector(sel)).filter(Boolean).map(e => top(e)); if (ys.length && Math.max(...ys) - Math.min(...ys) > 1) out.push(sel + ' at different y in a row: ' + ys.map(Math.round)); });
    });
  });
  document.querySelectorAll('.filters, .homesearch, .check, .inlineform, .chat .send').forEach(f => {
    const ctl = [...f.querySelectorAll('input:not([type=checkbox]), select, button, label.inline')].filter(vis);
    const rows = {}; ctl.forEach(c => { const k = Math.round(c.getBoundingClientRect().bottom); (rows[k] = rows[k] || []).push(c); });
    const bottoms = Object.keys(rows).map(Number).sort((a, b) => a - b);
    ctl.forEach(c => { const h = Math.round(c.getBoundingClientRect().height); if (h !== 48) out.push('control height ' + h + ' (not 48) in ' + f.className + ': ' + (c.name || c.textContent.trim().slice(0, 20))); });
    for (let i = 1; i < bottoms.length; i++) if (bottoms[i] - bottoms[i - 1] < 40) out.push('controls in one row with bottoms ' + bottoms[i - 1] + ' and ' + bottoms[i] + ' in ' + f.className);
  });
  if (W <= 430) [...document.querySelectorAll('a, button, input, select, summary, label.inline')].filter(vis).forEach(e => {
    if (e.closest('p, dd, li.prose, .crumbs, .car, small, .note, .lead, .sechead p, .insp-card p, .shots, #gridov')) return;  // links inside running text, and whole cards (much taller)
    const r = e.getBoundingClientRect(); if (r.height < 44) out.push('touch target ' + Math.round(r.height) + 'px: ' + (e.textContent.trim().slice(0, 24) || e.name || e.tagName));
  });
  if (kind === 'home') { const s = document.querySelector('#hs'); if (!s || s.getBoundingClientRect().top > H) out.push('home search starts below the first screen'); }
  if (kind === 'listing' || kind === 'static-car') {
    const p = document.querySelector('.car-bigprice'); if (!p || top(p) > 2 * H) out.push('price is beyond two screens (' + (p ? Math.round(top(p)) : 'none') + ')');
    const c = document.querySelector('.buybox .btn, .buybox form'); if (c && top(c) > 2 * H) out.push('contact/offer is beyond two screens (' + Math.round(top(c)) + ')');
  }
  return out;
}"""
SIGNED = "--signed-in" in sys.argv
ROLE_PAGES = {  # local test accounts from tests/browser_flow_test.py
  ("sam@x.test", "seller"): ["#/my/cars", "#/sell/new"],
  ("gus@garage.test", "garage"): ["#/garage", "#/garage/team"],
  ("bob@x.test", "buyer"): ["#/offers", "#/inbox", "#/account", "#/verify", "#/track", "#/selling"],
}
def totp(secret):
    import base64, hashlib, hmac, struct, time
    k = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8)); h = hmac.new(k, struct.pack(">Q", int(time.time()) // 30), hashlib.sha1).digest()
    o = h[-1] & 15; return "%06d" % ((struct.unpack(">I", h[o:o + 4])[0] & 0x7fffffff) % 1000000)
def signed_in_pages(br, w):
    import psycopg2
    db = psycopg2.connect(host="/var/tmp/saazpg", port=5433, user="postgres", dbname="sb"); db.autocommit = True; cur = db.cursor()
    def go(pg, h): pg.goto("about:blank"); pg.goto(SITE + h); pg.wait_for_timeout(1200)
    def signin(pg, email, as_):
        go(pg, "#/signin"); pg.check(f"input[name=as][value={as_}]"); pg.fill("input[name=email]", email); pg.fill("input[name=password]", "demo1234"); pg.click("form button"); pg.wait_for_timeout(1500)
    for (email, as_), hashes in list(ROLE_PAGES.items()) + [(("admin@saaz.test", "seller"), ["#/admin", "#/admin/cars", "#/admin/garages"])]:
        ctx = br.new_context(viewport={"width": w, "height": 800 if w >= 768 else 760}); pg = ctx.new_page()
        signin(pg, email, as_)
        if email.startswith("admin"):
            go(pg, "#/admin/verify"); pg.fill("input[name=password]", "demo1234"); pg.click("#pf button"); pg.wait_for_timeout(1200)
            cur.execute("select f.secret from auth.mfa_factors f join auth.users u on u.id=f.user_id where u.email=%s", (email,))
            pg.fill("input[name=code]", totp(cur.fetchone()[0])); pg.click("#cf button"); pg.wait_for_timeout(1800)
        for h in hashes:
            go(pg, h); key = (as_ + h).replace("#/", "-").replace("/", "-")
            res[f"{key}@{w}"] = pg.evaluate(CHECKS, "app"); pg.evaluate(OVERLAY); pg.screenshot(path=f"{OUT}/signed{key}_{w}.png", full_page=True)
        ctx.close()
    db.close()

res = {}
with sync_playwright() as p:
    br = p.chromium.launch()
    for w in WIDTHS:
        pg = br.new_page(viewport={"width": w, "height": 800 if w >= 768 else 760})
        static_car = None
        for name, url in PAGES:
            if name == "static-car":
                if not static_car: continue
                url = static_car
            pg.goto("about:blank"); pg.goto(url); pg.wait_for_timeout(1300)
            if name == "static-cars":
                a = pg.query_selector(".cars .car"); static_car = a and a.evaluate("e => e.href")
            found = pg.evaluate(CHECKS, name)
            res[f"{name}@{w}"] = found
            pg.evaluate(OVERLAY)
            pg.screenshot(path=f"{OUT}/{name}_{w}.png", full_page=True)
        pg.close()
        if SIGNED and w in (390, 1280): signed_in_pages(br, w)
    br.close()
bad = {k: v for k, v in res.items() if v}
for k, v in res.items(): print(("FAIL " if v else "PASS ") + k + ("" if not v else "\n   " + "\n   ".join(sorted(set(v)))))
print(f"\n{len(res) - len(bad)} of {len(res)} page renders pass")
