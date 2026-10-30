# Saaz security audit and hardening (30 Oct 2026)

Scope: sign-in and sessions, admin authenticator, password and reset flows, row security, every database function, storage, the edge function, the pages (injection, framing, outside scripts), secrets, grants, logging. The live project was only read. Every fix was applied and tested on the local copy (Postgres 16 with all parts, PostgREST 12.2.3). Nothing is live until James applies part 21, redeploys `invite-user` and ships the site.

Labels: **Confirmed** means a test reached the data or changed state across a boundary (on the local copy, and the same rule or grant was read on live). **Code** means the code path is certain but there is no live data to reach yet.

## Findings

| # | Finding | Severity | Status | Fix |
|---|---|---|---|---|
| 1 | Vehicle register readable by any signed-in account: every VIN, make, model, import mileage, including cars never listed and Saaz's imports. Sign-up is free, so this is effectively public | Medium | Confirmed (local: buyer, seller and other garage owner read an unlisted import VIN; live policy `signed-in read vehicles` is `auth.uid() is not null`) | Part 21: admins only. The app reads it only in Admin |
| 2 | Saaz's comments on any inspection report (support or object, with the reason) readable by anyone through `opinions_of`, including unpublished reports, given the report id | Medium | Code (callable by visitors on live; no unpublished report with a comment exists yet) | Part 21: internal only. Seller, garage and admin still get them through the report functions |
| 3 | Odometer history readable by anyone, signed in or not | Low | Confirmed by policy (`true` on live, 0 rows live today; local visitor read all rows) | Part 21: admins only. The public report still shows the odometer |
| 4 | A car that isn't public (draft, in inspection) could be saved by anyone with its id, and its saves, views and offers counted for anyone through `listing_stats` | Low | Confirmed (local: visitor read `saves: 3` for a car awaiting inspection) | Part 21: saves only for public cars; figures only for public cars, the seller and admins |
| 5 | Visitors and signed-in people held insert, update, delete and truncate on every table | Low (defence in depth) | Confirmed on live grants; not exploitable because row security has no write policy (writes refused, tested over HTTP) | Part 21: revoked, and default privileges set so new tables don't get them |
| 6 | Internal helpers callable by anyone: `tick`, `setting`, `saaz_stance`, `model_sales`, `require_full_admin`, two trigger functions | Low | Confirmed (visitor called `tick` locally and on the live grant list) | Part 21: internal only; `tick` stays for signed-in people (the app runs it on page load, there is no scheduler) and skips when already running |
| 7 | Invite emails: `invite-user` passed any redirect address from the caller into the email link | Low (Supabase only follows addresses on the Auth redirect list) | Code | Redirect accepted only back to the Saaz site |
| 8 | No Content Security Policy; QR code script loaded from cdnjs; five inline `onclick`/`onchange` handlers; site could be framed | Low (no injection found, so this is the second line) | Confirmed | One policy stamped on every page in `build.py` (scripts from this site only, inline scripts by hash, no plugins, forms and base to this site); config moved to `assets/config.js`; QR library self-hosted; handlers replaced by `data-after`, `data-print`, `data-jump`; Saaz refuses to run in a frame; referrer policy |
| 9 | Notification links rendered as `href` without checking the scheme | Informational | Not exploitable: every link is written by database functions as `#/...` (checked every call site in parts 1 to 20 and the 12 live rows) | `S.safeHref` in the inbox, and a database rule that a link must be a Saaz page |
| 10 | Seven functions without a fixed search_path (advisor) | Informational | Confirmed | Four fixed. Three report helpers left on purpose: fixing them stopped Postgres inlining them and made reports 50% slower (2.38 s, over the 2 s limit). They use no tables and nobody outside can create objects in public |

## Checked and sound

