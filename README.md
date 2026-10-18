# Saaz website

The public Saaz website (homepage, one page per service, help pages) and the Saaz marketplace app at the site root (one address for everything; `/app/` forwards there). Built from small source files into plain HTML for GitHub Pages; the app reads and writes the Saaz Supabase database.

## Project documents (17 Oct 2026)
The system audit, module inventory, workflows, data model, roles, email findings, admin navigation and test results are in `project-docs/`. Tests are in `tests/`.

## Build and publish
1. Edit files in `src/`.
2. Run `python3 build.py`. It needs Python 3.8+ only and fails on any unknown placeholder or broken internal link.
3. Commit `src/` and `docs/`.
4. In GitHub, go to Settings, then Pages, and set the source to `main` and the `/docs` folder (one time only).

## Shipping from the terminal (added 17 Oct 2026)
- One time: `xcode-select --install`, then `git clone https://github.com/JamesSsemujju/saaz.git ~/Desktop/Saaz/saaz`. The first push asks for your GitHub username and a personal access token, and macOS Keychain saves them.
- Working folder: `/Users/james/Desktop/Saaz`. The repo is `saaz/` inside it.
- Each update: save the new `Saaz_Platform_*.zip` into `/Users/james/Desktop/Saaz`, then run `bash ~/Desktop/Saaz/saaz/tools/ship.sh`. It takes the newest zip there (or in Downloads), builds, shows how many files changed, and pushes only if you type `y`.
- Tested against a local copy of the repo, not against GitHub.

## Structure
```
build.py                 builds src/ into docs/, then checks every internal link
src/data/site.json       site settings: WhatsApp number, launch date, base path, company name
src/data/modules.json    every service. Drives the nav, homepage list, footer and service pages
src/data/images.json     fixed design images, by slot
src/layouts/base.html    the page shell
src/layouts/module.html  the template for every service page
src/modules/<slug>.html  extra sections for one service page
src/pages/*.html         homepage, how it works, buying safely, questions, about, privacy
src/partials/            header, footer, icon set, car illustration
src/styles/*.css         tokens (the only place sizes are set), base, layout (the one header and footer), components, pages, cars, app. Joined into one file. The build stops if any spacing, type or container value is not a token (tools/check_layout.py). Rules: project-docs/Saaz_LayoutSystem_2026-10-18.md
src/assets/img/          your fixed images go here
src/lib/money-parser.js  the "40m" / UGX / KES parser from the old site. Kept, not used yet
docs/                    built output. Never edit by hand
```

**To add a service:** add an entry to `modules.json`, add an optional `src/modules/<slug>.html`, then run the build. The nav, homepage, footer and page all update.

**To go live with a service:** change its `status` to `live` only when it actually works end to end.

## Pages (14)
- Home
- 8 service pages: Saaz Check, Vehicle history, Inspected cars, Sell your car, Partner garages, Import desk, Finance, Become a partner garage
- How it works, Buying safely, Questions, About, Privacy

## Marketplace app (added 17 Oct 2026)
Built from "Saaz marketplace: build description" (17 Oct 2026). Lives at the site root since 18 Oct 2026 (one page, hash routes); `/app/` forwards there.

**The rule:** no Saaz review, no listing. A review is made inside Saaz by a signed-in member of a certified garage, on a job arranged through Saaz.

