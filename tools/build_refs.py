#!/usr/bin/env python3
"""build_refs.py: the element names (data-ref) in the Saaz source, and where each is defined.

The Build Assistant names elements after the data-ref on their component. Before the coding agent acts on a comment,
it runs this to check that every tagged element still exists in the code:
    python3 tools/build_refs.py                 list every name and the files that define it
    python3 tools/build_refs.py header filter-panel   check these names: exit 1 if any is missing
A name that is missing (renamed or removed component) is reported to James through the task; the agent never
applies the comment to a different element.
"""
import re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
found = {}
for p in list((ROOT / "src").rglob("*.html")) + [x for x in (ROOT / "src" / "scripts").glob("*.js") if x.name != "build-assistant.js"]:
    for i, line in enumerate(p.read_text(encoding="utf-8").split("\n"), 1):
        for name in re.findall(r"data-ref=[\"']([a-z0-9-]+)[\"']", line):
            found.setdefault(name, []).append(f"{p.relative_to(ROOT)}:{i}")
want = [a.lstrip("/") for a in sys.argv[1:]]
if not want:
    for k in sorted(found): print(f"//{k:22} {', '.join(found[k])}")
    sys.exit(0)
missing = [w for w in want if w.split(">")[-1] not in found]
for w in want: print(("MISSING " if w in missing else "ok      ") + "//" + w + ("" if w in missing else "  " + ", ".join(found[w.split('>')[-1]])))
sys.exit(1 if missing else 0)
