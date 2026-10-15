# Saaz website

The public Saaz website: a homepage, one page for each service, and help pages. It is built from small source files into plain HTML for GitHub Pages. Nothing on it is live yet. Every service shows its planned date.

## Build and publish
1. Edit files in `src/`.
2. Run `python3 build.py`. It needs Python 3.8+ only and fails on any unknown placeholder or broken internal link.
3. Commit `src/` and `docs/`.
4. In GitHub, go to Settings, then Pages, and set the source to `main` and the `/docs` folder (one time only).

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
| Check field on the homepage | Placeholder. Switched off and labelled "Opens early 2027" |
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