**Files**
- `supabase/marketplace_1_tables.sql` to `_4_access.sql`: tables, every action as a database function, and read rules. Run them in order after `schema.sql`. Nothing in `schema.sql` changes.
- `src/pages/app.html`, `src/layouts/app.html`, `src/styles/app.css`
- `src/scripts/app-core.js` (sign-in, router), `app-public.js` (browse, car page, what's selling, verify, report document), `app-seller.js` (list a car, my cars, offers, deals), `app-garage.js` (apply, jobs, review editor, team), `app-admin.js` (all admin tabs)
- `src/scripts/supabase.js`: supabase-js 2.45.4 (MIT), kept locally instead of a CDN.
- `/admin/` is gone (18 Oct 2026): admin is reached from the account menu. `/car/?ref=` forwards to the app. `/cars/` lists live cars from the marketplace. The old `cars` table is no longer used (dropping it needs your approval).

**Security:** the website never decides who may do what. Every change goes through a database function that checks the caller. Tables have read rules only; nobody writes them directly. Internal helpers can't be called from the website. The audit trail can't be edited or deleted.

**What's built:** accounts (one type, Sign in as Buyer, Seller, Garage team or Admin); VIN-first listing with the vehicle record and odometer history; garage applications, direct adds and teams; the garage line (one garage in play per car, nearest first, 24-hour contact window, pass, decline, time-out, release, admin assign and restart); in-app conversation with phone numbers and emails hidden until the seller agrees; the Saaz review editor (12 checks, body map, odometer, notes) and the report document (number, version, score, rosette and wave bands from the fingerprint, signature block, QR and verification code, A4 print); public Verify that detects altered records; admin approval; offers with offer rules, auto-reject or flag, counters, admin propose and mark agreed, completion; contacts shared only after agreement; demand counts (views one per person per day, saves, offers, auto-rejected, 14-day chart, model comparison) and What's selling with Selling fast; inbox, outbox and audit trail; Saaz-owned cars and Saaz imports; settings.

**Left out on purpose:** payments of any kind, and the platform fee (no money moves through Saaz).

**Placeholders:** every number in Admin, Settings. Mobile numbers aren't verified by SMS (`require_phone_verified` is off until an SMS provider is connected). Email and SMS notices land in the in-app inbox only. VIN decoding uses starter tables. The fingerprint is a check value, not a cryptographic signature. The QR code loads from cdnjs.

**Tested (17 Oct 2026):**
- Database: 72 checks against a local Postgres copy of the Saaz Supabase setup, including the upgrade from the live schema with an existing admin.
- Browser: the whole flow at 320, 390 and 1280 px against a local stand-in for Supabase (66 checks each): garage applies, admin approves, seller lists with photos, garage contacts, seller agrees, garage issues the review, public verify, admin approves, buyer offers (auto-rejected, then accepted after a counter), contacts shared, admin completes, What's selling, every admin tab. No sideways scroll, no script errors.
- Applied to the live Supabase project on 17 Oct 2026: parts 1, 2a, 2b and 5 (hardening) from this chat; the rest via `supabase/marketplace_run_in_sql_editor_2026-10-17.sql` in the SQL Editor (the connection here stops on SQL containing the word "delete"). Checked after: 21 tables, all with row-level security; 80 functions; internal helpers not callable from the website; sign-in-only actions not callable by visitors; James is admin with a profile.
- Supabase security check after: 19 functions callable by visitors, on purpose (public browse, car stats, verify, report, what's selling, and the helpers the read rules use); `listing_views` has no read rule on purpose; leaked-password protection is off (dashboard setting).
- Admin reports (18 Oct 2026): Admin > Reports. Inventory and Listing funnel (part 16, live 19 Oct 2026); Inspections and garages, Deals and sales (part 17, `supabase/marketplace_17_reports_inspections_deals.sql`, must run in Supabase for those two pages to work). Details: project-docs/Saaz_Reports_2026-10-18.md
- Layout audit (18 Oct 2026): `tests/layout_audit.py` renders home, results and listing (and the static pages that share them) at 360, 390, 430, 768, 1024, 1280 and 1440 px with the column grid drawn on, plus the seller, garage, buyer and admin pages at 390 and 1280. 68 of 68 pass: one left edge, equal card rows, one control height, 44 px touch targets on phones, no sideways scroll, search on the first screen, price within two screens.
- Text audit (17 Oct 2026): every site page, preview page and app page at 320, 390, 768 and 1280 px, checked for text spilling out of its box. Found one (the VIN decoder's Series value, e.g. ASA44L/ASA42L/AVA44L, ran into the Body column). Fixed with a wrap rule for long unbroken values in base.css and app.css. Re-run with every typed field and every decoder value filled with 43 characters without spaces: 0 problems.
- Not tested yet: the live site against the real project, real email confirmation, a real phone on slow data.

**Open calls:** one garage in play per car (built) or per seller across all their cars; the platform fee (left out).

**Changes, 17 Oct 2026 (afternoon)**
- History lives with the thing it's about: each car, garage (with its team), account and deal page shows its own history. Admin, All activity still lists everything, and each row now links to the car, garage, account or deal it touched. New admin page per account (`#/admin/user/<id>`): details, cars listed, offers made, garage team, history.
- "Reviews" renamed to "Car review reports": a Saaz review is always a report on one car, made by a certified garage. Saaz doesn't rate sellers or garages yet.
- Required fields show a red * (added automatically to every required field in the app).
- Direct-add reason now reads "Why are you adding this garage directly, without an application?", with an example.
- Links from Saaz emails (invite, password reset, email confirmation) now open the right page. An invite opens "Set your password".
- Invite emails: `supabase/functions/invite-user/index.ts` (Edge Function, not deployed yet). Admins and garage owners get "Send invite email" next to anyone added who has no account yet. The service key stays on Supabase's servers.
- Email needs set-up in Supabase before it reaches real people: (1) Authentication, URL Configuration: Site URL `https://jamesssemujju.github.io/saaz/`, and under Redirect URLs add both `https://jamesssemujju.github.io/saaz/**` and `https://jamesssemujju.github.io/saaz/app/**`. (2) A custom SMTP sender (Authentication, Emails, SMTP Settings). Without it Supabase only emails members of the project's team (source: supabase.com/docs/guides/auth/auth-smtp).
- Tested: browser flow 73 checks at 320, 390 and 1280 px; text audit with stress values, 0 problems. The Edge Function is not tested (no Deno here).

## One address, roles, admin entry, sign-out (added 18 Oct 2026)
**One address:** https://jamesssemujju.github.io/saaz/ is the marketplace app (public listings first). The old `/app/` address forwards there with its code and page, so links in emails already sent keep working. The old home page is now `/home/`.

**Roles** (the database decides every one; the page only shows what the database says):
- Buyer and seller: one account. Sign-in "as" Buyer or Seller only picks the start page.
- Garage: invited by Saaz or by the owner of a certified garage, or applies and waits for Saaz. Nothing works for a garage until Saaz certifies it (`my_garage_id`). Team list shows Invited (no password yet) or Accepted (password set), and the garage's own stage (Certified, or waiting) separately. Owners of a garage that isn't certified can't add members or send invites.
- Admin: an admin account that signs in as Seller sees **Admin panel** in the menu under their initials. Buyers, sellers and garage users never see it. Choosing it asks for the password again, then the authenticator code (first time: scan the QR code, then pin it, below). Five wrong tries signs you out. Failed tries are written to All activity.

**What makes admin admin** (`is_admin`, parts 10 and 12): this session used the authenticator pinned to the account, and the password and the code were both entered in the last 12 hours. The menu entry, the page and the address give nothing on their own.

First time, or after a lost phone:
1. Sign in as Seller, open the menu, choose Admin panel, enter your password, scan the QR code, enter the code.
2. In the Supabase SQL Editor, run `supabase/marketplace_10b_pin_admin_authenticator.sql` (refuses unless there is exactly one verified authenticator).
3. Choose Admin panel again.
Lost phone: in Supabase, Authentication, Users, open the admin and remove the old authenticator ("factor"), then steps 1 to 3.

**Sign-out** (`Saaz.signOut`, one function for every role): ends every session of the account on Supabase, clears what the browser kept, and opens https://jamesssemujju.github.io/saaz/ (the public listings). Never the sign-in page. Afterwards a copied token can't run any Saaz function (`require_user` checks the session is still live), and admin is gone at once. Back to a protected page shows "Sign in to see this page", not the page. A session that ends some other way (expired, signed out on another device) lands on the listings with "Your session ended".

**Known limit:** table reads through row rules accept a copied token until it expires (Supabase default: 1 hour). Every function call, every write and all admin access stop at sign-out.

## Admin Cars page = the marketplace listings page (added 18 Oct 2026)
Admin, Cars is the marketplace listings page itself (`Saaz.listingsPage` in `app-public.js`): same heading, filters, cards and layout, with every car and one extra filter for status. Cards link to the car's admin page. Cars that aren't live show their status on the photo, where "Reserved" already shows. Card data comes from one database function, `listing_card`, used by `browse_listings` (live and reserved only, as before) and `admin_listings` (every status, admins only). Visibility rules are unchanged. Database: `supabase/marketplace_15_admin_listings_preview.sql` (applied 18 Oct 2026).

## Inspection IDs, tracking, scopes, one inspector (added 18 Oct 2026)
**IDs from the request.** Sending a car for inspection creates its General inspection with an ID straight away (status Requested). The seller sees it on their car page. Statuses: Requested, In progress (database: `draft`), Completed (`issued`, later `superseded`), Cancelled. If a garage leaves, its inspections go back to Requested with the same ID.

**Track an inspection** (top bar, `#/track`): 1. Lookup says only "found" or "not found". 2. Only after a match does the sign-in prompt appear (Seller or Garage team). 3. `inspection_access` then decides what that account may see and do; another account gets "isn't linked to your account". Already signed in: no prompt.

**Starting** (`start_inspection`) re-checks at that moment, with a row lock: the inspection exists and is Requested; the car is still with Saaz; it's booked with your garage (seller agreed); you're the inspector it was given to, or the owner taking an unassigned one. One inspector per inspection: once started, only that person can fill it in, issue it or stop it, and the owner can't hand it to someone else. Stopping puts it back to Requested with the same ID and inspector. Withdrawn or rejected cars cancel their open inspections.

**Scopes** (table `inspection_scopes`, a PROPOSAL to edit): General (12 checks and body map; the only one that decides whether the car goes live) plus Engine and gearbox, Body and chassis, Electrics, Brakes steering tyres. VIN and odometer are in every scope. A seller adds scopes when submitting or while waiting for the garage. Each scope has its own ID; the garage owner gives each to one inspector. The booking closes when no open inspection is left.

**Not decided yet (gaps):** inspection-only requests for cars not for sale; whether an inspection may start only on or after its inspection date; whether a Requested inspection expires; IDs are sequential, so lookups can confirm that an ID exists (nothing else).

## Access inside each team, inspection IDs, Saaz opinions (added 18 Oct 2026)
**Garage.** The owner sees and runs everything: offered cars, every job, every report, the team. The owner gives each job to a team member ("Give this job to" on the job page). An inspector sees only the jobs given to them and the reports they wrote: no offered cars, no other inspectors' work, no team list. Decline and release are the owner's. Messages from the seller reach the owner and that job's inspector only. An owner who starts an unassigned job takes it.

**Inspection IDs.** Every inspection gets its ID (`SZR-YYYY-NNNNNN`) the moment it starts, and keeps it as the report number. A car can have many; each is separate. "Open an inspection by its ID" on the garage dashboard opens it (owner: any of the garage's; inspector: their own). The car pages for Saaz and the seller list every inspection of the car with its ID, garage, inspector, status and Saaz's view.

**Saaz never changes a report.** Staff support or object, always with a reason; the garage (owner or the report's author) can reply. The report and the public verify page show all of it. While Saaz objects, the car can't be approved, and a live car goes off sale (open offers wait) until Saaz supports the report or asks for a new inspection. Voiding is gone.

**Saaz team.** Admin: everything, including Settings and the Saaz team page. Staff: cars, garages, deals, acting for sellers and buyers, supporting or objecting. An admin adds people by the email of their Saaz account, changes roles, removes people (with a reason; their sessions end at once) and approves each new authenticator on the Saaz team page. Account flags: staff can set trusted and phone verified; suspending is admin only.

Database: `supabase/marketplace_13_roles_inside_teams.sql` (run in the SQL Editor: it replaces table rules).

## Admin acting for a seller or buyer (added 18 Oct 2026)
Like event-platform staff managing an event for the organiser. On a car's admin page, "Act for the seller" can change the price, change the offer rules, send the car for inspection, take it off sale to edit, withdraw it, and agree to or pass on a garage. On a deal page, "Act for the seller" and "Act for the buyer" can counter, accept, decline or withdraw.

- Every action needs a reason of 10 characters or more. The person acted for gets a notice with the reason.
- It runs the same database function the seller or buyer would run, so the same rules apply (minimum price, 4 photos, offer rules).
- Every row written is stamped in All activity: actor = the admin, plus who it was for, which side, and the reason. The car's history (seller and admin) and the deal history (both sides) show "Our team" or "Saaz team, for the seller" with the reason.
- An admin can't accept a figure that an admin entered for the other side. Every agreement needs one real person, or "Mark agreed" with a note of how both sides confirmed.
- Not included: writing garage messages as the seller, making a new offer as a buyer, editing a draft's details from the admin page (the database allows it, the page doesn't offer it yet).
- Database: `supabase/marketplace_11_admin_on_behalf.sql`.

## VIN decoder (added 17 Oct 2026)
- The first live feature. Use the homepage field or the Vehicle history page (`/history/#decode`).
- `src/scripts/vin.js` sends the VIN from the visitor's browser to the free NHTSA vPIC API (`DecodeVinValues`, no key). Saaz stores nothing.
- It shows make, model, year, body, fuel, engine, drive, gearbox and the country it was built in, and warns when the check digit doesn't add up.
- Japanese frame numbers (such as ZSU60-0012345), number plates, and anything with I, O or Q get a clear message instead of a wrong answer.
- Times out after 12 seconds, with a retry message.
- To move to a paid decoder later, replace `decode()` in vin.js and keep the field list.
- Tested with a simulated NHTSA response, because this workspace can't reach NHTSA. The real API was checked separately: it returned a 2017 Toyota RAV4 for a test VIN. Not yet tested on the live site from a phone.

## Images (added 16 Oct 2026)
- Originals stay in `Pictures/` at the top of the repo and are never changed.
- `src/data/image-crops.json` says which photo goes where, where to crop it (4:3), and which number plates to blur.
- `python3 tools/prepare_images.py` makes `src/assets/img/<slot>-640.webp` and `-1280.webp`. It needs Pillow (`pip3 install pillow`) and only has to be run when a photo or crop changes. The made files are committed, so `build.py` still needs nothing extra.
- Phones load the 640 px version (12 to 49 KB). Large screens load the 1280 px version.

## Car browsing (added 16 Oct 2026)
- `/cars/` is the buyer search page. It has shop-by buttons (make, body, price in UGX), filters (make, body, price, year, fuel, gearbox), sorting, and car cards with their inspection result.
- Each car gets its own page at `/cars/<ref>/`, with the photo gallery, price, inspection summary, specs and findings.
- Real listings come from `src/data/cars.json`. It is empty, so the public page shows "No cars listed yet".
- `docs/preview/` is the same site built with `src/data/cars.sample.json`: 12 invented cars, each labelled "Design sample". It carries noindex, and nothing on the public site links to it. Address: /saaz/preview/cars/
- Car photos go in `src/assets/img/cars/` and are listed in each car's `photos`.
- `src/scripts/cars.js` (about 3 KB) only filters and sorts. Without JavaScript, every car is still listed.

## Status
| Part | Status |
| --- | --- |
| All 14 pages, nav, footer, mobile menu | Built and tested |
| Check field on the homepage | Live: free VIN decoder |
| Car lists, garage lists, history records | Empty states. Filled from the database once inspections run |
| WhatsApp links | Hidden until `whatsapp` is set in site.json |
| Images | 7 fixed photos from Pictures/ (watermarked SaaZ Automotive): home, Saaz Check, Vehicle history, Sell, Import, Finance, About. Number plates blurred. Garages and partner pages have none: no garage photos yet |
| Colours and fonts | Current navy and orange, kept until a brand direction is chosen |
| Icons | Hand-drawn set in one file. To be replaced by a licensed set |

## Assumptions
- `basePath` is `/saaz/` (jamesssemujju.github.io/saaz). Change it to `/` on a custom domain.
- `legalName` is "Saaz" until registration is confirmed.
- `launch` is "early 2027", taken from the spec plan.
- No JavaScript: the mobile menu and the questions open with plain HTML.

## From the old repo
| File | Action | Why |
| --- | --- | --- |
| index.html | Replace | Built pages now come from `docs/` |
| build.py (old) | Replace | It generated the page with false claims |
| data.json | Remove | 24 sample cars and invented stock counts |
| patch2.py | Remove | It filled in service records and grades at random |
| nl.js | Keep, moved to `src/lib/money-parser.js` | Good parser, needed when search goes live |

## Checked (15 Oct 2026)
- All 14 pages load at 360 and 1280 px wide.
- No sideways scroll, no script or console errors, no broken internal links.
- Homepage is 19 KB plus 16 KB of shared CSS.

**Not checked:** a real phone on a slow connection.
