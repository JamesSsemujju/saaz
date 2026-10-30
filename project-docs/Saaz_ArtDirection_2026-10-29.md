# Saaz art direction (approved 29 Oct 2026)

James approved the sample on 29 Oct 2026 ("I approve of this. All pages should follow the same strategy"). This is what was built, and why.

How decisions were made: each part was built in many versions and rendered on a phone (390 px) and desktop (1280 px), then scored. Measured: readability, touch size, alignment, nothing off the screen, the main action within reach. Judged: fit with the references (Carwow and Porsche page text read on 29 Oct 2026; Mercedes-Benz returned only its menu, so no decision rests on it), no new pill, box or card-inside-a-card, and coherence with the rest. Round scores are in the outputs (search 100 and 101 versions, page sections 100, card text 216).

## The system (every page)

| Part | Rule | Why |
|---|---|---|
| Type | Instrument Serif for page and section titles, the car's own name on its page, big scores and step numbers. Instrument Sans for everything else. Self-hosted (assets/fonts, SIL OFL, about 108 KB) | One foundry, drawn to pair. Data stays in the sans so lists scan easily |
| Actions | One solid navy bar with square corners for the step that matters (Make an offer, Send offer, Save). Everything else is the text link: a hairline underline, an arrow when it goes somewhere | Carwow and Porsche use short text actions ("Discover more", "Explore the 911"); one solid action per screen |
| On dark sections and photos | No solid bars or white blocks; every action is the text link in ivory (#E9E3D8) | James: the white blocks "pop out of the socket" |
| Fields | The value over one hairline, no box. Search and filter labels in small capitals; form questions in sentence case (they can be long). Textareas keep a hairline frame | Same look as the approved home search; long questions in capitals are hard to read |
| Dropdown lists | On mouse screens Saaz draws the open list (dark on photos, light on light pages; a bar and a tick on the chosen line). Phones keep their own picker | The system blue list James saw |
| Status words | Small capitals, no pill. Colour only when the state needs attention (amber, red); good states stay ink | James: dots and pills "feel AI" |
| Numbered steps | The number in the serif, no circle, no line | One pattern for the home story, how-it-works and service pages |
| Notes and empty states | Text with a rule, not a grey or dashed box | Every container must earn its place |
| Pages, account menu, shortcuts | Plain numbers (current one underlined), no outline round the account menu, shortcuts as arrow links | No pills |
| Lists (inbox, offers, my cars, team, past jobs) | Rows under hairlines; no card per row. Unread is bold with NEW in small capitals | Added 30 Oct 2026 after James found the inbox in boxes and red |
| Sections inside app pages (account, Build Assistant, garage, admin) | A hairline and a serif title, no white panel. Figures (demand, reports) are serif numbers over a hairline, not tiles | Same rule as notes and empty states |
| Admin side menu | No panel; the current page is bold with a bar on its left | The black block was a second solid bar competing with the real action |
| Look-up fields (VIN, Verify) | The field over a hairline and the arrow link (Look up, Verify) | Same as the home search |
| Required mark (*) | Muted, not red. Red only when something is wrong | Colour only for attention |
| Kept as containers | Dropdown lists, the account menu, the chat thread, the QR code frame, the sticky toolbar, the car page price panel, the inspection report document | Each one does a job a hairline can't (floats over content, scrolls, frames a code, or is the approved panel) |

## The card (home, results, Admin, Cars, /cars/, previews)

Photo (kept clean), then one line: INSPECTED 96/100 · PASS (Conditional in amber), then the price, the name, the specs. Prices line up across a row; the name may take two lines without holding an empty line on short names. No demand line on cards (it stays on the car page). Admin stage and Reserved stay on the photo as small square tags (BA-0003 asked for the stage on the photo). Chosen from 216 versions; the label above the name follows Porsche's cards (a small word above the model name).

## Home

Saaz's own Defender photo with "Inspected *before* you buy.", the search on the picture, quick searches built from the cars there are (two commonest bodies, then UGX 40m and 80m when they narrow the list). Latest inspected on white with "See all N cars". The story section: the engine-bay photo with "Every car is opened up *before* it is listed." and three numbered points (12 checks, body panels and odometer; a report with a code; no money through Saaz), then Verify a report.

The road video from BA-0006 is no longer used on the home page; its files stay in assets/video. James approved the photo hero in the sample.

## Car page

The title in the serif. Under the price, after a hairline: the score large in the serif, the verdict in words, the checks counted from the issued report ("11 of 12 checks passed. 1 advised."), who inspected it and when, validity, report number, then "Read the inspection report". The offer is the solid bar.

## Left out on purpose

Score rings and bars, cards inside cards, a dark band after the dark hero, pills and dots, white button blocks on photos, text over car photos.

## Fix, 30 Oct 2026

A CSS rule in app.css was cut short in the 19 Oct Reports update. The browser joined it to the next rule (required fields), so every list link on the site turned red for a month. Restored, and `tools/check_layout.py` now stops the build when a selector list breaks onto a new line without a comma. `tests/browser_artdirection_test.py` checks the inbox (rows, no boxes, no red) and that a page with nothing wrong has no red text.
