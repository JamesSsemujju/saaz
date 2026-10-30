# Saaz engineering rules (30 Oct 2026)

Standing rules for every Saaz build session and every Build Assistant agent. `CLAUDE.md` at the repo root points here; `Saaz_BuildAssistant_2026-10-19.md` (runbook steps 5 and 6) and `Saaz_Skills_2026-10-30.md` name it. James's rules (no push, no deploy, no live database change without his approval in a live chat, no secrets) still come first.

## 1. Fix the pattern, not just the instance

When you find a problem, it is a sample of a pattern until proven otherwise. Before you call it fixed:

1. **Name the pattern.** Example: "a definer function returns data without checking the caller can see that row", not "listing_stats leaks saves".
2. **Search the whole codebase for it.** Every `supabase/marketplace_*.sql` part, every script in `src/scripts`, the build, the tests. Use the live grants and policies too (read-only), since the files and live can differ.
3. **Fix the cause where it is shared.** One helper, one rule in `build.py`, one database constraint, one default privilege, rather than a patch at each site. Example from 30 Oct 2026: the security policy is stamped on every page in `build.py write()`, so no page can be built without it.
4. **Add a check that fails if the pattern comes back.** A test that sweeps every function, page or table, not just the one you fixed. Example: `tests/db_security_test.py` fails when a new definer function is callable by visitors without being on its agreed list.
5. **Report the count.** "Found in 4 places, fixed in 1 shared place, checked by X." Say plainly if some instances are left and why.

Don't add abstractions the pattern doesn't need, and don't duplicate a component that already exists: extend it.

## 2. Security rules (from the 30 Oct 2026 audit)

| Area | Rule | Enforced by |
|---|---|---|
| Who may do what | The database decides. Every write is a `security definer` function that checks the caller first (`require_user`, `require_admin`, ownership). The page never decides | `db_security_test.py` function sweep (every function, called by outsiders with other people's ids) |
| Tables | Read through row security only. Visitors and signed-in people hold no insert, update, delete or truncate on any table, now or for new tables (part 21 default privileges) | `db_security_test.py` grants check; `api_security_test.py` over HTTP |
| New database functions | End each part with explicit grants: `revoke execute ... from public, anon` and grant only to who calls it from the app. Helpers used only by other functions get no grant at all. Always `set search_path` | Visitor allow-list and search_path checks in `db_security_test.py` |
| Data in replies | A definer function returns only what the caller may see (public car, own row, own garage's job, admin) | Leak check in the sweep (other people's emails, phones, messages, private VINs, unpublished reports) |
| Admin | Password and the pinned authenticator within 12 hours, checked in the database (`is_admin`). No bypass, no client-side flag | `db_access_test.py`, `db_admin_mfa_test.py` |
| Pages | Text from the database goes through `S.esc`. Links built from data go through `S.safeHref` (Saaz pages only). No inline script or `on...=` attributes: use `data-after`, `data-print`, `data-jump` and the handler in `app-core.js` | `browser_xss_test.py`, `browser_csp_test.py` |
| Scripts | Only from this site. Vendor a library into `src/scripts` (with its licence line) rather than loading it from a CDN | `browser_csp_test.py` |
| Settings and keys | Only the Supabase anon key ships in the site. The service key lives in Supabase function secrets | Grep in the security report; never paste keys in chat |
| Email links | Edge functions accept a redirect only back to the Saaz site | `invite-user/index.ts` |
| Request limits | Every API write passes `check_request` (part 22). A new function people could repeat (messages, offers, invites, look-ups) gets its own row in `public.request_limits`; everything else falls under the general limit. A look-up that must be limited is marked volatile (read-only calls can't be counted) | `api_rate_limit_test.py` |
| Error messages | Only Saaz's own `raise exception` messages (code P0001) reach the page; `S.friendly` replaces any other database or API error with a plain sentence. Edge functions never return internal errors | `browser_csp_test.py` |
| Libraries | Pinned versions, checked with `npm audit` before each security pass; the edge function uses the same supabase-js version as the site | Security checklist |

## 3. Before saying fixed

Run the suites the change can touch (`tests/README.md`), and for anything on the list above, the security tests. A screen that works is not proof a rule holds: test the boundary directly (another person's id, a visitor, a forged token).

## 4. Zips for James

Always the whole project (`src`, `supabase`, `tools`, `tests`, `project-docs`, `brand`, `build.py`, `README.md`, `CLAUDE.md`), zipped from inside the repo, never only the changed files: `ship.sh` mirrors each folder, so a partial zip deletes everything it leaves out. Since 30 Oct 2026, `ship.sh` refuses a zip that is missing core files.
