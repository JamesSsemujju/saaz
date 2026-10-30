#!/bin/bash
set -e
# Rebuild and copy the site into the test server with local database settings.
# The live Supabase address is swapped for the local stand-in everywhere it appears: assets/config.js and each page's security policy.
cd ${SAAZ_REPO:-$(cd "$(dirname "$0")/../.." && pwd)} && python3 build.py | tail -1
LIVE=$(python3 -c 'import json;print(json.load(open("src/data/site.json"))["supabaseUrl"])')
rm -rf ${SAAZ_TEST:-$(cd "$(dirname "$0")" && pwd)}/srv/saaz && cp -r docs ${SAAZ_TEST:-$(cd "$(dirname "$0")" && pwd)}/srv/saaz && cd ${SAAZ_TEST:-$(cd "$(dirname "$0")" && pwd)}/srv/saaz && LIVE="$LIVE" python3 -c '
import os, re, pathlib
live = os.environ["LIVE"]; ws = live.replace("https://", "wss://")
for f in list(pathlib.Path(".").rglob("*.html")) + list(pathlib.Path(".").rglob("config.js")):
    t = f.read_text(); t = t.replace(ws, "ws://127.0.0.1:54321").replace(live, "http://127.0.0.1:54321")
    t = re.sub(r"\"supabaseAnonKey\": \"[^\"]*\"", "\"supabaseAnonKey\": \"LOCALANON\"", t); f.write_text(t)'
