# Saaz layout system (18 Oct 2026)

Structure only. Colours, fonts and images are unchanged.

## Tokens (src/styles/tokens.css, the only file with sizes)
- Container 1240 px. Gutter 16 on phones, 24 from 768.
- Columns: 4 on phones, 12 from 768. Column gap = gutter.
- Spacing: 4, 8, 12, 16, 24, 32, 48, 64, 96.
- Section padding, two sizes: standard 48 (64 from 768), compact 24 (32 from 768).
- Type: 12/16, 14/20, 16/24, 18/28, 20/28, 24/32, 32/40, 40/48, 56/64. Every line height is a multiple of 4.
- Controls: 48 high (also the phone touch target). Small controls 40 from 768, 48 on phones.
- Breakpoints: 768, 1024, 1280 only.
- `tools/check_layout.py` runs inside `build.py`. Any margin, padding, gap, offset, font size, line height, wide width or breakpoint not from the tokens stops the build. Inline styles are checked too.

## One of each
- Card: photo 4:3, name (2 lines held when cards sit side by side), specs (1 line), price, demand (1 line). Used on home, results and Admin, Cars.
- Buttons: primary `.btn`, secondary `.btn.ghost`, text `.btn.text`. Modifiers: `.small`, `.wide`. They invert on dark bands.
- Input: one rule for text, number, email, select, textarea.
- Badge: one rule. `.chip`, `.car-tag`, `.src`, `.result`, `.lvl`, `.sample` and `.status` are names for it; colour is the only variant.
- Section heading: `.sechead` (title, optional line, optional link at the right edge).
- Header and footer: one markup for the app and the static pages.

## What each section is for (find, trust the car, trust the seller, act)
Home
- Header: get to buying, checking a report or selling. Next: pick one.
- Headline and search: say what Saaz is and start a search. Next: search.
- Latest inspected cars: show real inspected cars. Next: open one, or see all.
- Why you can trust a car on Saaz: the reason to believe the inspection. Next: verify a report or track one.
- Footer: the rest of Saaz and the rules. Next: an info page.

Results
- Heading and count: what this list is. Filter bar: narrow it. Grid: pick a car. Pages: see more. Nothing sits between the filters and the cards.

Listing
- Gallery: see the car.
- Price panel, in order: name, price, where (find); inspection result and report (trust the car); seller area or "Sold by Saaz" (trust the seller); offer, save (act); views, saves, offers.
- Details and "From the seller": check the facts.

## Removed (no job the sections above don't already do)
- "Selling fast" strip on results (it has its own page, What's selling, in the header).
- Shop-by chips and the "How listings work" band on /cars/ (they repeated the filters and the home trust section).
- The second "See all" link above the home grid (the button under the grid stays).
- The static pages' own header and mobile Menu (services are in the footer). The preview notice moved from above the header into the footer, so every header is the same.
- admin.css (no page used it).
- The footer line "This site collects no personal data and uses no cookies or tracking." It is no longer true.

## Choices made (say if you want them the other way)
- Listing: the gallery takes the left 8 columns with the price panel beside it on desktop, instead of a full-width gallery above. It keeps the price on the first screen. On phones the panel comes straight after the photos.
- The header stays fixed at the top from 1024 px. Below that it is two rows, so it scrolls away to leave the screen to the page.
- Results show 24 cars a page.
- The report's security microprint went from 5 px to 6 px (now a token).

## Proof (local test stack, 18 Oct 2026)
- check_layout: every value is a token.
- tests/layout_audit.py: 68 of 68 renders pass (home, results, listing, /cars/, a static car page, a service page at 360, 390, 430, 768, 1024, 1280, 1440; seller, garage, buyer and admin pages at 390 and 1280).
- tests/browser_flow_test.py: 173 of 173 at 390 and at 1280.
- No database changes. Routes, data, search, filters, sign-in and seller, garage and admin workflows are the same.
