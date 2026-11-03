# Saaz Promotions (3 Nov 2026)

Asked for in "IT Integration Proposal" (car giveaway draw). Built as one branch, Promotions, so later kinds (offers, referrals, competitions) reuse it. First kind: prize draw.

Status: **built and tested locally. Not live.** `supabase/marketplace_23_promotions.sql` needs James's approval in a live chat before it runs in Supabase. The switch starts off.

## Rules the database enforces
- One master switch (Admin, Communications, Promotions). Full admins only. Switching off needs a reason. History can't be edited.
- A promotion takes entries only when the switch is on, its status is open, and now is between its dates.
- It can't open without a permit number, terms text and version, a prize and dates.
- Once open, only the summary and a later closing time can change.
- Entry: signed-in account with a confirmed email, one per account, Saaz team excluded, the current T&C version ticked, Ugandan mobile (stored as +256...), current car and next car. Marketing and WhatsApp consent are separate optional ticks.
- NIN and TIN are not collected (waiting on Allan's answer).
- Entries lock. Only a full admin changes an entry's status, with a reason, and only before the draw.
- Fraud flag: the 4th and later entries from one network address are flagged (setting `promo_flag_same_address`, default 3) and kept out of the draw until an admin decides. Addresses are stored only as a salted hash.
- Draw: closed promotions only, once, valid entries only, with a named witness. The seed is saved. Order = md5(seed + entry id), so anyone with the entry list and seed gets the same result.
- Winners are not told by the draw. An admin presses "Tell them", which sends an in-app notice. Declined, no reply or not eligible: the next reserve becomes the winner.
- Export: CSV, full admins only, logged. File name `Promotions_<slug>_Entries_<from>_to_<to>.csv`.
- Personal details (name, mobile, email, address hash) are cleared after the retention period (default 180 days after closing), when an admin opens Promotions. Counts stay.
- Rate limit: 10 entries an hour per account (`/rpc/promotion_enter`).

## Pages
- `/giveaway/` opens `#/promotions/current` (the open promotion) and keeps `?src=`.
- `#/promotions/<slug>?src=<channel>`: the public page and form.
- Admin: `#/admin/promotions` (switch, list, new draft), `#/admin/promotion/<id>` (report, entries, draw, links, codes, details).

## Placeholders
- `promo_contact_phone` setting: the one number winners are called from. Empty until James sets it.
- Permit number, T&C text, prize, dates: entered per promotion.
- Winner notice goes to the in-app inbox only until SMS (Africa's Talking) and email are connected.

## Not built yet
Notifications branch (SMS, outbox, announcements), referral and offer types, public winners list, NIN/TIN.
