# Saaz admin reports (18 Oct 2026)

Admin > Reports. Each report answers one question. Every number is worked out in the database (part 16) and opens the rows behind it.

## 1. What Saaz records today

| Event | Recorded? | Where |
|---|---|---|
| Listing created, draft edited, submitted | Yes | `listings.created_at`, `submitted_at`; audit "created draft", "submitted" |
| Listing approved (went live) | Yes | audit "approve" (first time = first live); `live_at` is the latest |
| Changes requested, rejected, unlisted, withdrawn | Yes | audit, with the admin or seller and the note |
| Sold | Yes | `listings.sold_at` |
| Price changed | Yes | audit "price changed" |
| Inspection expired (car off sale) | Status only | status `re_review_due`; no audit row, no date |
| Listing viewed | Yes, by day | `listing_views`: one per person or device per listing per day. No time of day, no source |
| Saved | Yes | `saves.created_at`. Unsaving deletes the row, so removed saves leave no trace |
| Enquiry | Yes | Offers: `deals` and `deal_events` (offer, counter, accept, agreed, completed, auto-rejected, with side and time) |
| Seller or buyer registered | Yes | `profiles.created_at` |
| Garage applied, approved, team changes | Yes | audit |
| Garage line, inspections | Yes | `conversations`, `reviews` timestamps, audit |
| Admin actions | Yes | audit, with who |
| Search run, filters used | **No** | Needed for Demand |
| Visits, traffic source, device, landing page | **No** | No analytics is wired. Needed for Traffic |
| Enquiry by phone or WhatsApp | **No, and no such channel** | Listings have no call or WhatsApp button; contact details are shared only after an offer is agreed. The offer is the only channel |
| Complaints or "report this listing" | **No, and no such feature** | Adding one changes the public site (out of scope). Moderation will use the admin queues, deal flags and Saaz objections |
| Charges (featured listings, plans) | **Nothing is billed** | Revenue report skipped, no placeholder |

New recording needed later (smallest change, history starts on the day it ships, nothing back-filled): a search log for Demand (slice 2), a visit log for Traffic (slice 3).

## 2. Slices
1. **Slice 1, built:** Inventory, Listing funnel, shared control bar, glossary, drill-downs, CSV export with export log. No new events needed.
2. Slice 2: Demand (adds the search log), Sellers.
3. Slice 3: Buyers and enquiries, Moderation, Traffic (adds the visit log).
4. Reports you didn't list, proposed for slice 3:
   - **Inspections and garages:** requested to started to issued times, garage line accept and time-out rates, results by garage, reports Saaz objected to. This is Saaz's core promise.
   - **Deals and sales:** offers to agreed to completed, asking versus agreed price, time to agree, deals on hold. Answers "what sold, and for how much".
   - **Data checks:** odometer flags, logbook name mismatches, auto-rejected offers, suspended accounts.
   - **Monday summary:** one page with the five Monday questions, each linking into its report.

## 3. How slice 1 works
- Database (`marketplace_16_reports_inventory_funnel.sql`): `report_glossary()` holds every label and definition. `rpt_listing_facts(from, to)` is the one place each metric is calculated. `admin_report(...)` returns the key numbers, the trend, groups and a page of rows. It is admin only and refuses unknown reports and sort columns. With export it returns up to 10,000 rows and writes "report exported" to the audit log (who, report, period, filters, row count).
- Status groups: Draft; Pending (awaiting inspection, booked, awaiting approval, changes requested); Live (live, reserved); Sold; Expired (inspection lapsed); Removed (withdrawn, unlisted, rejected).
- Dates: East Africa Time, stated on every report. Stored in UTC.
- Speed: aggregated in the query. At 20,000 listings, 600,000 views and 30,000 offers the slowest call was 1.14 s (local test machine), so no daily rollups yet. The page shows the time the numbers were worked out.
- Page: question as the heading, control bar (period presets plus custom, compare to previous period, make, price band, status, seller, age, search), key numbers in one row, trend (Funnel only: views and enquiries per day as two small charts, never one chart with two scales), then the table. Filters stay with you between reports. On phones, rows become labelled cards and sorting is a menu.

## 4. Choices to confirm
- "No price" is always 0: a price above zero is required. It is still shown.
- Similar cars: same make and model, live, reserved or sold, same currency. The median includes the car itself when it is one of them. It is shown only with 3 or more other cars.
- Why column: priced 10% or more above or below similar, fewer than 6 photos, description under 150 characters. These are my thresholds (Guess); change them in part 16.
- Days on site and days to sold count from the first time the car went live.

## 5. Reconciliation (local test data, 18 Oct 2026)
Fresh database, live-project time zone (UTC), 9 listings in every status, views, saves and offers on known days. Each report number was checked against a separate hand-written count (`tests/db_reports_test.py`, 59 of 59 pass).

| Number | Report | Hand count |
|---|---|---|
| Live now | 3 | 3 |
| Pending now | 1 | 1 |
| Added, last 7 days | 2 | 2 |
| Sold, last 7 days | 1 | 1 |
| Not updated in 30 days | 2 | 2 |
| Views, last 7 days | 18 | 18 |
| Enquiries, last 7 days | 2 | 2 |
| Reconciliation day (2 days ago): views | 6 | 6 |
| Same day: enquiries, including one at 23:30 UTC the night before (02:30 in Kampala) | 1 | 1 |
| Previous 7 days: views / enquiries | 13 / 1 | 13 / 1 |
| Groups by status, make, price band, age | each adds up to 9 | 9 |

Live project: part 16 is not applied yet. Today it holds 2 listings, both awaiting inspection. After it is applied, Inventory must show Pending now = 2 and Live now = 0. I check that read-only and report back.
