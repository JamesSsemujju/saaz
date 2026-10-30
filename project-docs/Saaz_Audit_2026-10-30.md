# Saaz audit and demo (30 Oct 2026)

Done on a local copy of Saaz (Postgres 16 with every supabase/*.sql part, PostgREST 12.2.3, the local Supabase stand-in), with demo accounts. The live project was only read: counts of listings, reviews, garages and members.

## The journey, in Saaz's real order

Saaz's rule is "no Saaz inspection, no listing", so admin approval comes after the inspection, not before:

1. Seller lists the car (VIN, details, 4 to 12 photos, price) and submits it. It stays private.
2. Saaz puts one certified garage in play and creates the inspection ID. Admin sees the car in Admin, Cars, with no Approve button yet.
3. The garage messages the seller inside Saaz (phone numbers hidden), the seller agrees, the garage sets the date, the owner gives the inspection to an inspector.
4. The inspector does the 12-point check, body map, odometer and notes, and issues the report.
5. The report gets a verification code; anyone can verify it. The seller sees it.
6. Admin reviews the report (support or object, with a reason) and approves. The car goes live.
7. Visitors see it on the marketplace and the home page; the car page links the report.
8. A buyer offers; contacts are shared only after both agree.
9. The seller sees it live, the report and the offer.
10. Admin sees the whole record and the deal.

`tests/demo_journey.py` runs these steps through the screens and checks each one, that the same facts show everywhere, and that each person sees only what they may (41 checks).

## Running it live

Needs: your admin account and authenticator; a seller account; a sign-in for a member of Musa Body (the certified garage on live). Live has 3 listings (SZ-00001 and SZ-00002 awaiting inspection, SZ-00003 a draft) and 0 deals. Every step creates real records on live; there is no undo for an issued report except a new version. A recorded run is in the outputs: Saaz_Demo_Journey_2026-10-30.html.

## Sample report

`#/report/sample`: a complete report drawn by the same code as real reports, from data kept in app-public.js (SAMPLE_REPORT). Watermarked SAMPLE, amber ribbon, no verify code, nothing read from or written to the database. Linked from the home trust section, the seller page and Verify a report.

The report structure is 12 checks (pass, advise, fail), 9 body panels, odometer, one notes field, signature, code. It has no inspection photos, no per-check notes and no separate diagnostics fields; the sample puts findings by area in the notes, as a garage can today. Adding those fields is a database change (BA-0010).

## Found and fixed today

- Photos were saved in the order their uploads finished, so the card photo could be any of them. Now the seller's order is kept.
- The VIN look-up said "The not in the starter tables gave nothing." Now a plain sentence.
- The seller's progress bar showed Approved as the current step on a live car. Now Approved is done and the car waits for a deal; the bar is in ink, not green.
- Account initials took "(" from names like "Sam Seller (demo)". Now letters only.
- The privacy page said the site "collects no personal data and uses no cookies or tracking", false since accounts. Now it says what Saaz stores.
- Added the sample report and the demo run.

## Still open

- The eight service pages (Saaz Check, Vehicle history, Import desk, Finance, garage ratings and others) describe planned services the app doesn't offer yet; release timing is hidden on purpose (17 Oct 2026). The footer says "Preview. Saaz is not trading yet."
- No full privacy notice yet, and sign-up doesn't ask consent for cloud storage outside Uganda, both promised on the privacy page.
- Email and SMS are not connected; every notice lands in the in-app inbox. Mobile numbers aren't verified.
- Four signed-in phone pages scroll sideways when a field holds a 43-character word with no spaces.
- The QR code on reports loads from cdnjs.
- Not tested in Safari or on a real phone.
