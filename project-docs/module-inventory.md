# Module inventory

Status: 1 built and verified, 2 built but incomplete, 3 screen only, 4 backend only, 5 missing, 6 blocked by configuration. Scope: Uganda only, UGX, East Africa Time.

| Module | Purpose | Status | Pages (app routes unless marked) | Database | Depends on | Next step |
|---|---|---|---|---|---|---|
| Accounts | One account type: buy and sell | 1 (email parts 6) | `#/signup`, `#/signin`, `#/forgot`, `#/reset`, `#/account` | `auth.users`, `profiles` | Supabase Auth, email (F-01) | Custom SMTP |
| Roles | Buyer, seller, garage team, admin | 1 | header role switch | `admins`, `garage_members` | | |
| VIN decoder | Factory spec for a 17-character VIN | 1 | site `/history/#decode`, home | none | NHTSA vPIC (free) | |
| Vehicle records | One record per VIN, odometer history | 1 | admin Vehicle records, report | `vehicles`, `odometer_readings` | | |
| Listings | VIN-first listing, draft to sold | 1 | `#/sell/new`, `#/my/cars`, `#/my/cars/<id>`, `#/browse`, `#/car/<ref>`, site `/cars/` | `listings` | Storage | Photo clean-up (F-17) |
| Garage line | One certified garage in play at a time, in-app contact | 2 | seller car page, `#/garage`, `#/garage/job/<id>` | `conversations`, `messages`, `pass_reasons` | Scheduler (F-10) | Part 6, pg_cron |
| Saaz reviews | Review of a car by a certified garage, report, verify | 1 | `#/garage/review/<id>`, `#/report/<code>`, `#/verify` | `reviews` | | Photo evidence (F-24) |
| Listing approval | Admin approves, requests changes, rejects, unlists | 1 | `#/admin/car/<id>` | `listings`, `audit_log` | | |
| Offers and deals | Offers with rules, counters, agreement, completion | 1 | `#/car/<ref>`, `#/deals/<id>`, `#/offers` | `deals`, `deal_events` | | |
| Demand | Views, saves, offers, what's selling | 1 | car pages, `#/selling` | `listing_views`, `saves` | | |
| Garages | Apply, approve, suspend, add directly | 2 | `#/garage/apply`, `#/admin/garages`, `#/admin/garage/<id>` | `garages` | invite email (F-21) | Deploy invite function |
| Garage teams | Owner adds inspectors | 2 | `#/garage/team` | `garage_members`, `garage_invites` | invite email | |
| Saaz-owned cars | Saaz sells its own imports | 1 | `#/admin/saaz` | `vehicles.saaz_owned`, `listings.saaz_owned` | | |
| Inbox | Every notice to a person | 1 | `#/inbox` | `notifications` | | |
| Email | Account and business emails | 6 | | none yet | SMTP (F-01) | Custom SMTP, delivery log |
| Audit trail | Who did what, per record | 1 | car, garage, account, deal pages; admin All activity | `audit_log` | | |
| Admin console | Operate everything above | 1 | `#/admin/*` | all | | |
| Buyer inspection (Saaz Check for any car) | A buyer books a review of a car not listed on Saaz | 5 | site `/inspections/` promises it | none | Decision | Decide: build, or reword the page |
| Book a service at a certified garage | From the meeting: Saaz books services for owners | 5 | none | none | Decision on fee | |
| Import desk | Indicative landed cost in UGX | 3 | site `/import/` | none | URA rates source, FX source | Decide scope; no invented rates |
| Finance referrals | Pass a buyer to a lender with consent | 3 | site `/finance/` | none | Lender partner | Decide partner and consent text |
| Enquiries and support | Questions, reports, help | 5 | none | none | | Build (proposal in workflows) |
| SMS | Phone verification and alerts | 5 | none | `notifications.channels` | Provider | Later |

## Proposal for the missing modules (needs your decisions)

1. **Enquiries and support** (recommended next build). Buyer asks about a live car, or reports it; anyone asks for help. Stored per car or per topic, assigned to an admin, answered in the app, closed with a reason. Contact details stay hidden, as in the garage line.
2. **Buyer inspection (Saaz Check)**. Reuses the garage line and the review editor, with a "car not listed" record: buyer enters VIN or chassis, plate, where the car is; nearest garage in play; same report. Decide who pays the garage and how (no payments in Saaz).
3. **Import desk**. A request form in the app (VIN or auction link, budget) handled by staff, with an estimate marked "indicative" and an expiry date. Tax rates and fees only from a source you confirm (URA).
4. **Finance referrals**. A consent screen and a referral record with status (sent, contacted, approved by lender, declined). Saaz never shows itself as the lender.
