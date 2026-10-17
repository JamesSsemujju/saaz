# Saaz tests

These run against a local copy of the Saaz stack, never the live project.

| File | What it checks | Last result (17 Oct 2026) |
|---|---|---|
| `db_marketplace_test.py` | Every database rule: garages, listings, garage line, reviews, verify, offers, deals, access rules | 72 passed |
| `db_audit_fixes_test.py` | Part 6 fixes: Uganda only, garage needs an Active member, one notice, re-queue, East Africa Time | 10 passed |
| `browser_flow_test.py <width>` | The whole journey in Chromium: garage applies, admin approves, seller lists, garage reviews, admin approves, buyer offers, deal completes, plus Uganda-only, EAT, history pages, asterisks, invite link | 88 passed at 320, 390 and 1280 px |
| `text_overflow_audit.py <docs> [stress]` | Text spilling out of its box on every page at 4 widths, optionally with 43-character values everywhere | 0 problems |

Stack (in `stack/`): Postgres 16, PostgREST 12.2.3 (`pgrst.conf`), `stub.sql` (stand-in for Supabase roles, `auth.users`, `auth.uid()`, storage), `fakesb.py` (stand-in for Supabase Auth and Storage on port 54321), `reset.sh` (fresh database with every `supabase/*.sql` part), `sync.sh` (build and point the site at the local stack), `run.sh` (reset, then the browser flow).
Set `SAAZ_TEST` to the folder holding the stack files and the site copy. Python needs `psycopg2-binary`, `playwright` and `Pillow`.
