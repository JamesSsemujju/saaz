#!/usr/bin/env python3
"""Build the Saaz website from src/ into docs/ (served by GitHub Pages).

Usage:  python3 build.py
Needs:  Python 3.8+ only. No packages, no internet.

How it fits together:
  src/data/site.json      site-wide settings (WhatsApp number, launch, base path)
  src/data/modules.json   every service: drives nav, homepage list, footer, module pages
  src/data/images.json    fixed design images (files live in src/assets/img/)
  src/layouts/            base.html wraps every page; module.html is the template for each service page
  src/partials/           header, footer, icons, car illustration
  src/pages/              one-off pages (home, help, about...). First line holds JSON settings in a comment.
  src/modules/<slug>.html extra sections for one service page (optional)
  src/styles/*.css        joined, in order, into docs/assets/saaz.css
The build stops with an error on any unknown {{placeholder}} or broken internal link.
"""
import html, json, re, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC, OUT = ROOT / "src", ROOT / "docs"
CSS_ORDER = ["tokens.css", "base.css", "layout.css", "components.css", "pages.css"]
DESKTOP_NAV = ["inspections", "cars", "sell", "import", "finance", "garages"]
BUYER_FOOT = ["inspections", "history", "cars", "import", "finance"]
SELLER_FOOT = ["sell", "garages", "partners"]

def load(p): return json.loads((SRC / p).read_text(encoding="utf-8"))
def esc(s): return html.escape(s, quote=True)

site = load("data/site.json")
modules = load("data/modules.json")["modules"]
images = load("data/images.json")
M = {m["slug"]: m for m in modules}
base = site["basePath"]

def partial(name):
    for ext in (".html", ".svg"):
        p = SRC / "partials" / (name + ext)
        if p.exists():
            text = p.read_text(encoding="utf-8")
            return re.sub(r"<metadata>.*?</metadata>", "", text, flags=re.S)  # drop embedded file metadata to save bytes
    sys.exit(f"Missing partial: {name}")

def render(text, ctx):
    for _ in range(5):
        text = re.sub(r"\{\{>\s*([\w-]+)\s*\}\}", lambda m: partial(m.group(1)), text)
    def key(m):
        k = m.group(1)
        if k not in ctx: sys.exit(f"Unknown placeholder {{{{{k}}}}}")
        return str(ctx[k])
    for _ in range(3):  # values may contain placeholders such as {{base}}
        text = re.sub(r"\{\{\s*([\w]+)\s*\}\}", key, text)
    return text

def status_pill(m):
    return f'<span class="status {m["status"]}">{esc(m["status"].capitalize())} · {esc(m["when"])}</span>'

def icon(name): return f'<svg class="icon"><use href="#i-{name}"/></svg>'

def service_row(m):
    return (f'<li><a href="{base}{m["slug"]}/"><span class="ico">{icon(m["icon"])}</span>'
            f'<span><span class="svc-name">{esc(m["name"])}</span><span class="svc-line" style="display:block">{esc(m["line"])}</span>'
            f'<span class="svc-meta">{status_pill(m)}<span>{esc(m["audience"])}</span></span></span>'
            f'<span class="svc-go">{icon("arrow")}</span></a></li>')

def img_tag(slot, cls="figure"):
    f = images.get(slot, "")
    if not f: return ""
    if not (SRC / "assets/img" / f).exists(): sys.exit(f"images.json names {f} for '{slot}', but src/assets/img/{f} is missing")
    return f'<figure class="{cls}"><img src="{base}assets/img/{esc(f)}" alt="" loading="lazy" decoding="async"></figure>'

wa = re.fullmatch(r"\d{10,15}", site["whatsapp"] or "")
wa_url = f"https://wa.me/{site['whatsapp']}" if wa else ""

