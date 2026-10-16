# Saaz website

The public Saaz website: a homepage, one page for each service, and help pages. It is built from small source files into plain HTML for GitHub Pages. Nothing on it is live yet. Every service shows its planned date.

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

## Admin and the car database (added 17 Oct 2026)
- `/admin/` is the staff sign-in. It is not linked anywhere, and it carries noindex. Admins add, edit, publish, unpublish, mark sold and delete cars, and upload photos. Photos are resized to 1600 px WebP in the browser.
- Data lives in Supabase. `supabase/schema.sql` creates the `cars` and `admins` tables, a public `car-photos` bucket, and the access rules:
  - The public can read published cars only.
  - Only people in `admins` can write.
  - The database refuses to publish a car without a Passed review, a review date, a certified shop and plates confirmed hidden.
- Set-up, done once:
  1. Create a Supabase project.
  2. Run `schema.sql` in the SQL Editor.
  3. Turn off public sign-ups.
  4. Add admin users and their rows in `admins`.
  5. Put the Project URL and anon key in `src/data/site.json`, then rebuild.
- Published cars appear on `/cars/` and `/car/?ref=SZ-0001` straight from the database, with no rebuild (`src/scripts/live-cars.js`).
- Only a masked chassis number is saved (for example ZSU60-•••2210).
- Removing a photo from a car doesn't yet delete the file from storage.
- Tested against a simulated Supabase: wrong password, non-admin, saving a draft, publishing refused without a review, publishing with a review, and a duplicate ref.
- Live project (17 Oct 2026): ref `dkxyvlkhpnajbpethwqb`, region eu-west-1. Schema applied as 6 migrations (saaz_admins, saaz_cars, saaz_is_admin, saaz_touch_trigger, saaz_policies, saaz_photo_bucket). Checked on the live database: the public can't add cars (refused by row-level security), and publishing without a review is refused by `publish_needs_review`. Admin sign-in from a browser is not tested yet.
- The Supabase security advisor warns that anyone can call `is_admin()`. Kept on purpose: the access rules need it, and it only says whether the caller is an admin.

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
