# Saaz security checklist (30 Oct 2026, second pass)

Each item of the 8-part checklist, checked against the real architecture: a static site on GitHub Pages, with Supabase handling the database, API, sign-in and storage. Sessions are bearer tokens kept by supabase-js, not cookies. Everything below was tested locally. "Live" means confirmed on the production project or the deployed commit.

Status words: **Live** (verified in production), **Ready** (fixed and tested, waiting for James to apply, deploy or ship), **Manual** (a dashboard setting only James can change), **Accepted** (a remaining risk, with the reason).

## 1. Secrets and API

| Item | Finding | Status |
|---|---|---|
| Keys in the site | Only the Supabase anon key (decoded: role `anon`), which is public by design. Row security and grants protect the data | Live |
| Git history | All 50 commits scanned: no service key, `sb_secret`, private key, cloud or GitHub token, database URL or password. The only JWTs are the anon key (90 copies). The three "secrets" found are local test values (a test TOTP seed, the demo password, the local JWT secret), none of them used on live | Live. No rotation needed |
| Service key | Only in Supabase function secrets (`invite-user` reads it from the environment) | Live |
| Third-party APIs | NHTSA vPIC (free, no key, read-only). The QR library is self-hosted. No paid APIs | Live |
| Spending | Supabase organisation is on the Free plan: hard quotas and no overage billing, so there are no surprise costs (abuse would pause the project, not bill it). If you upgrade, turn the Spend Cap on | Live |

## 2. Authentication and access control

| Item | Finding | Status |
|---|---|---|
| Admin and privileged actions | Checked in the database (`is_admin`: password and pinned authenticator within 12 hours). The page only hides links | Live |
| Every sensitive action | 1,026 calls of every callable function by a visitor, a buyer, a seller and an unrelated garage owner, using other people's ids: nothing changed and nothing leaked. The same boundary was tested over HTTP with signed and forged tokens (109 checks) | Live (part 21 applied) |
| Escalation | Roles come only from database tables (admins, garage members), never from user metadata. Forged admin calls get "Admins only." | Live |
| Bypassing the page | Tables are read-only to the API (no write grants); every write is a checked function | Live |

## 3. Input and injection

| Item | Finding | Status |
|---|---|---|
| SQL injection | All queries are parameterised by PostgREST and plpgsql. The only dynamic SQL (report sort and group) uses fixed lists with quoted identifiers | Live |
| Command injection | No server-side shell; the edge function runs no commands | Live |
| XSS | All database text goes through `S.esc`; data links through `S.safeHref`; the database refuses non-Saaz notification links. Markup typed into every field stayed as text on 33 screens across all roles (with the policy off, to test the escaping itself) | Live |
| Server-side validation | Every rule (VIN, plate, price, photos, offers) is in the database functions; the page's checks are convenience only | Live |

## 4. Database

Row security is on for all 23 tables, with read policies only. Part 21 is live (checked today): the vehicle register and odometer history are admin-only, there are no table write grants, the internal helpers are locked, and the notification link rule is in place. The advisor now lists only the three report helpers kept fast on purpose. Visitors can call exactly the 24 agreed functions. **Live.**

## 5. Request protection

