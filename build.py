#!/usr/bin/env python3
"""Build the Saaz website from src/ into docs/ (served by GitHub Pages).

Usage:  python3 build.py
Needs:  Python 3.8+ only. No packages, no internet.

Builds two sites:
  docs/          the public site. Car listings come from src/data/cars.json (real, inspected cars only).
  docs/preview/  a design preview using src/data/cars.sample.json. Every sample is labelled,
                 the pages carry noindex, and nothing on the public site links to it.

How it fits together:
  src/data/site.json      site-wide settings (WhatsApp number, base path, Supabase URL and anon key)
  src/data/modules.json   every service: drives nav, homepage list, footer, module pages
  src/data/images.json    fixed design images (files live in src/assets/img/)
  src/data/cars.json      real listings (empty until inspections run)
  src/layouts/            base.html wraps every page; app.html wraps the marketplace app (built at the site root; /app/ forwards there); module.html = each service page; car.html = each car page
  src/partials/           header, footer, icons, car illustration
  src/pages/              one-off pages. A page named like a service (cars.html) replaces that service's template page.
  src/modules/<slug>.html extra sections for one service page (optional)
  src/styles/*.css        joined, in order, into assets/saaz.css
  src/scripts/*.js        copied to assets/
The build stops with an error on any unknown {{placeholder}}, broken internal link, or size not taken from tokens.css.
"""
import html, json, re, shutil, sys
from datetime import date
from pathlib import Path
MONO = ' class="mono"'

ROOT = Path(__file__).resolve().parent
SRC, DOCS = ROOT / "src", ROOT / "docs"
CSS_ORDER = ["tokens.css", "base.css", "layout.css", "components.css", "pages.css", "cars.css", "app.css"]
DESKTOP_NAV = ["inspections", "cars", "sell", "import", "finance", "garages"]
BUYER_FOOT = ["inspections", "history", "cars", "import", "finance"]
SELLER_FOOT = ["sell", "garages", "partners"]
# Assumption: price and year bands for browsing. Edit here.
PRICE_BANDS = [("Under 20m", 0, 19999999), ("20m to 40m", 20000000, 39999999), ("40m to 70m", 40000000, 69999999), ("70m to 100m", 70000000, 99999999), ("Over 100m", 100000000, None)]
YEAR_BANDS = [("2010 and older", 0, 2010), ("2011 to 2014", 2011, 2014), ("2015 to 2017", 2015, 2017), ("2018 and newer", 2018, None)]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

def load(p): return json.loads((SRC / p).read_text(encoding="utf-8"))
def esc(s): return html.escape(str(s), quote=True)

site = load("data/site.json")
modules = load("data/modules.json")["modules"]
images = load("data/images.json")
M = {m["slug"]: m for m in modules}

def partial(name):
    for ext in (".html", ".svg"):
        p = SRC / "partials" / (name + ext)
        if p.exists():
            return re.sub(r"<metadata>.*?</metadata>", "", p.read_text(encoding="utf-8"), flags=re.S)
    sys.exit(f"Missing partial: {name}")

def render(text, ctx):
    for _ in range(5):
        text = re.sub(r"\{\{>\s*([\w-]+)\s*\}\}", lambda m: partial(m.group(1)), text)
    def key(m):
        k = m.group(1)
        if k not in ctx: sys.exit(f"Unknown placeholder {{{{{k}}}}}")
        return str(ctx[k])
    for _ in range(3):
        text = re.sub(r"\{\{\s*([\w]+)\s*\}\}", key, text)
    return text

def icon(name): return f'<svg class="icon"><use href="#i-{name}"/></svg>'
def ugx(n): return f"UGX {n:,}"
def day(iso):
    y, m, d = iso.split("-")
    return f"{int(d)} {MONTHS[int(m) - 1]} {y}"
def km(n): return f"{n:,} km"

