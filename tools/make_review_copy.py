#!/usr/bin/env python3
"""Make a copy of docs/ that works from any folder, for reviewing the site before shipping.

Usage:  python3 tools/make_review_copy.py <output folder>
Rewrites every /saaz/... link to a relative path and points folder links at index.html,
so the copy opens anywhere (a local folder, a review page) without a web server at /saaz/.
docs/ itself is not changed.
"""
import os, re, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
BASE = "/saaz/"
out = Path(sys.argv[1]).resolve()
if out.exists(): shutil.rmtree(out)
shutil.copytree(DOCS, out, ignore=shutil.ignore_patterns(".nojekyll"))

ATTR = re.compile(r'((?:href|src|action)=")(' + re.escape(BASE) + r'[^"]*)(")')
SRCSET = re.compile(r'(srcset=")([^"]*)(")')

def rel(target, page_dir):
    path, sep, frag = target[len(BASE):].partition("#")
    path, qsep, query = path.partition("?")
    if path == "" or path.endswith("/"):
        path += "index.html"
    r = os.path.relpath(out / path, page_dir)
    return r + (qsep + query if qsep else "") + (sep + frag if sep else "")

for f in out.rglob("*.html"):
    text = f.read_text(encoding="utf-8")
    d = f.parent
    text = ATTR.sub(lambda m: m.group(1) + rel(m.group(2), d) + m.group(3), text)
    text = SRCSET.sub(lambda m: m.group(1) + ", ".join(
        (rel(p.split()[0], d) + " " + " ".join(p.split()[1:])).strip() if p.strip().startswith(BASE) else p.strip()
        for p in m.group(2).split(",")) + m.group(3), text)
    def cfg(m):
        r = os.path.relpath(out / m.group(1)[len(BASE):], d).replace(os.sep, "/") + "/"
        return '"base": "' + ("" if r == "./" else r) + '", "fileLinks": true'
    text = re.sub(r'"base": "(' + re.escape(BASE) + r'[^"]*)"', cfg, text)
    f.write_text(text, encoding="utf-8")
left = [str(f) for f in out.rglob("*.html") if BASE in re.sub(r"https?://\S+", "", f.read_text(encoding="utf-8"))]
print(f"Review copy in {out}. Files still mentioning {BASE}: {len(left)}")
