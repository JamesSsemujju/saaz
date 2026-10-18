# Admin navigation

Reference: Zoho's admin products (grouped side menu, record pages with related lists, actions next to the record). Applied to Saaz's real modules only; no empty sections.

## Menu (built 17 Oct 2026)

Wide screens: fixed side menu. Phones: a "Go to" menu at the top.

| Group | Pages |
|---|---|
| Overview | Queues: cars waiting for approval, cars with no garage left, garage applications, deals waiting for handover. Reports (18 Oct 2026): own rail of reports, see Saaz_Reports_2026-10-18.md |
| Vehicles and listings | Cars, Saaz cars, Vehicle records, What's selling |
| Reviews and garage line | Garage line (counts only), Car review reports |
| Garages and partners | Garages |
| Customers and deals | Users, Deals |
| Communications | Outbox |
| System | All activity, Settings |

Not added until the modules exist: Enquiries, Import estimates, Finance referrals, Email failures.

## Staying in Admin (19 Oct 2026)

You are in Admin while two things hold: this session passed the password and the pinned authenticator (the database decides), and Admin is the chosen area. It ends only when you choose: Leave Admin, switch to Buying or Selling in the account menu, or sign out (or the admin session runs out).

| Where | What you see |
|---|---|
| Any Admin page | Bar: View marketplace as admin, Admin, Leave Admin. The Admin menu is always there, also on a missing or failing page. |
| Reports | The reports menu with "‹ Admin", also when a report fails to load. |
| Marketplace while in Admin | Bar: ‹ Back to Admin, Viewing the marketplace as admin, Leave Admin. On a car: Manage this car. Offers and saves are off; your views are not counted as demand. |
| Account menu, admin session active | Admin is one of the areas (Buying, Selling, Admin). Going back needs no password or code until the admin session ends. |
| Account menu, no admin session | Unchanged: Admin panel (password and authenticator) only in Selling. |



| Page | Shows | Actions where you need them |
|---|---|---|
| Car | Photos, details, current report, decision, garage line, demand, reports for this car, history | Approve, request changes (optionally new review), reject, unlist; assign garage, restart line; void review |
| Garage | Details, decision, team, reports it issued, history of the garage and team | Approve, more info, reject, suspend, reinstate; remove member; send invite email |
| Account | Details, cars listed, offers made, garage team, history (what they did and what was done to them) | Trust, suspend, admin, phone verified (on Users list) |
| Deal | Figure, both sides' acceptance, history | Propose a price, mark agreed with a note, complete, cancel |
| All activity | Every change, filterable; each row links to the record | |

Rules: a note is required for every consequential decision; anything that can't be undone needs a second tap; history can't be edited.

## Next improvements

1. Search box on Cars and Users (by ref, VIN, plate, name, email).
2. Pagination past 300 rows.
3. Actions on the Users list moved into the Account page with a reason.
4. Overview counts as tiles with links.
