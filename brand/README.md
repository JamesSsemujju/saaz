# Saaz brand kit

Source: the Saaz Automotive logo James shared on 17 Oct 2026 (`Saaz_Logo_Original_2026-10-17.jpg`, 1080 × 1044, on black). Everything here is cut from that file; nothing is redrawn.

## Logo files

| File | What it is | Use on |
|---|---|---|
| `saaz-lockup-white.png` (+ `-240.webp`, `-480.webp`) | Pill wordmark with "Automotive" script, white, transparent background | Dark backgrounds: hero, posters, social images |
| `saaz-lockup-black.png` (+ webp) | Same, black | Light backgrounds: documents, letterheads |
| `saaz-wordmark-white.png` (+ webp) | Pill wordmark only, white | Site and app headers (used now) |
| `saaz-wordmark-black.png` (+ webp) | Pill wordmark only, black | Inspection reports, emails, light pages (used now) |
| `saaz-icon-32.png`, `-180.png`, `-512.png` | White wordmark on a black square | Browser tab, phone home screen, app stores |

The web copies the site uses are in `src/assets/img/brand/` (WebP for the site, PNG for emails, which often don't show WebP).

**How the transparent versions were made:** brightness became opacity, so the black background disappears and the silver shading of the pill is kept. On light backgrounds the black version shows the pill dark with the letters cut out, which keeps the logo's look.

## Rules

- Clear space: at least the height of the pill's top bar on every side.
- Smallest size: wordmark 96 px wide on screen; lockup 160 px wide (the script gets thin below that).
- Use the lockup where there's room and the wordmark in tight spaces (headers, icons).
- Don't stretch, recolour, add shadows, or put the white logo on light photos.
- The script word is part of the logo image. Don't type "Automotive" in another script font.

## Colours

Taken from the logo: black, silver and white. Contrast measured with the WCAG formula.

| Name | Hex | Use | Contrast |
|---|---|---|---|
| Saaz Black | `#0B0B0C` | Headers, dark bands, primary buttons on light pages, text | White on it 19.7:1 |
| Charcoal | `#232327` | Secondary dark surfaces | |
| Silver | `#D8DBE0` | Buttons and accents on black (with a light-to-silver gradient on buttons) | Black on silver 14.2:1 |
| Silver text | `#C4C7CC` | Muted text on black | 11.6:1 on black |
| Graphite | `#3A3D42` | Small accents on white (labels, links on hover) | 10.9:1 on white |
| White | `#FFFFFF` | Page background | |
| Soft grey | `#F4F6F9` | App background | Black on it 18.2:1 |

Status colours (green Pass, amber Conditional, red Fail) stay as they are: they carry meaning, not brand.

## Type

- Site and app: the phone's own system font (no web fonts, so pages load fast on slow data).
- Headings: heavy weight (800), tight spacing. Labels: small capitals with letter spacing, in Silver on black or Graphite on white.
- The logo's lettering is custom; it lives only in the logo files.

## Where it's applied

Site header, app header, inspection report, browser and home-screen icons, the four Supabase emails (logo loads from the site, so it shows once shipped), and the colour tokens in `src/styles/tokens.css` (the variable names are older than the brand: `--navy` now holds Saaz Black and `--accent` holds Silver).
