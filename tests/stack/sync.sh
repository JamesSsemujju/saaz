#!/bin/bash
# Rebuild and copy the site into the test server with local database settings
cd ${SAAZ_REPO:-$(cd "$(dirname "$0")/../.." && pwd)} && python3 build.py | tail -1
rm -rf ${SAAZ_TEST:-$(cd "$(dirname "$0")" && pwd)}/srv/saaz && cp -r docs ${SAAZ_TEST:-$(cd "$(dirname "$0")" && pwd)}/srv/saaz && cd ${SAAZ_TEST:-$(cd "$(dirname "$0")" && pwd)}/srv/saaz && python3 -c '
import re,pathlib
for f in pathlib.Path(".").rglob("*.html"):
    t=f.read_text(); t=re.sub(r"\"supabaseUrl\": \"[^\"]*\"","\"supabaseUrl\": \"http://127.0.0.1:54321\"",t); t=re.sub(r"\"supabaseAnonKey\": \"[^\"]*\"","\"supabaseAnonKey\": \"LOCALANON\"",t); f.write_text(t)'
