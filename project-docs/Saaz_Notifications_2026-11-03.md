# Saaz Notifications (3 Nov 2026)

SMS through Africa's Talking, an outbox, message settings, a mobile check by code, and announcements. James chose Africa's Talking on 3 Nov 2026.

Status: **database live since 4 Nov 2026** (part 24, run by James in the SQL Editor after approving it). Not yet: the Edge Function `send-outbox` (deploy, then its Africa's Talking secrets). Until then SMS wait in the outbox and every notice lands in the in-app inbox, as before.

## How a notice becomes an SMS
1. The marketplace writes a notice (`notifications`) with its channels, as before.
2. If an admin changed the channels for that kind of notice (Admin, Outbox, Channels for each notice), those win.
3. For SMS, one outbox row is written. It is queued only if the person has a Ugandan mobile, verified by code (`sms_needs_verified`, on), allows SMS alerts, and the number isn't on the opt-out list. Otherwise it is kept as "Not sent" with the reason.
4. Email copies are held: no email sender is connected yet.
5. `send-outbox` takes due SMS (codes first, then alerts, then news), sends each through Africa's Talking, and records sent (with message id and cost) or the error. Up to 3 tries, 1, 5 and 30 minutes apart. A bad number fails at once. A low balance, risk hold, bad sender name or gateway error stops the run and puts the rest back.
6. The app asks `send-outbox` to run after actions (at most every 30 seconds per open tab). Part 24b (optional) runs it every minute with Supabase Cron.

## Mobile check
My account, Mobile number: Send me a code by SMS. 6 digits, 10 minutes, 5 tries, one a minute, 5 a day. Stored only as a hash; its text leaves the outbox once sent. Changing the mobile clears the check (as before). Once SMS works, turn on `require_phone_verified` in Settings so listings, offers and promotion entries need a verified mobile.

## Announcements (Admin, Communications, Announcements; full admins)
Audience: everyone, sellers, buyers, certified garage teams, or a promotion's entrants. Everyone gets it in the inbox. SMS only to people who opted in (My account, News and offers by SMS, or the marketing tick on that promotion), verified, not opted out. SMS wait for 08:00 to 20:00 EAT. "Check who gets it" shows counts, why others get no SMS, the SMS parts, and the cost once `sms_price_ugx` is set. Limit `sms_max_audience` (20,000).

## Custom audience (BA-0013, part 25, 4 Nov 2026; not live yet)
James chose C: filters plus named people. Filters (all must hold; empty ones ignored): who they are (sellers, buyers, garage teams; any of), verified mobile only, active in the last N days, joined in the last N days, car makes and models they listed or saved. Named people (found by name, email or mobile) are added on top; with no filters, only they get it. Suspended accounts never do. The check shows the count and up to 10 names. The Sent list records how the audience was chosen. No country filter: Saaz is Uganda only.

## Set-up (James or Allan; type keys only in the Supabase dashboard)
1. Africa's Talking: account for Saaz Investments Ltd, an app, apply for the sender name SAAZ (Likely about 2 weeks, MTN and Airtel), top up a test amount, ask for the Uganda price per SMS.
2. Approve part 24 in a live chat. The agent applies it.
3. Deploy the function: `supabase functions deploy send-outbox` (or the agent deploys it through the connector after approval).
4. Supabase, Edge Functions, Secrets: `AT_USERNAME`, `AT_API_KEY`, and `AT_SENDER_ID` once SAAZ is approved. Using `sandbox` as the username sends to the Africa's Talking simulator only.
5. Settings: `sms_price_ugx` (price of one SMS part).
6. Optional: part 24b for the every-minute schedule (turn on pg_cron and pg_net first).
7. Check: verify your own mobile from My account. Admin, Outbox shows the sender's last run and each SMS.

## Placeholders and limits
- Price per SMS: not set (no quote yet).
- Delivery reports from the networks are not read yet: "Sent" means Africa's Talking accepted it.
- SMS can't take replies, so opting out is My account, or an admin adds the number (Admin, Outbox, SMS opt-outs).
- Email: held until an email sender is chosen (project-docs/email-and-notifications.md).
- WhatsApp: the promotion tick is recorded; sending needs a WhatsApp provider.
