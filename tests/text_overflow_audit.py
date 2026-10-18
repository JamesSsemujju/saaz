"""Audit: on every page, at 4 widths, find text that spills out of its box into its neighbours.
Public site + preview + app pages (with data), plus the VIN decoder with long real-world values."""
import json, sys, psycopg2
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT = "http://localhost:8777/saaz/"
DOCS = Path(sys.argv[1])
WIDTHS = [320, 390, 768, 1280]
pages = sorted("" if p.parent == DOCS else str(p.parent.relative_to(DOCS)) + "/" for p in DOCS.rglob("index.html"))
pages = [p for p in pages if not p.startswith("app/") and not p.startswith("admin/")]

STRESS = len(sys.argv) > 2 and sys.argv[2] == "stress"
LONG = "ZXCVBNMASDFGHJKLQWERTYUIOP0123456789ZXCVBNM"
NHTSA = {"Results": [{"Make": "TOYOTA", "Model": "RAV4", "ModelYear": "2017", "Trim": "LE", "Series": "ASA44L/ASA42L/AVA44L",
  "BodyClass": "Sport Utility Vehicle (SUV)/Multipurpose Vehicle (MPV)", "FuelTypePrimary": "Gasoline", "DisplacementL": "2.5",
  "DriveType": "4WD/4-Wheel Drive/4x4", "TransmissionStyle": "Automatic", "PlantCountry": "JAPAN", "ErrorCode": "0", "ErrorText": "0 - VIN decoded clean."}]}

if STRESS:
    NHTSA["Results"][0] = {k: (LONG if k not in ("ErrorCode", "ErrorText", "ModelYear") else v) for k, v in NHTSA["Results"][0].items()}

JS = """() => {
  const out = [];
  for (const el of document.querySelectorAll('body *')) {
    if (el.closest('svg,script,style,noscript,select,option,input,textarea,[hidden]')) continue;
    const shut = el.closest('details:not([open])'); if (shut && !el.closest('summary')) continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const hasText = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    if (!hasText) continue;
    // text wider than its own box, and the box doesn't scroll or clip it on purpose
    if (el.scrollWidth > el.clientWidth + 1 && el.clientWidth > 0 && !['auto','scroll','hidden','clip'].includes(cs.overflowX) && cs.textOverflow !== 'ellipsis') {
      if (el.closest('.tablewrap,.tabs,.faststrip,.appnav,.micro,.ribbon')) continue;
      out.push({el: el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className.split(' ').join('.') : ''),
        text: el.textContent.trim().slice(0, 50), box: el.clientWidth, needs: el.scrollWidth});
    }
  }
  return out;
}"""

db = psycopg2.connect(host="/var/tmp/saazpg", port=5433, user="postgres", dbname="sb"); c = db.cursor()
c.execute("select verify_code from reviews where verify_code is not null limit 1"); code = (c.fetchone() or [None])[0]
c.execute("select id, ref from listings limit 1"); row = c.fetchone()
if STRESS:  # long unbroken text in every field people can type
    db.rollback(); db.autocommit = True
    c.execute("update profiles set name = %s", (LONG,))
    c.execute("update garages set name = %s, address = %s", (LONG, LONG))
    c.execute("update listings set colour = %s, description = %s, admin_note = %s, model = %s, engine = %s", (LONG, LONG + " " + LONG, LONG, LONG[:30], LONG[:20]))
    c.execute("update reviews set garage_name = %s, member_name = %s, notes = %s", (LONG, LONG, LONG))
    c.execute("update messages set body = %s", (LONG + LONG,))
    c.execute("update notifications set body = %s", (LONG + LONG,))
problems = []
with sync_playwright() as pw:
    b = pw.chromium.launch()
    for w in WIDTHS:
        ctx = b.new_context(viewport={"width": w, "height": 900})
        pg = ctx.new_page()
        pg.route("**/vpic.nhtsa.dot.gov/**", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(NHTSA)))
        def audit(label):
            for p in pg.evaluate(JS): problems.append((w, label, p))
        for p in pages:
            pg.goto(ROOT + p); pg.wait_for_timeout(250); audit("/" + p)
        # VIN decoder with long values
        pg.goto(ROOT + "history/"); pg.fill("#vin", "JTMBFREV3HD123456"); pg.click("#vinform button"); pg.wait_for_timeout(800); audit("VIN decoder result")
        # App pages (public and signed in)
        app = ROOT + "app/"
        for h in ["#/browse", "#/selling", "#/verify?code=" + (code or "X"), "#/report/" + (code or "X"), "#/how", "#/signin", "#/signup", "#/garage/apply"] + (["#/car/" + row[1]] if row else []):
            pg.goto("about:blank"); pg.goto(app + h); pg.wait_for_timeout(900); audit("app " + h.split("?")[0])
        for email, as_, hashes in [("sam@x.test", "seller", ["#/my/cars", "#/sell/new", "#/offers", "#/inbox"] + (["#/my/cars/" + str(row[0])] if row else [])),
                                   ("gus@garage.test", "garage", ["#/garage", "#/garage/team"]),
                                   ("admin@saaz.test", "admin", ["#/admin", "#/admin/cars", "#/admin/saaz", "#/admin/garages", "#/admin/users", "#/admin/deals", "#/admin/audit", "#/admin/outbox", "#/admin/settings", "#/admin/vehicles", "#/admin/reviews"] + (["#/admin/car/" + str(row[0])] if row else []))]:
            pg.goto("about:blank"); pg.goto(app + "#/signin"); pg.wait_for_timeout(500)
            pg.evaluate("localStorage.clear()"); pg.goto("about:blank"); pg.goto(app + "#/signin"); pg.wait_for_timeout(600)
            pg.check(f"input[name=as][value={'seller' if as_ == 'admin' else as_}]"); pg.fill("input[name=email]", email); pg.fill("input[name=password]", "demo1234"); pg.click("form button"); pg.wait_for_timeout(1200)
            if as_ == "admin":  # staff step-up: password again, then the authenticator code (part 10)
                import psycopg2, base64, hashlib, hmac, struct, time
                db = psycopg2.connect(host="/var/tmp/saazpg", port=5433, user="postgres", dbname="sb"); k = db.cursor()
                k.execute("select f.secret from auth.mfa_factors f join auth.users u on u.id=f.user_id where u.email=%s", (email,)); sec = k.fetchone()[0]; db.close()
                key = base64.b32decode(sec.upper() + "=" * (-len(sec) % 8)); hm = hmac.new(key, struct.pack(">Q", int(time.time()) // 30), hashlib.sha1).digest(); o = hm[-1] & 15
                pg.goto("about:blank"); pg.goto(app + "#/admin/verify"); pg.wait_for_timeout(900)
                pg.fill("input[name=password]", "demo1234"); pg.click("#pf button"); pg.wait_for_timeout(1200)
                pg.fill("input[name=code]", "%06d" % ((struct.unpack(">I", hm[o:o + 4])[0] & 0x7fffffff) % 1000000)); pg.click("#cf button"); pg.wait_for_timeout(1800)
            for h in hashes:
                pg.goto("about:blank"); pg.goto(app + h); pg.wait_for_timeout(900); audit(f"app {as_} {h}")
        ctx.close()
    b.close()
seen = set()
for w, label, p in problems:
    k = (label, p["el"], p["text"])
    if k in seen: continue
    seen.add(k); print(f"{w}px  {label}  {p['el']}  '{p['text']}'  box {p['box']} needs {p['needs']}")
print(f"\n{len(pages)} site pages + app pages at {WIDTHS}: {len(seen)} spill problems")
