#!/bin/bash
# Fresh database, fresh PostgREST, then the browser flow
cd ${SAAZ_TEST:-$(cd "$(dirname "$0")" && pwd)} && ./reset.sh >/dev/null 2>&1
pkill -x postgrest; sleep 0.5
(setsid nohup /tmp/pgrst/postgrest pgrst.conf > pgrst.log 2>&1 &)
rm -rf ${SAAZ_TEST:-$(cd "$(dirname "$0")" && pwd)}/storage/*; sleep 1.5
cd ${SAAZ_TEST:-$(cd "$(dirname "$0")" && pwd)} && timeout 400 python3 flow.py ${1:-390}
