# Saaz system audit

Naming (17 Oct 2026): what the code and database call a "review" is shown to people as a **Saaz inspection** and its **inspection report**. Table and status names stay `reviews`, `review_booked` to avoid a risky rename.

Date: 17 Oct 2026 (EAT). Auditor: Claude, for James Ssemujju.
Folder note: these documents live in `project-docs/` because `docs/` is the built website and `build.py` wipes it on every build.

## How this audit was done

| Evidence | What it covers |
|---|---|
| Repository (`build.py`, `src/`, `supabase/`, `tools/`) read in full | Code, routes, schema, access rules |
| Live Supabase project `dkxyvlkhpnajbpethwqb`, read-only SQL on 17 Oct 2026 | Real tables, row counts, functions, rules, timezone, extensions |
| Supabase security advisor, 17 Oct 2026 | Security warnings |
| Google public DNS for saazinvestmentsltd.com, 17 Oct 2026 | Mail server, SPF, DKIM, DMARC, reverse DNS |
| Local test stack: Postgres 16 + PostgREST 12.2.3 + a stand-in for Supabase Auth and Storage, Playwright Chromium | All tests below. Not the live project |

Nothing was written to production during this audit. The fixes that need the database are in `supabase/marketplace_6_audit_fixes.sql`, waiting for approval.

## Architecture as built

| Layer | What it is | Evidence |
|---|---|---|
| Public website | Static HTML built by `build.py` (Python 3.8+, no dependencies) from `src/` into `docs/`, served by GitHub Pages at jamesssemujju.github.io/saaz/ | `build.py`, `src/pages`, `src/modules`, `src/data/modules.json` |
| Marketplace app | One page at `/app/`, hash routes (`#/…`), plain JavaScript in 5 files, no framework | `src/pages/app.html`, `src/scripts/app-*.js` |
| Backend | Supabase: Postgres 17 (UTC clock), Auth, Storage, PostgREST. All business logic is in 80 Postgres functions; tables are read-only to the website | `supabase/marketplace_*.sql`; live: 21 tables, 80 functions |
| Access control | Row-level security on all 21 tables (verified live); functions check the caller | `marketplace_4_access.sql`, `_5_hardening.sql` |
| Files | Supabase Storage bucket `car-photos` (public read; sellers write to their own folder; admins write anywhere) | live: 5 storage rules, 4 photos |
| Email | None working. See F-01 | `project-docs/email-and-notifications.md` |
| Scheduled work | None. Garage time-outs and review expiry run when someone signs in (`tick()`) | live: no `pg_cron` |
| Edge Functions | One written (`invite-user`), not deployed | `supabase/functions/invite-user/index.ts` |
| External APIs | NHTSA vPIC VIN decoder, called from the visitor's browser | `src/scripts/vin.js` |
| Secrets | Only the public anon key is in the site. No service key anywhere in the repo (checked) | `src/data/site.json` |
| Deployment | `tools/ship.sh` on James's Mac: unzip, build, commit, push to `main` | `tools/ship.sh` |
| Monitoring, backups | None configured by Saaz. Supabase plan backups not checked | F-20 |

Live data on 17 Oct 2026: 1 account (admin), 1 garage (Musa Body, certified, no team member yet, owner invite waiting), 1 Saaz-owned car (SZ-00001, waiting for review with an empty garage line), 0 reviews, 0 deals.

## Status of every feature

Categories: 1 = built and verified, 2 = built but incomplete, 3 = screen only or placeholder, 4 = backend with no usable screen, 5 = missing, 6 = blocked by configuration or credentials.