def build_site(out, base, cars, preview):
    def status_pill(m):
        return ""  # release timing is not shown publicly (James, 17 Oct 2026)

    def service_row(m):
        return (f'<li><a href="{base}{m["slug"]}/"><span class="ico">{icon(m["icon"])}</span>'
                f'<span><span class="svc-name">{esc(m["name"])}</span><span class="svc-line">{esc(m["line"])}</span>'
                f'<span class="svc-meta"><span>{esc(m["audience"])}</span></span></span>'
                f'<span class="svc-go">{icon("arrow")}</span></a></li>')

    def img_tag(slot, cls="figure", eager=False):
        f = images.get(slot, "")
        if not f: return ""
        for wdt in (640, 1280):
            if not (SRC / "assets/img" / f"{f}-{wdt}.webp").exists():
                sys.exit(f"images.json names '{f}' for '{slot}', but src/assets/img/{f}-{wdt}.webp is missing. Run tools/prepare_images.py")
        load_attr = 'fetchpriority="high"' if eager else 'loading="lazy"'
        return (f'<figure class="{cls}"><img src="{base}assets/img/{esc(f)}-640.webp" '
                f'srcset="{base}assets/img/{esc(f)}-640.webp 640w, {base}assets/img/{esc(f)}-1280.webp 1280w" '
                f'sizes="(min-width: 900px) 50vw, 100vw" width="1280" height="960" alt="" {load_attr} decoding="async"></figure>')

    wa = re.fullmatch(r"\d{10,15}", site["whatsapp"] or "")
    wa_url = f"https://wa.me/{site['whatsapp']}" if wa else ""
    sample_tag = '<span class="sample">Design sample</span>' if preview else ""

    def common(active):
        def nav_link(slug, label):
            cur = ' aria-current="page"' if slug == active else ""
            return f'<a href="{base}{slug}/"{cur}>{esc(label)}</a>'
        foot = lambda slugs: "".join(f'<li><a href="{base}{s}/">{esc(M[s]["name"])}</a></li>' for s in slugs)
        ctx = dict(site)
        ctx.update(base=base,
                   nav_desktop="".join(nav_link(s, M[s]["nav"]) for s in DESKTOP_NAV) + nav_link("help", "Help"),
                   nav_mobile="".join(f'<a href="{base}{m["slug"]}/">{esc(m["name"])}</a>' for m in modules),
                   foot_buyers=foot(BUYER_FOOT), foot_sellers=foot(SELLER_FOOT),
                   whatsapp_header=f'<a class="hwa" href="{wa_url}">WhatsApp</a>' if wa else "",
                   whatsapp_footer=f'<li><a href="{wa_url}">WhatsApp +{site["whatsapp"]}</a></li>' if wa else "",
                   partner_contact=(f'<a class="btn" href="{wa_url}?text=I%20run%20a%20garage%20in%20Kampala%20and%20want%20to%20be%20a%20Saaz%20partner.">Talk to us on WhatsApp</a>') if wa else "",
                   robots='\n<meta name="robots" content="noindex,nofollow">' if preview else "",
                   saaz_config="<script>window.SAAZ=" + json.dumps({"base": base, "supabaseUrl": "" if preview else site.get("supabaseUrl", ""), "supabaseAnonKey": "" if preview else site.get("supabaseAnonKey", ""), "whatsapp": site.get("whatsapp", "")}) + "</script>",
                   strip=("<b>Design preview.</b> Every car on these pages is an invented sample for reviewing the design. None is for sale.") if preview
                         else "<b>Preview.</b> Saaz is not trading yet. Nothing here can be bought, booked or paid for.")
        return ctx

    def write(rel, text):
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def page(content, meta, active, extra=None):
        ctx = common(active)
        ctx.update(extra or {})
        body = render(content, ctx)
        ctx.update(title=esc(meta["title"]), description=esc(meta["description"]), content=body)
        if meta.get("noindex"): ctx["robots"] = '\n<meta name="robots" content="noindex,nofollow">'
        return render((SRC / "layouts" / (meta.get("layout", "base") + ".html")).read_text(encoding="utf-8"), ctx)

    # ---- cars ----
    def photo(c, cls="car-photo", tag=True):
        inner = (f'<img src="{base}assets/img/cars/{esc(c["photos"][0])}" alt="" loading="lazy" decoding="async">' if c["photos"]
                 else '<svg class="ph" aria-hidden="true"><use href="#i-carside"/></svg><span class="phl">Photo from the inspection</span>')
        n = len(c["inspection"]["findings"])
        t = (f'<span class="car-tag"><i></i>{esc(c["inspection"]["result"])} · {n} finding{"s" if n != 1 else ""}</span>' if tag else "")
        return f'<div class="{cls}">{inner}{t}{sample_tag}</div>'

    def name(c): return f'{c["year"]} {c["make"]} {c["model"]}'
    def slug(c): return c["ref"].lower()

    def card(c):
        return (f'<a class="car" href="{base}cars/{slug(c)}/" data-make="{esc(c["make"])}" data-body="{esc(c["body"])}" '
                f'data-fuel="{esc(c["fuel"])}" data-gearbox="{esc(c["gearbox"])}" data-price="{c["price_ugx"]}" '
                f'data-year="{c["year"]}" data-km="{c["km"]}" data-date="{c["inspection"]["date"]}">'
                f'{photo(c)}<div class="car-name">{esc(name(c))}</div>'
                f'<div class="car-meta">{km(c["km"])} · {esc(c["fuel"])} · {esc(c["gearbox"])} · {esc(c["drive"])}</div>'
                f'<div class="car-price"><b>{ugx(c["price_ugx"])}</b><small>{esc(c["area"])}</small></div></a>')

    def counts(key):
        d = {}
        for c in cars: d[c[key]] = d.get(c[key], 0) + 1
        return sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))

    def select(name_, label, opts):
        o = "".join(f'<option value="{esc(v)}">{esc(t)}</option>' for v, t in opts)
        return f'<label>{label}<select name="{name_}"><option value="">Any</option>{o}</select></label>'

    band = lambda lo, hi: f"{lo}-{'' if hi is None else hi}"
    cars_sorted = sorted(cars, key=lambda c: c["inspection"]["date"], reverse=True)
    if True:  # filters always exist; live-cars.js adds options for database cars
        filter_fields = (select("make", "Make", [(k, f"{k} ({n})") for k, n in counts("make")]) +
                         select("body", "Body type", [(k, f"{k} ({n})") for k, n in counts("body")]) +
                         select("price", "Price (UGX)", [(band(lo, hi), t) for t, lo, hi in PRICE_BANDS]) +
                         select("year", "Year", [(band(lo, hi), t) for t, lo, hi in YEAR_BANDS]) +
                         select("fuel", "Fuel", [(k, k) for k, _ in counts("fuel")]) +
                         select("gearbox", "Gearbox", [(k, k) for k, _ in counts("gearbox")]))
        chip = lambda f, v, t, n=None: f'<button type="button" data-set="{f}:{esc(v)}" aria-pressed="false">{esc(t)}{f"<small>{n}</small>" if n else ""}</button>'
        shop_by = ('<section class="shopby" hidden aria-label="Shop by"><div class="wrap">'
                   '<div class="row"><span class="lbl">Make</span>' + "".join(chip("make", k, k, n) for k, n in counts("make")) + "</div>"
                   '<div class="row"><span class="lbl">Body</span>' + "".join(chip("body", k, k, n) for k, n in counts("body")) + "</div>"
                   '<div class="row"><span class="lbl">Price</span>' + "".join(chip("price", band(lo, hi), t) for t, lo, hi in PRICE_BANDS) + "</div>"
                   "</div></section>")
        count_text = f"{len(cars)} car{'s' if len(cars) != 1 else ''}"
        car_empty = "" if cars else ('<div class="empty" id="carsempty"><b>No cars listed yet</b><span>A car appears here only after it passes a Saaz review. '
                     "Check back soon.</span></div>")
        if not cars: shop_by = ""
    cars_ctx = {
        "cars_status": status_pill(M["cars"]), "shop_by": shop_by, "filter_fields": filter_fields,
        "car_cards": "".join(card(c) for c in cars_sorted), "car_empty": car_empty, "car_count_text": count_text,
        "cars_script": f'<script src="{base}assets/live-cars.js" defer></script>',
    }

    # ---- output ----
    if out.exists() and out != DOCS / "preview": shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / ".nojekyll").write_text("")
    write("assets/saaz.css", "\n".join((SRC / "styles" / f).read_text(encoding="utf-8") for f in CSS_ORDER))
    for js in (SRC / "scripts").glob("*.js"):
        write(f"assets/{js.name}", js.read_text(encoding="utf-8"))
    for f in {v for k, v in images.items() if not k.startswith("_") and v}:
        (out / "assets/img").mkdir(parents=True, exist_ok=True)
        for wdt in (640, 1280):
            shutil.copy2(SRC / "assets/img" / f"{f}-{wdt}.webp", out / "assets/img" / f"{f}-{wdt}.webp")
    for sub in ("brand", "social"):  # logo and icons (brand kit); social icons for emails
        if (SRC / "assets/img" / sub).exists():
            shutil.copytree(SRC / "assets/img" / sub, out / "assets/img" / sub, dirs_exist_ok=True, ignore=shutil.ignore_patterns("*.md"))
    for c in cars:
        for f in c["photos"]:
            (out / "assets/img/cars").mkdir(parents=True, exist_ok=True)
            shutil.copy2(SRC / "assets/img/cars" / f, out / "assets/img/cars" / f)

    page_slugs = set()
    for src in sorted((SRC / "pages").glob("*.html")):
        raw = src.read_text(encoding="utf-8")
        m = re.match(r"<!--\s*(\{.*?\})\s*-->\n", raw, flags=re.S)
        if not m: sys.exit(f"{src.name}: first line must be a JSON comment")
        meta, content = json.loads(m.group(1)), raw[m.end():]
        extra = {"services_list": "".join(service_row(x) for x in modules),
                 "hero_visual": img_tag("home-hero", "figure hero-photo", eager=True) or partial("car-illustration")}
        extra.update(cars_ctx)
        # The marketplace app (pages/index.html) is the site root: one address for everything.
        # The design preview has no database, so its root shows the About page (pages/home.html) instead.
        if preview and src.stem in ("index", "app"): continue
        page_slugs.add(src.stem)
        html_out = page(content, meta, "help" if src.stem == "help" else meta.get("nav", ""), extra)
        write("index.html" if src.stem == "index" else f"{src.stem}/index.html", html_out)
        if preview and src.stem == "home": write("index.html", html_out)

    tmpl = (SRC / "layouts/module.html").read_text(encoding="utf-8")
    for m in modules:
        if m["slug"] in page_slugs: continue  # a hand-built page replaces the template page
        extra_file = SRC / "modules" / f"{m['slug']}.html"
        fig = img_tag(m["slug"])
        ctx = {
            "m_name": esc(m["name"]), "m_intro": esc(m["intro"]), "m_icon": m["icon"], "m_audience": esc(m["audience"]),
            "m_when": esc(m["when"]), "m_status": status_pill(m),
            "m_steps_title": esc(f'{m["name"]} in {len(m["steps"])} steps.'),
            "m_steps": "".join(f'<li><span class="n">{i}</span><div><b>{esc(a)}</b><span>{esc(b)}</span></div></li>' for i, (a, b) in enumerate(m["steps"], 1)),
            "m_depends": "".join(f"<li>{esc(d)}</li>" for d in m["depends"]),
            "m_related": "".join(service_row(M[r]) for r in m["related"]),
            "m_figure": fig, "m_figure_class": "has-figure" if fig else "",
            "module_extra": extra_file.read_text(encoding="utf-8") if extra_file.exists() else "",
        }
        write(f'{m["slug"]}/index.html', page(tmpl, {"title": f'{m["name"]} | Saaz', "description": m["line"]}, m["slug"], ctx))

    car_tmpl = (SRC / "layouts/car.html").read_text(encoding="utf-8")
    for c in cars:
        ins = c["inspection"]
        n = len(ins["findings"])
        specs = [("Year", c["year"]), ("Mileage", km(c["km"])), ("Fuel", c["fuel"]), ("Gearbox", c["gearbox"]), ("Drive", c["drive"]),
                 ("Engine", f'{c["cc"]:,} cc'), ("Body", c["body"]), ("Colour", c["colour"]), ("Chassis number", c["chassis"]), ("Saaz ref", c["ref"])]
        findings = "".join(f'<li><span class="lvl {f["level"]}">{"Attention" if f["level"] == "attention" else "Note"}</span><div><b>{esc(f["area"])}</b><span>{esc(f["note"])}</span></div></li>' for f in ins["findings"]) \
                   or '<li><span class="lvl clear">Clear</span><div><b>No findings</b><span>Every check on the list passed.</span></div></li>'
        more = [x for x in cars_sorted if x is not c and x["body"] == c["body"]][:3]
        ctx = {
            "c_name": esc(name(c)), "c_meta": f'{km(c["km"])} · {esc(c["fuel"])} · {esc(c["gearbox"])} · {esc(c["drive"])}',
            "c_price": ugx(c["price_ugx"]), "c_area": esc(c["area"]), "c_seller": esc(c["seller"]),
            "c_result": esc(ins["result"]), "c_result_class": "pass" if ins["result"] == "Passed" else "",
            "c_findings_count": f'{n} finding{"s" if n != 1 else ""}', "c_date": day(ins["date"]), "c_garage": esc(ins["garage"]),
            "c_photo_main": photo(c, tag=False), "c_thumbs": "".join(photo(c, tag=False) for _ in range(4)) if not c["photos"] else "",
            "c_sample": sample_tag,
            "c_contact": (f'<a class="btn wide" href="{wa_url}?text=' + html.escape(__import__("urllib.parse").parse.quote(f"Hello Saaz, I'm interested in {name(c)} ({c['ref']}).")) + '">Ask about this car on WhatsApp</a>') if wa else "",
            "c_specs": "".join(f'<div><dt>{esc(k)}</dt><dd{MONO if k == "Chassis number" else ""}>{esc(v)}</dd></div>' for k, v in specs),
            "c_findings": findings,
            "c_more": ('<section class="band soft"><div class="wrap"><div class="sechead"><h2>More cars like this</h2></div>'
                       '<div class="cars">' + "".join(card(x) for x in more) + "</div></div></section>") if more else "",
        }
        write(f"cars/{slug(c)}/index.html", page(car_tmpl, {"title": f"{name(c)} | Saaz", "description": f"{name(c)}, inspected {day(ins['date'])}."}, "cars", ctx))

