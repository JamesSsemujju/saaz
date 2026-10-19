# Saaz tests

These run against a local copy of the Saaz stack, never the live project.

| File | What it checks | Last result (17 Oct 2026) |
|---|---|---|
| `db_marketplace_test.py` | Every database rule: garages, listings, garage line, reviews, verify, offers, deals, access rules | 72 passed |
| `db_audit_fixes_test.py` | Part 6 fixes: Uganda only, garage needs an Active member, one notice, re-queue, East Africa Time | 10 passed |
| `browser_flow_test.py <width>` | The whole journey in Chromium: garage applies, admin approves, seller lists, garage reviews, admin approves, buyer offers, deal completes, plus Uganda-only, EAT, history pages, asterisks, invite link | 184 passed at 390 and 1280 px (19 Oct 2026), including staying in Admin |
| `layout_audit.py <site> <car ref> <out> [--signed-in]` | The layout rules at 360 to 1440 px, with grid-overlay screenshots: one left edge, equal card rows, one control height, 44 px touch targets on phones, search on the first screen, price within two screens | 68 of 68 renders pass (18 Oct 2026) |
| `db_reports_test.py` | Part 16 reports: access, every Inventory and Funnel number reconciled with a hand count, the Kampala-day rule, drill-downs, groups, sort, pages, compare, export log | 58 passed (19 Oct 2026) |
| `db_reports_2_test.py` | Part 17: Inspections and garages, Deals and sales, the learned gap and its fallbacks, each reconciled with a hand count | 43 passed (19 Oct 2026) |
| `browser_reports_2_test.py <site> <width>` | The two new reports in Chromium: key numbers, garage rows and their drill-downs, time-outs, learned gaps, expected prices, grouped export, filters kept | 18 passed at 1280, 19 at 390 |
| `db_reports_speed_test.py` | Report speed at 20,000 listings, 600,000 views, 30,000 offers | slowest call 1.76 s with all four reports (limit 2 s) |
| `browser_reports_test.py <site> <width>` | Admin, Reports in Chromium: access, rail, drill-downs, groups, sort, CSV name, header and columns, export log, filters kept between reports, charts, empty state, phone cards | 32 passed at 390, 31 at 1280 |
| `db_build_test.py` | Part 18 Build Assistant: who can use it, the switch, element links must match the text, idempotent saves, status rules, leases, retries, two agents at once, dependencies, conflicts shown to the agent, versions, append-only history, privacy | 70 passed (19 Oct 2026) |
| `browser_build_test.py <site> <width>` | The Build Assistant in Chromium: who sees it, selecting without the page reacting, one comment with several tags, cursor placement, no duplicates, removing tags, drafts across pages and reloads, Cancel confirm, unknown refs refused, save and queue, chat, tasks, agent questions and answers, touch (tap then Comment), the switch | 47 passed at 1280, 51 at 390 (19 Oct 2026) |
| `text_overflow_audit.py <docs> [stress]` | Text spilling out of its box on every page at 4 widths, optionally with 43-character values everywhere | 0 problems |

Stack (in `stack/`): Postgres 16, PostgREST 12.2.3 (`pgrst.conf`), `stub.sql` (stand-in for Supabase roles, `auth.users`, `auth.uid()`, storage), `fakesb.py` (stand-in for Supabase Auth and Storage on port 54321), `reset.sh` (fresh database with every `supabase/*.sql` part), `sync.sh` (build and point the site at the local stack), `run.sh` (reset, then the browser flow).
Set `SAAZ_TEST` to the folder holding the stack files and the site copy. Python needs `psycopg2-binary`, `playwright` and `Pillow`.