- **Admin:** `is_admin` needs the password and the pinned authenticator within 12 hours, checked in the database; no client flag can grant it. A forged admin call over HTTP gets "Admins only." Failed checks are logged.
- **Sessions and sign-out:** every write calls `require_user`, which needs the session row, so sign-out ends a stolen token's write access at once. Sign-out is global, clears the browser's copies and lands on the public listings for every role.
- **Password reset:** the reply never says whether an email has an account. Reset and invite links work once.
- **Ownership:** 1,019 calls of every callable function by a visitor, a buyer, a seller and the owner of an unrelated garage, with other people's ids: nothing changed and nothing of anyone else's came back (after part 21).
- **Roles:** buyers can't reach seller or admin functions; sellers manage only their own cars; garages are invitation-based and an owner can invite only into a certified garage they own; inspectors see only jobs given to them; reports are public only for the current report of a public car.
- **Injection:** every free-text field filled with markup and opened on 33 screens across all roles with the policy switched off: all shown as text. Report sorting and grouping use fixed lists with quoted identifiers.
- **Storage:** uploads only into the person's own folder; 2 MB images only.
- **Secrets:** only the anon key ships (decoded: role anon). The service key stays in Supabase function secrets.
- **Build Assistant schema:** not served by the API.

## Tests (local, 30 Oct 2026)

New: `db_security_test.py` (76: function sweep, table reads, grants, named cases, visitor function allow-list, search_path), `api_security_test.py` (109, over HTTP with signed tokens and a forged one), `browser_csp_test.py` (10), `browser_xss_test.py` (34). Without part 21 the security test fails 19 checks; with it, all pass.

All 14 database suites pass with part 21 (532 checks), and report speed is 1.55 s (limit 2 s). All browser suites pass with the security policy on: flow 184 at 1280 and 390, sell 44 and 44, Build Assistant 48 and 52, admin preview 24 and 22, design 28, cards 110, reports 31 and 32, reports 2 18 and 19, demo journey 41 at 1280 and 390, policy 10, injection 35; text overflow 0 problems on 44 pages at 4 widths. Two test waits used `wait_for_function`, which the policy blocks inside the test browser; they now wait on a selector instead.

## For James to do

1. **Apply part 21** (`supabase/marketplace_21_security_hardening.sql`) after reading it. It runs in one go and is safe to repeat. Then run the two check queries at its end, and the advisor.
2. **Redeploy `invite-user`** (the redirect fix). Optional: set the secret `SAAZ_SITE_URL` if the site address changes.
3. **Ship the site** (the zip). The pages now carry the security policy; the app needs `assets/config.js`, which the build writes.
4. **Supabase dashboard, Authentication:**
   - turn on leaked password protection (advisor warning);
   - set the minimum password length to 8 (the site already asks for 8) and require letters and digits;
   - check the Redirect URLs list has only `https://jamesssemujju.github.io/saaz/**` (and localhost only if you test locally);
   - keep email confirmation on; check the rate limits for sign-up, sign-in, OTP and email sends (defaults are fine for now);
   - JWT expiry: 3600 s is fine; sign-out already ends access at once.
5. **Part 20** (photos must be the seller's own uploads) is still not live. Apply it with part 21 if you're happy with it.

## Remaining risks

- **Sign-in is kept in the browser's storage, not an HttpOnly cookie.** That needs a server, which GitHub Pages doesn't have. The policy, the escaping tests and the short session checks reduce the risk; the full fix is hosting with a server (for example Cloudflare Pages Functions) later.
- **Headers:** GitHub Pages can't send security headers, so framing protection is the script check, and the policy is a page tag (it can't use `frame-ancestors` or report violations).
- **View counts** can be inflated by a visitor sending made-up device names to `record_view`. Only the seller's and Saaz's view figures are affected. A fix needs a per-address limit (Supabase passes the caller's address); proposed for a later part.
- **No app-level rate limits** on messages and saves beyond the business rules; Supabase limits sign-in and email.
- Not tested in Safari or on a real phone.
