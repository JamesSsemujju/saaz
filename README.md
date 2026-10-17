# Saaz website

The public Saaz website (homepage, one page per service, help pages) and the Saaz marketplace app at `/app/`. Built from small source files into plain HTML for GitHub Pages; the app reads and writes the Saaz Supabase database.

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
src/styles/*.css         tokens, base, layout, components, pages. Joined into one file
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
Built from "Saaz marketplace: build description" (17 Oct 2026). Lives at `/app/` (one page, hash routes). The header's Sign in opens it.

**The rule:** no Saaz review, no listing. A review is made inside Saaz by a signed-in member of a certified garage, on a job arranged through Saaz.

**Files**
- `supabase/marketplace_1_tables.sql` to `_4_access.sql`: tables, every action as a database function, and read rules. Run them in order after `schema.sql`. Nothing in `schema.sql` changes.
- `src/pages/app.html`, `src/layouts/app.html`, `src/styles/app.css`
- `src/scripts/app-core.js` (sign-in, router), `app-public.js` (browse, car page, what's selling, verify, report document), `app-seller.js` (list a car, my cars, offers, deals), `app-garage.js` (apply, jobs, review editor, team), `app-admin.js` (all admin tabs)
- `src/scripts/supabase.js`: supabase-js 2.45.4 (MIT), kept locally instead of a CDN.
- `/admin/` now forwards to `/app/#/admin`. `/car/?ref=` forwards to the app. `/cars/` lists live cars from the marketplace. The old `cars` table is no longer used (dropping it needs your approval).

**Security:** the website never decides who may do what. Every change goes through a database function that checks the caller. Tables have read rules only; nobody writes them directly. Internal helpers can't be called from the website. The audit trail can't be edited or deleted.

**What's built:** accounts (one type, Sign in as Buyer, Seller, Garage team or Admin); VIN-first listing with the vehicle record and odometer history; garage applications, direct adds and teams; the garage line (one garage in play per car, nearest first, 24-hour contact window, pass, decline, time-out, release, admin assign and restart); in-app conversation with phone numbers and emails hidden until the seller agrees; the Saaz review editor (12 checks, body map, odometer, notes) and the report document (number, version, score, rosette and wave bands from the fingerprint, signature block, QR and verification code, A4 print); public Verify that detects altered records; admin approval; offers with offer rules, auto-reject or flag, counters, admin propose and mark agreed, completion; contacts shared only after agreement; demand counts (views one per person per day, saves, offers, auto-rejected, 14-day chart, model comparison) and What's selling with Selling fast; inbox, outbox and audit trail; Saaz-owned cars and Saaz imports; settings.

**Left out on purpose:** payments of any kind, and the platform fee (no money moves through Saaz).

**Placeholders:** every number in Admin, Settings. Mobile numbers aren't verified by SMS (`require_phone_verified` is off until an SMS provider is connected). Email and SMS notices land in the in-app inbox only. VIN decoding uses starter tables. The fingerprint is a check value, not a cryptographic signature. The QR code loads from cdnjs.

**Tested (17 Oct 2026):**
- Database: 72 checks against a local Postgres copy of the Saaz Supabase setup, including the upgrade from the live schema with an existing admin.
- Browser: the whole flow at 320, 390 and 1280 px against a local stand-in for Supabase (66 checks each): garage applies, admin approves, seller lists with photos, garage contacts, seller agrees, garage issues the review, public verify, admin approves, buyer offers (auto-rejected, then accepted after a counter), contacts shared, admin completes, What's selling, every admin tab. No sideways scroll, no script errors.
- Applied to the live Supabase project on 17 Oct 2026: parts 1, 2a, 2b and 5 (hardening) from this chat; the rest via `supabase/marketplace_run_in_sql_editor_2026-10-17.sql` in the SQL Editor (the connection here stops on SQL containing the word "delete"). Checked after: 21 tables, all with row-level security; 80 functions; internal helpers not callable from the website; sign-in-only actions not callable by visitors; James is admin with a profile.
- Supabase security check after: 19 functions callable by visitors, on purpose (public browse, car stats, verify, report, what's selling, and the helpers the read rules use); `listing_views` has no read rule on purpose; leaked-password protection is off (dashboard setting).
- Not tested yet: the live site against the real project, real email confirmation, a real phone on slow data.

**Open calls:** one garage in play per car (built) or per seller across all their cars; the platform fee (left out).

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