def common(active):
    def nav_link(slug, label):
        cur = ' aria-current="page"' if slug == active else ""
        return f'<a href="{base}{slug}/"{cur}>{esc(label)}</a>'
    desktop = "".join(nav_link(s, M[s]["nav"]) for s in DESKTOP_NAV) + nav_link("help", "Help")
    mobile = "".join(f'<a href="{base}{m["slug"]}/">{esc(m["name"])}<small>{esc(m["when"])}</small></a>' for m in modules)
    foot = lambda slugs: "".join(f'<li><a href="{base}{s}/">{esc(M[s]["name"])}</a></li>' for s in slugs)
    ctx = dict(site)
    ctx.update(base=base, nav_desktop=desktop, nav_mobile=mobile,
               foot_buyers=foot(BUYER_FOOT), foot_sellers=foot(SELLER_FOOT),
               whatsapp_header=f'<a class="hwa" href="{wa_url}">WhatsApp</a>' if wa else "",
               whatsapp_footer=f'<li><a href="{wa_url}">WhatsApp +{site["whatsapp"]}</a></li>' if wa else "",
               partner_contact=(f'<a class="btn" href="{wa_url}?text=' + "I%20run%20a%20garage%20in%20Kampala%20and%20want%20to%20be%20a%20Saaz%20partner." + '">Talk to us on WhatsApp</a>') if wa else '<span class="soon">Partner sign-up opens soon</span>')
    return ctx

def write(rel, text):
    p = OUT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")

def page(content, meta, active, extra=None):
    ctx = common(active)
    ctx.update(extra or {})
    body = render(content, ctx)
    ctx.update(title=esc(meta["title"]), description=esc(meta["description"]), content=body)
    return render((SRC / "layouts/base.html").read_text(encoding="utf-8"), ctx)

# clean output
if OUT.exists(): shutil.rmtree(OUT)
OUT.mkdir()
(OUT / ".nojekyll").write_text("")

# styles: one file, one request
write("assets/saaz.css", "\n".join((SRC / "styles" / f).read_text(encoding="utf-8") for f in CSS_ORDER))
# fixed images
for f in {v for k, v in images.items() if not k.startswith("_") and v}:
    (OUT / "assets/img").mkdir(parents=True, exist_ok=True)
    shutil.copy2(SRC / "assets/img" / f, OUT / "assets/img" / f)

# one-off pages
for src in sorted((SRC / "pages").glob("*.html")):
    raw = src.read_text(encoding="utf-8")
    m = re.match(r"<!--\s*(\{.*?\})\s*-->\n", raw, flags=re.S)
    if not m: sys.exit(f"{src.name}: first line must be a JSON comment")
    meta, content = json.loads(m.group(1)), raw[m.end():]
    extra = {"services_list": "".join(service_row(x) for x in modules)}
    hero = img_tag("home-hero")
    extra["hero_visual"] = hero or partial("car-illustration")
    out = "index.html" if src.stem == "index" else f"{src.stem}/index.html"
    write(out, page(content, meta, "help" if src.stem == "help" else meta.get("nav", ""), extra))

# service pages, all from one template
tmpl = (SRC / "layouts/module.html").read_text(encoding="utf-8")
for m in modules:
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
    meta = {"title": f'{m["name"]} | Saaz', "description": m["line"]}
    write(f'{m["slug"]}/index.html', page(tmpl, meta, m["slug"], ctx))

# link check: every internal link must point at a built page or file
bad = []
for f in OUT.rglob("*.html"):
    for href in re.findall(r'href="([^"]+)"', f.read_text(encoding="utf-8")):
        if href.startswith(base) and not href.startswith("//"):
            rel = href[len(base):].split("#")[0].split("?")[0]
            target = OUT / rel
            if not (target.is_file() or (target / "index.html").is_file() or rel == ""):
                bad.append((str(f.relative_to(OUT)), href))
if bad:
    for b in bad: print("Broken link:", *b)
    sys.exit(1)
pages = sorted(str(p.relative_to(OUT)) for p in OUT.rglob("index.html"))
print(f"Built {len(pages)} pages into docs/:", ", ".join(pages))
