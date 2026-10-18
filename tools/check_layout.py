#!/usr/bin/env python3
"""check_layout.py: every spacing, type and container value comes from tokens.css.

Usage:  python3 tools/check_layout.py          (build.py runs it and stops on any finding)
Checks every stylesheet in src/styles except tokens.css:
  margin, padding, gap, top/right/bottom/left/inset  -> 0, auto, %, or spacing/layout tokens
  font-size, line-height                             -> type tokens (--fs-*, --lh-*)
  max-width / width of 480px or more                 -> layout tokens (--container, --narrow, --measure, ...)
Inside calc(), max(), min() and env() the same rule applies to every length; plain numbers (multipliers) are fine.
Breakpoints: only 768, 1024 and 1280 (max-width 767, 1023, 1279).
Also checks inline style="" attributes in src/ HTML and JS and in build.py for the same properties.
"""
import re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
STY = ROOT / "src" / "styles"
SPACE = re.compile(r"^(margin|padding|gap|row-gap|column-gap|top|right|bottom|left|inset)(-.+)?$")
TYPE = {"font-size", "line-height"}
WIDE = {"max-width", "width", "min-width"}
OK_SPACE = r"--sp-\d|--gutter|--col-gap|--section|--section-compact|--header|--areabar|--control|--control-sm"
OK_TYPE = r"--fs-[\w]+|--lh-[\w]+"
OK_WIDE = r"--container|--narrow|--measure|--doc|--rail|--gutter|--sp-\d|--col-gap"
BREAKPOINTS = {("min","768"),("min","1024"),("min","1280"),("max","767"),("max","1023"),("max","1279")}
LEN = re.compile(r"(?<![\w-])(-?\d*\.?\d+)(px|rem|em|vw|vh|dvh|ch)\b")

def bad_value(prop, val):
    v = re.sub(r"!important", "", val).strip()
    if prop in TYPE:
        ok = OK_TYPE
        if re.fullmatch(r"inherit|normal|initial", v): return None
    elif prop in WIDE:
        ok = OK_WIDE
        m = LEN.search(v)
        if not m or m.group(2) != "px" or float(m.group(1)) < 480: return None
    else:
        ok = OK_SPACE
    # strip allowed var(...) uses; anything left with a unit, or a bare unitless number for type, is a finding
    rest = re.sub(r"var\(\s*(" + ok + r")\s*\)", "", v)
    rest = re.sub(r"env\([^,()]+", "", rest)
    if re.search(r"var\(", rest): return "uses a variable that isn't a " + ("type" if prop in TYPE else "layout") + " token"
    m = LEN.search(rest)
    if m and float(m.group(1)) != 0: return f"raw {m.group(0)}"
    if prop in TYPE and re.search(r"(?<![\w.-])\d*\.?\d+(?![\w%])", rest) and not re.fullmatch(r"\s*", rest): return "raw number"
    if prop in TYPE and re.search(r"\d+%", rest): return "raw %"
    if "clamp(" in v: return "clamp() sizes are not tokens"
    return None

def scan_css(path):
    out = []
    text = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), path.read_text(encoding="utf-8"), flags=re.S)
    for i, line in enumerate(text.split("\n"), 1):
        for bp in re.findall(r"@media[^{]*", line):
            for w in re.findall(r"(min|max)-width\s*:\s*(\d+)px", bp):
                if w not in BREAKPOINTS: out.append(f"{path.relative_to(ROOT)}:{i}: breakpoint {w[0]}-width:{w[1]}px  (use 768, 1024 or 1280)")
        line = re.sub(r"@media[^{]*", "", line)
        for prop, val in re.findall(r"([a-z-]+)\s*:\s*([^;{}]+)", line):
            if not (SPACE.match(prop) or prop in TYPE or prop in WIDE): continue
            if prop.startswith("--"): continue
            why = bad_value(prop, val)
            if why: out.append(f"{path.relative_to(ROOT)}:{i}: {prop}:{val.strip()}  ({why})")
    return out

def scan_inline():
    out = []
    for p in list((ROOT / "src").rglob("*.html")) + list((ROOT / "src" / "scripts").glob("*.js")) + [ROOT / "build.py"]:
        for i, line in enumerate(p.read_text(encoding="utf-8").split("\n"), 1):
            for style in re.findall(r"style=['\"]([^'\"]*)['\"]", line):
                for prop, val in re.findall(r"([a-z-]+)\s*:\s*([^;]+)", style):
                    if (SPACE.match(prop) or prop in TYPE) and bad_value(prop, val):
                        out.append(f"{p.relative_to(ROOT)}:{i}: inline {prop}:{val.strip()}")
    return out

def main():
    found = []
    for p in sorted(STY.glob("*.css")):
        if p.name != "tokens.css": found += scan_css(p)
    found += scan_inline()
    for f in found: print(f)
    print(f"check_layout: {len(found)} value(s) not from tokens" if found else "check_layout: every value is a token")
    return 1 if found else 0

if __name__ == "__main__": sys.exit(main())