| Feature | Cat. | Evidence and note |
|---|---|---|
| Sign up, sign in, sign out | 1 | Browser tests, local stack. Live sign-in by James confirmed earlier |
| Email confirmation on sign-up | 6 | Default Supabase email only reaches team members (F-01) |
| Forgot password (reset email) | 6 | Screen and link handling built and tested locally; email delivery blocked (F-01), redirect URL not confirmed (F-02) |
| Change password while signed in | 1 | Added in this audit (Account page) |
| Change email | 6 | Added in this audit; needs email (F-01) |
| Profile (name, mobile) | 1 | |
| Mobile verification by SMS | 3 | Placeholder; setting `require_phone_verified` is off (F-23) |
| VIN decoder (public) | 1 | Verified live by James (2017 Toyota RAV4) |
| Vehicle record per VIN, odometer history | 1 | Database tests |
| List a car (VIN first, photos, draft, submit) | 1 | Browser tests |
| Garage line (one garage at a time, nearest first, pass, decline, time-out) | 2 | Works; gaps F-04, F-06, F-10 |
| Garage to seller messages, contacts hidden until agreed | 1 | Database and browser tests |
| Saaz review (12 checks, body map, odometer, issue) | 1 | |
| Review report document, public Verify, tamper detection | 1 | |
| Inspection photos and evidence inside the review | 5 | The review has no photo upload (F-24) |
| Admin approval of listings, changes, reject, unlist, void | 1 | |
| Offers, offer rules, auto-reject, counters, agreement, completion | 1 | |
| Demand counts and What's selling | 1 | |
| Saaz-owned cars and Saaz imports | 1 | |
| Garage application and admin decision | 1 | |
| Garage added directly by admin | 2 | Works; owner without an account depends on invite email (F-01, F-21) |
| Garage teams (owner, inspector) | 2 | Same invite dependency |
| Inspection booking by a buyer for any car (Saaz Check page) | 5 | Public page promises it; no workflow (F-11) |
| Book a service with a certified garage (meeting decision) | 5 | Not built (F-11) |
| Import desk, landed-cost estimate in UGX | 3 | Public page only (F-12) |
| Finance referrals | 3 | Public page only (F-12) |
| Enquiries, support, report a listing | 5 | Not built (F-13) |
| In-app inbox | 1 | |
| Email and SMS delivery, delivery records, failures | 5/6 | F-01, F-14 |
| Audit trail per car, garage, account, deal | 1 | Added in this audit for garage and account |
| Admin navigation | 1 | Regrouped in this audit |
| Old public car list (`cars` table) | 3 | Unused since the marketplace; table empty (F-18) |

## Findings

Priority: P0 blocks launch, P1 blocks a business process, P2 risk or quality, P3 tidy-up.