| Item | Finding | Status |
|---|---|---|
| Sign-in, sign-up, reset, OTP, MFA | Rate limited by Supabase Auth (per IP and per user; the built-in email sender is capped at a few emails an hour project-wide) | Live (defaults) |
| App writes (messages, offers, applications, invites, saves, views, look-ups) | Had no limit. **Part 22** adds one check before every API write, with limits in one table, per account or per network address. Over the limit, the API answers 429. Tested over HTTP (13 checks), plus all suites with the limits on | Ready |
| Found while testing part 22 | PostgREST runs read-only functions in read-only transactions, so a naive limit would have broken every look-up on the site. The check skips those, and the three look-ups used to walk through inspection numbers and report codes are marked volatile so they are counted | Ready |
| CSRF | Not applicable: no cookie authentication. The token is sent in a header that other sites can't make the browser add. No CSRF tokens added on purpose | Live |
| CORS | The database API allows any origin (Supabase's design for bearer tokens; the token, not the origin, authorises). The `invite-user` function now allows only the Saaz site | Ready (redeploy) |
| Edge function abuse | `invite-user`: 20 invite emails an hour per sender; redirect only to Saaz; internal errors not returned | Ready (redeploy) |

## 6. Uploads

| Item | Finding | Status |
|---|---|---|
| Type and size | Bucket allows webp, jpeg, png only, 2 MB. SVG and HTML are refused | Live |
| Names and paths | Part 22: only `<your id>/<letters and digits>.<webp/jpg/png>`. No `..`, no sub-folders, no odd characters | Ready |
| Quantity | Part 22: 300 photos per account | Ready |
| Whose photos | Part 20: a listing may only use photos the seller uploaded | Ready since 23 Oct (not applied) |
| Content | The app re-encodes every photo to WebP in the browser before uploading. The server checks the declared type, not the bytes; files are served from Supabase's domain with `nosniff`, so a disguised file can't run as a page on Saaz | Accepted (a byte check needs an upload function; see risks) |

## 7. Hosting

| Item | Finding | Status |
|---|---|---|
| HTTPS | GitHub Pages serves `github.io` over HTTPS, and `github.io` is on browsers' HSTS preload list (Likely; this session can't reach github.io to read headers). Check "Enforce HTTPS" is ticked in the repo's Pages settings | Manual check |
| Security policy, referrer, framing | On every page in the deployed commit c4e314a (checked in the repo): scripts only from the site, no plugins, forms and base to the site; referrer policy; Saaz refuses to run inside a frame | Live |
| HSTS and frame headers | GitHub Pages can't send custom headers; HSTS comes from the preload list; framing is blocked by script | Accepted |
| Cookies | Saaz sets none; the session is kept by supabase-js in browser storage | Accepted (HttpOnly needs a server) |
| Debug and errors | No debug flags or console logging in the app. Database errors that aren't Saaz's own messages are now replaced by a plain sentence (constraint names and internal paths were reaching the page). The edge function no longer returns internal errors | Ready (ship) |
| Dependencies | `npm audit`: supabase-js 2.45.4 bundled auth-js with GHSA-8r88-6cj9-9fh5 (low; Saaz never passes user-typed ids to the affected calls). Updated to 2.50.0, the first release with the fix, and pinned the edge function to the same version. qrcodejs: no advisories | Ready (ship and redeploy) |

## 8. Verification

Local, 30 Oct 2026, with parts 21 and 22:
- **Database suites:** all 15 pass, including security (83) and teams (57). Report speed is 1.36 s, under the 2 s limit.
- **API tests:** security 109 and request limits 13.
- **Browser suites:**
  - flow 184 at 1280 and 390;
  - sell 44 and 44;
  - Build Assistant 48 and 52;
  - admin preview 24 and 22;
  - design 28;
  - cards 110;
  - reports 31 and 32;
  - reports 2 18 and 19;
  - policy and error messages 13;
  - injection 35;
  - demo journey 41 at both widths;
  - text overflow: 0 problems.

The local storage stand-in now has Supabase's real columns and grants. Before, two upload checks were passing for the wrong reason (a missing column). They now reach the real policies.

## For James

1. **Apply part 22** (`supabase/marketplace_22_rate_limits_and_uploads.sql`) in the SQL Editor, then run the checks at its end. Part 20 can go with it.
2. **Redeploy `invite-user`.** The live version is still the 17 Oct one, without the redirect fix.
3. **Ship** the full zip (supabase-js 2.50.0, error messages, tests).
4. **Supabase dashboard:**
   - Authentication: turn on leaked password protection; set the minimum password length to 8 with letters and digits; keep only the Saaz site in Redirect URLs; review Rate Limits.
   - Optional: turn on CAPTCHA (Cloudflare Turnstile) for sign-up and sign-in. That also needs a small change in the sign-up and sign-in forms, so ask before turning it on.
5. **GitHub, Settings, Pages:** confirm "Enforce HTTPS" is ticked.
6. **After part 22 is live,** I can confirm from here that the hook is set (read-only). The check reads Cloudflare's own address header first, which Cloudflare sets and a visitor can't fake (Likely: Supabase's API sits behind Cloudflare). If it's missing, it falls back to X-Forwarded-For, which a script could vary to dodge the per-visitor limit; signed-in limits are per account and can't be dodged that way. I'll confirm which header arrives once part 22 is live.

## Remaining risks

- Sign-in tokens live in browser storage (no HttpOnly cookie without a server). The security policy and the escaping tests are the protection.
- Read-only database calls (browsing, reports) aren't counted by the request limit, only by Supabase's platform limits. Abuse there costs quota, not data.
- Upload bytes aren't checked on the server, and nothing scans for malware. The risk is low: images only, served from another domain with `nosniff`, and re-encoded by the app.
- No CAPTCHA yet.
- Not tested in Safari or on a real phone.
