# Saaz layout references (18 Oct 2026)

How it was gathered: each site's page was read as text through a web reader on 18 Oct 2026. This shows the order of sections and the card fields, but **not** pixel widths, column counts or the listing-page split. Those come from memory of the sites and are marked "no source". Direct browser access to these sites was blocked from the build machine.

| Site | Container and grid | Search vs hero | Card anatomy | Listing page split |
|---|---|---|---|---|
| AutoTrader UK (autotrader.co.uk/cars/uk) | Centred fixed container, 4 cards per row in carousels (source: 4 cards per section) | Title and count, then one "Search N cars" button | Image (with photo count), title, price, then 6 specs: seats, doors, body, fuel, gearbox, engine | No source: gallery on top, price and dealer panel on the right, specs below |
| Cars.com (cars.com) | No source | Headline "Imagine the possibilities", search directly below it | Home carousels: image, model, "shop" link only | No source: gallery left, price and contact right |
| CarGurus (cargurus.com) | No source | Headline, search bar directly below it | Home has no listing cards (reviews only) | No source: gallery, price with deal rating, then specs |
| mobile.de (mobile.de) | No source | Headline "Millionen Fahrzeuge. Eine simple Suche.", search form directly below with a live result count | Image, model, price, price rating, then fuel, power, gearbox, mileage, location | No source: gallery left, sticky price and contact panel right |
| Carvana (carvana.com) | No source | "Search Cars" in the header; headline under a hero image | Title, description, vehicle, price, button | No source: gallery top, price and buy panel right |
| Carwow (carwow.co.uk) | No source | No headline; tabbed search panel first under the nav | Model, trim, rating, image, deal score, price | No source |
| BE FORWARD (beforward.jp) | No source | Keyword and reference search in the header; full "Search for cars" form mid page after banners | No cards in the text; filters show make, model, type, year, FOB price, discount, location, steering, fuel, gearbox, cc | No source: photo grid left, price and quote form right |
| SBT Japan (sbtjapan.com) | No source | Hero heading with a stock count, search bar directly below (make, body, price, year, mileage) | No cards in the text | No source |
| Cheki Kenya (cheki.co.ke) | No source | Headline "Find Your Next Car On Cheki", search (make and Search) directly below | Photo, condition label, save, title (make model year fuel), price KES, cc, year, fuel | No source |
| Jiji Uganda (jiji.ug/cars) | Long filter stack before results (likely a left rail, not confirmed) | Search box in the header; heading and price shortcuts above results | Title, seller badge, price USh, description, condition, gearbox, location, seller type | No source: gallery top, price and seller contact right |
| Autochek (autochek.africa) | Landing page only | Headline then country picker; no search | No cards | No source |
| Peach Cars (peachcars.co.ke) | Page content didn't load in the reader (metadata only) | No source | No source | No source |

## What the sites agree on (the discipline to copy)
1. Headline, then search directly under it, before anything else (CarGurus, mobile.de, SBT, Cheki, Cars.com). No promotions above the search.
2. Card order: image first, then title (year make model), then price, then 3 to 6 short specs on one or two lines. Location last. Every card has the same fields in the same order.
3. Results: one filter area (bar or rail) above or beside one uninterrupted grid, with paging or "show more" at the end.
4. Listing page (no source, common pattern): gallery first, then the price, title and contact block beside the details on desktop, and straight after the gallery on mobile.

## What Saaz takes
- One container (1240 px), one gutter, 12 columns at desktop and 4 on phones.
- Home: one headline, search under it, the latest cars, one trust section (the inspection is Saaz's reason to exist), footer.
- One card: image 4:3, title, price, specs line, inspection result on the photo. Same on home, results and admin.
- Listing: gallery, then specs and description left, sticky price and contact right; on phones the price and contact come straight after the gallery.
