# Data model

Database: Supabase Postgres 17, project `dkxyvlkhpnajbpethwqb`. Source of truth for every rule. Files in order: `supabase/schema.sql` (admins, old cars), `marketplace_1_tables.sql` to `_5_hardening.sql` (live), `_6_audit_fixes.sql` (live 17 Oct 2026), `_7_inspection_wording.sql` and `_8_report_privacy.sql` (SQL Editor, combined in `marketplace_run_in_sql_editor_2026-10-17b.sql`).

## Entities

| Table | Holds | Key relations | Main constraints |
|---|---|---|---|
| `profiles` | One per account | `auth.users` 1:1 | Uganda only (part 6) |
| `admins` | Who is admin | `auth.users` | |
| `settings` | Every number that is an assumption | | Admin-editable, logged |
| `regions` | Region centres for "nearest garage" | | Kenya rows unused |
| `vehicles` | One per VIN | | VIN format; source saaz_import or local |
| `odometer_readings` | Every Saaz reading per VIN | `vehicles`, `reviews` | 0 to 1,000,000 km |
| `listings` | A car for sale | `vehicles`, `profiles` (seller), `regions`, `reviews` (current) | One active listing per VIN and per plate; Saaz-owned has no seller; states in workflows |
| `garages` | Certified garages and applications | `regions`, `profiles` | statuses |
| `garage_members` | Team | `garages`, `profiles` | One garage per person |
| `garage_invites` | Emails with no account yet | `garages` | Used on sign-up |
| `conversations` | Garage in play for a car | `listings`, `garages` | One open per listing; rounds |
| `pass_reasons` | Seller's private reason | `conversations` | Garage can't read |
| `messages` | Garage and seller chat | `conversations`, `profiles` | 1 to 2,000 characters; contacts masked before agreement |
| `reviews` | Saaz review reports | `listings`, `vehicles`, `garages`, `profiles` | Number, version, fingerprint, verify code unique |
| `deals`, `deal_events` | Offers and their history | `listings`, `profiles` | One open deal per buyer per car |
| `listing_views`, `saves` | Demand | `listings` | One view per person per day |
| `notifications` | Every notice, with intended channels | `profiles` | |
| `audit_log` | Every change | | Append only for the website |
| `cars` | Old public list | | Unused, empty (F-18) |

Indexes: unique partial indexes for one active listing, one open conversation, one open deal, one garage per person; `audit_log (entity, entity_id)`. At current volume (tens of rows) no performance issue. When listings pass a few thousand, add indexes on `listings(status, live_at)`, `listing_views(listing_id, day)`, `deals(listing_id, status)`.

## Proposed changes

| Change | Why | Status |
|---|---|---|
| Part 6: Uganda-only guard, garage needs an Active member, one notice per admin, automatic re-queue, East Africa Time, photo bucket limits | Findings F-03 to F-07, F-16 | Live 17 Oct 2026 |
| Part 16: report indexes, `report_glossary`, `rpt_listing_facts`, `admin_report`, `admin_report_options` (reads only, no table changes) | Admin reports slice 1 | Written and tested 18 Oct 2026, needs approval to run live |
| Enable `pg_cron`, run `tick()` every 15 minutes | F-10 | Proposal |
| `email_outbox` table: one row per email, status queued, sent, failed, attempts, last error (no message secrets) | F-14 | After SMTP is chosen |
| `enquiries` and `enquiry_messages` | F-13 | Proposal, needs approval |
| Drop `cars` | F-18 | Needs approval |

Transactions: each database function runs in one transaction, so a failed rule leaves nothing half-done. Privacy: profiles are visible only to the person and admins; contact details are released only after agreement. Retention: no deletion policy yet (decision needed).
