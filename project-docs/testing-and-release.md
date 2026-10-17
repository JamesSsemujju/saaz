# Testing and release

All results from 17 Oct 2026, on the local test stack (see `tests/README.md`). The live project was only read, never tested with writes.

## Results

| Suite | Result |
|---|---|
| Database rules (`tests/db_marketplace_test.py`) | 72 passed, 0 failed |
| Audit fixes, part 6 (`tests/db_audit_fixes_test.py`) | 10 passed, 0 failed |
| Browser journey at 320, 390, 1280 px (`tests/browser_flow_test.py`) | 88 passed, 0 failed at each width (adds: inspection wording, seller sign-up landing, garage invite landing) |
| Text overflow, all pages, 4 widths, normal and stress (`tests/text_overflow_audit.py`) | 0 problems |
| Supabase security advisor (live) | Only intended items left (see system audit) |

## The 12 required scenarios

| # | Scenario | Status | Evidence or blocker |
|---|---|---|---|
| 1 | Register, verify email, sign in, use permitted functions | Partly verified | Register and sign in pass locally. Email verification blocked (F-01) |
| 2 | Password reset end to end | Blocked | Screens and link handling pass locally (invite and reset links open the right page). Email delivery blocked (F-01, F-02) |
| 3 | Seller lists a car and follows it through moderation | Verified locally | Browser journey: draft, submit, garage line, review, approval, sold, with the progress strip |
| 4 | Admin approves or rejects; status shows everywhere | Verified locally | Approve tested in browser; reject and changes in database tests |
| 5 | Customer books an inspection and gets confirmation | Partly | Sellers book through the garage line (verified). Buyers can't book an inspection of a car not listed (F-11, decision needed) |
| 6 | Inspector completes the inspection, records evidence, report generated | Partly | Checklist, body map, odometer, notes, report: verified. Photo evidence missing (F-24) |
| 7 | Right person sees the report; others can't | Gap found | Drafts are protected (database test). But issued reviews can be listed by anyone through the API (F-25). Fix proposed |
| 8 | Garage applies, is reviewed, gets only permitted access | Verified locally | Blocked sign-in until certified; access to its own jobs only |
| 9 | Enquiry stored, routed, answered, closed | Missing | F-13 |
| 10 | Notification failure visible to admins and retryable | Missing | F-14, after SMTP |
| 11 | Unauthorized users can't open or change others' records | Verified locally | Database tests: listings, messages, pass reasons, profiles, audit, internal functions |
| 12 | Uganda only: prices, places, workflows | Screens verified; database guard waiting | Browser tests: no Kenya, no country chooser, UGX, EAT. Part 6 adds the database guard |

## Release checklist

Done:
- [x] Marketplace schema parts 1 to 5 live, checked read-only
- [x] Site build passes, every internal link resolves
- [x] No secret keys in the repository

Waiting for James (dashboard or decisions):
- [ ] Approve and apply `supabase/marketplace_6_audit_fixes.sql` (no deletes, can run from here)
- [ ] Approve the report-privacy fix (F-25), run in the SQL Editor
- [ ] Run `supabase/marketplace_7_inspection_wording.sql` in the SQL Editor ("review" becomes "inspection" in database messages)
- [ ] Paste the 4 email templates and subjects (email document, set-up steps)
- [ ] Custom SMTP sender (route A or B in the email document)
- [ ] Authentication, URL Configuration: Site URL and Redirect URL `https://jamesssemujju.github.io/saaz/app/`
- [ ] "Confirm email" back on once SMTP works
- [ ] Approve deploying the `invite-user` function
- [ ] Approve `pg_cron` for garage time-outs (F-10)
- [ ] Check Supabase backups for the plan (F-20)
- [ ] Decide: buyer inspections (F-11), enquiries (F-13), import desk and finance scope (F-12), launch wording (F-22)
- [ ] Ship this build with `tools/ship.sh`

After shipping, on the live site:
- [ ] Sign up with a Gmail address outside the team; confirm; sign in
- [ ] Reset that password from the email link
- [ ] Owner of Musa Body signs up with jayssemujju@gmail.com, signs in as Garage team; SZ-00001 gets put in play (after part 6)
- [ ] One full car from listing to sold on a phone over mobile data
