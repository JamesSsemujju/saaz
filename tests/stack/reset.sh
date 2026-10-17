#!/bin/bash
# Fresh stand-in database with the live schema plus the marketplace parts
P="psql -h /var/tmp/saazpg -p 5433 -U postgres -q -v ON_ERROR_STOP=1"
D=${SAAZ_TEST:-$(cd "$(dirname "$0")" && pwd)}
S=${SAAZ_REPO:-$(cd "$(dirname "$0")/../.." && pwd)}/supabase
$P -c "drop database if exists sb with (force)" -c "create database sb" 2>&1 | grep -v NOTICE
$P -d sb -f $D/stub.sql -f $S/schema.sql 2>&1 | grep -v NOTICE
for f in 1_tables 2_core 3_reviews_deals 4_access 5_hardening 6_audit_fixes 7_inspection_wording 8_report_privacy 9_invites 10_admin_mfa 11_admin_on_behalf 12_access_and_signout 13_roles_inside_teams 14_inspection_ids_and_scopes; do $P -d sb -f $S/marketplace_$f.sql 2>&1 | grep -v NOTICE; done