def link_check(base):
    bad = []
    for f in DOCS.rglob("*.html"):
        for href in re.findall(r'(?:href|src)="([^"]+)"', f.read_text(encoding="utf-8")):
            if href.startswith(base):
                rel = href[len(base):].split("#")[0].split("?")[0]
                t = DOCS / rel
                if not (rel == "" or t.is_file() or (t / "index.html").is_file()):
                    bad.append((str(f.relative_to(DOCS)), href))
    return bad

# Layout discipline: every spacing, type and container value comes from tokens.css (tools/check_layout.py)
sys.path.insert(0, str(ROOT / "tools"))
import check_layout
if check_layout.main(): sys.exit("Fix the values above: use the tokens in src/styles/tokens.css.")
base = site["basePath"]
real = load("data/cars.json")["cars"]
sample = load("data/cars.sample.json")["cars"]
build_site(DOCS, base, real, preview=False)
build_site(DOCS / "preview", base + "preview/", sample, preview=True)
bad = link_check(base)
if bad:
    for b in bad: print("Broken link:", *b)
    sys.exit(1)
pub = [p for p in DOCS.rglob("index.html") if "preview" not in p.parts]
pre = list((DOCS / "preview").rglob("index.html"))
print(f"Built {len(pub)} public pages and {len(pre)} preview pages. All internal links resolve.")