| ID | Finding | Evidence | Impact | Priority | Fix | Verify by |
|---|---|---|---|---|---|---|
| F-01 | No working email. Supabase's built-in sender only delivers to members of the project's team | Supabase docs, auth-smtp page; jayssemujju@gmail.com received nothing | Sign-up confirmation, password reset, invites and email change can't reach customers | P0 | Add a custom SMTP sender in Supabase (Authentication, Emails, SMTP). Options in the email document. Needs a mailbox password from James, entered in the dashboard only | Send a reset to a Gmail address outside the team; check inbox and headers |
| F-02 | Auth Site URL and redirect URLs not confirmed | Can't be read from here | Links in emails may open the wrong site | P0 | Set Site URL `https://jamesssemujju.github.io/saaz/app/` and add it to Redirect URLs | Click a reset link; it opens "Set a new password" |
| F-03 | Kenya was selectable in sign-up, listing, garage forms, browse and What's selling; database still accepts Kenya | Code; live regions table has 5 Kenyan regions | Breaks the Uganda-only rule | P1 | Screens: fixed (Uganda only, UGX, no country chooser). Database: guard in part 6 | Browser tests (Kenya absent); database test F-03 |
| F-04 | A certified garage with nobody on its team can be put in play, and the car waits 24 hours for nothing | `next_garage()` didn't check the team | Delays | P1 | Part 6: only garages with an Active member | Database test F-04 |
| F-05 | Admins told twice when the line is empty on a Saaz-owned car | Live: 4 notices for 2 events | Noise | P3 | Part 6 | Database test F-05 |
| F-06 | Cars with an empty line stay stuck when a garage becomes ready | Live: SZ-00001 stuck; Musa Body certified after | Process stops until an admin restarts the line | P1 | Part 6: re-queue automatically when a garage is certified or its first member signs in | Database test F-06 |
| F-07 | Dates use UTC; Uganda is UTC+3 | Live `TimeZone = UTC` | Review "valid until" and view days can be a day off for 3 hours a night | P2 | Screens now show EAT. Part 6 sets Africa/Kampala on the date functions | Browser test ("EAT"); database test F-07 |
| F-08 | Sign-up said "That email already has an account" | Code | Anyone could check if an email uses Saaz | P2 | Fixed: same wording either way. Fully closed only when "Confirm email" is on | Browser test |
| F-09 | No change password or change email while signed in | Code | Users need the reset email instead | P2 | Added to Account page | Browser test (mismatch check); live test after F-01 |
| F-10 | No scheduler: garage time-outs only happen when someone signs in | No pg_cron | A car can sit with an unresponsive garage | P2 | Enable `pg_cron` and run `tick()` every 15 minutes (needs approval) | Check job runs |
| F-11 | "Saaz Check" public page offers inspections to buyers for any car; the app only reviews cars being sold. Meeting decision "book a service with listed shops" not built | Public page vs app | Promise without a process | P1 | Business decision needed (see module inventory) | |
| F-12 | Import desk and Finance are marketing pages with no workflow | Public pages | No lead capture | P2 | Decide scope; don't invent tax rates or lender terms | |
| F-13 | No enquiries, support or "report this listing" | Code | Buyers' only channel is an offer | P1 | Build an enquiry module (proposal in workflows) | |
| F-14 | Notices are stored with intended channels, but nothing records delivery or failure | `notifications.channels` only | Admins can't see failed emails | P1 | Email queue and delivery log, once F-01 is fixed | |
| F-15 | Leaked-password protection off | Supabase advisor | Weak passwords allowed | P3 | Dashboard switch (may need a paid plan) | Advisor clears |
| F-16 | Photo bucket accepts any file type and size in a seller's folder | Live bucket settings | Abuse, storage cost | P2 | Part 6: images only, 2 MB | Upload a PDF; refused |
| F-17 | Removing a photo from a listing leaves the file in storage | Code | Storage grows | P3 | Clean-up job later | |
| F-18 | Old `cars` table unused | Live: 0 rows | Confusion | P3 | Drop with approval | |
| F-19 | No rate limits on messages and offers beyond Supabase defaults | Code | Spam | P2 | Per-account limits in the functions | |
| F-20 | Backups and recovery not checked | Plan not visible here | Data loss risk | P1 | James checks the plan's backups in Supabase; write a restore note | |
| F-21 | Invite email function written, not deployed | Repo | Garage owners can't get a set-password link | P1 | Deploy after F-01 and approval | Invite a test address |
| F-22 | Public site says "Preview. Saaz is not trading yet" and every service is "planned", while the marketplace is live | `site.json`, `modules.json` | Mixed message | P2 | Business decision: launch wording | |
| F-23 | Mobile numbers aren't verified | Placeholder | Fake numbers | P2 | SMS provider (Africa's Talking or similar), later | |
| F-25 | Every issued, superseded or void review can be listed by anyone through the database API, including reviews of cars that were rejected, withdrawn or never went live. The report page itself needs the verification code, but the table read rule doesn't | `marketplace_4_access.sql`, rule "issued reviews public" | Garage notes and odometer readings of unlisted cars are exposed; reviews can be scraped in bulk | P1 (no live reviews yet, so nothing exposed today) | Read only through `review_document(code)` and `verify_review(code)` for the public; table rows only for the seller, the garage and admins; the public car page asks for its one current review. Changing a rule needs a "drop policy", so it goes through the SQL Editor after approval | Visitor lists reviews: gets none; the report link still works |
| F-24 | Review has no photo evidence | Review editor | Weaker reports | P2 | Add photo upload to the review (garage folder) | |

## What is not verified

- Anything against the live project beyond read-only queries: no live sign-up, reset or email test was possible (F-01).
- The Edge Function (no Deno here).
- `mail.saazinvestmentsltd.com` (DNS lookup rate-limited).
- Real phones on slow data.
