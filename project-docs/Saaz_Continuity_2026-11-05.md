# Saaz continuity (5 Nov 2026)

From the Mercedes-Benz navigation study (James's Claude in Chrome session, 5 Nov 2026) and our own measurements on the local copy.
Mercedes feels continuous through speed, a fixed header and the back/forward cache; on slow mobile it flashes and jumps. Saaz had
the same jump. No layout, spacing, component or styling changes: timing and loading only.

## Measured before and after (local copy; live numbers differ: the test server doesn't compress files)
| Page | Layout shift before, desktop | before, phone Slow 4G | after (both) |
|---|---|---|---|
| Home | 0.70 | 1.36 | under 0.1 (0 on phone) |
| Car list | 0.40 | 0.89 | under 0.1 |
| Car page | 0.56 | 1.00 | under 0.1 |
Good is under 0.1. Cause: the footer painted near the top under an empty app, then got pushed down; on phones the home photo
also had no size until it arrived.

## What changed
1. **Header and page room in the HTML.** `src/pages/index.html` carries the visitor header, so it is the first thing on screen
   before any script. The page area keeps a screen's worth of room (`#view` min-height), so the footer never paints high.
   One visible effect: on very short pages the footer sits at the bottom of the screen instead of under the content.
2. **Back keeps your place.** Each history entry remembers its scroll and last view. Back or Forward shows that view at once,
   at the same place (greyed out while it refreshes). A new page starts at the top. A refresh after an action stays put.
3. **Smaller first load.** Visitors and buyers get `supabase.js`, `app-core.js` and `app-public.js` only. Selling, garage,
   admin, reports, promotions and notifications code load the first time someone goes there (`S.need`, in the old order).
   Signed-in people get their own area's code in the background once the page is idle. About 260 KB less for buyers
   (uncompressed). `S.kick` (SMS sender) moved into the core so every visitor's actions still wake it.
4. **Photos fade in** over 200 ms once loaded, over their reserved frame and placeholder colour. Photos already cached show at
   once. Off with reduced motion. Home photos now carry width and height, so their space is held.
5. **Prefetch.** A finger landing on a car or on Buy cars, or a mouse resting on it for 80 ms, starts loading it; the tap
   then needs no new request. Public, read-only data only, kept 20 seconds; any change empties it. Per-person parts (your
   saves, your offers) and view counts are never cached.
6. **Press state.** Links and cards dim at once when pressed, in place of the browser's blue flash.
7. **Fonts preloaded** (sans 400, serif normal and italic) so text doesn't reflow when they arrive.

## Not done
- Cross-document View Transitions on the static pages: they already show 0 layout shift; left for later.
- Real-phone check on MTN or Airtel data: not possible from here.

## Tests
`tests/browser_continuity_test.py`: 29 checks (19 fail on the code before). With `browser_navigation_test.py` (BA-0016).

## Code review, 5 Nov 2026 (ponytail, thermo-nuclear review)

What changed. Behaviour is the same; the tests prove it.

- One table helper. `S.table` in app-core.js replaces three identical copies (Admin, Promotions, Outbox).
- One place decides "data may have changed". `S.changed()` empties the 20-second read cache and nudges the SMS sender. `S.rpc` (any call not on the read list) and `S.act` both use it; only `S.act` also asks who-you-are again, so moving around Admin still asks at most once.
- One switch for the greyed-out page. `setBusy(view, on)` replaces four hand-written copies in `S.render`.
- No pass-through wrappers. Promotions and Outbox call `S.adminPage` directly at draw time.
- Toasts share one text builder; a redundant admin check and an alias were removed.
- send-outbox: one typed result (`Sent`) and one `stop()` for "the account can't send now", instead of five hand-written objects.

Not changed, on purpose:
- SQL parts 23 to 25 are live. Changing the files would make them differ from the database, so they stay as run.
- The two "last view" stores stay separate. `S._views` is per history entry (Back), `S._shellCache` is per address inside Admin. Merging them would change what Back shows. Likely fine as is.
- No file is over 1,000 lines (largest: app-core.js, about 800).
