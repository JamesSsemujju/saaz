# Email and notifications

## Findings (17 Oct 2026)

| Question | Finding | Source | Certainty |
|---|---|---|---|
| Is a Saaz-owned domain set up? | Yes: saazinvestmentsltd.com (James's own email address uses it) | DNS A record 104.194.11.128 | Certain |
| Where is its mail handled? | MX `0 saazinvestmentsltd.com`, the same server as the website | Google public DNS | Certain |
| What server is it? | Reverse DNS of 104.194.11.128 is nexus.crystalcloudhost.com: a shared hosting server. Fits the Roundcube 1.6.19 webmail with Webuzo plugins you saw | DNS PTR | Certain (record); Likely (shared hosting) |
| SPF | `v=spf1 a mx ip4:104.194.11.128 ~all`: mail from that server is allowed | DNS TXT | Certain |
| DKIM | Selector `default` publishes an RSA key | DNS TXT | Certain |
| DMARC | `v=DMARC1; p=none;` (monitor only, no reports address) | DNS TXT | Certain |
| mail.saazinvestmentsltd.com | Not checked: the DNS lookup was rate-limited | | No source |
| Mailboxes, SMTP username, password, ports | Not known here. Never send them to me; enter them only in the Supabase dashboard | | |
| What does Supabase send today? | Only to members of the Supabase project's team, at a low hourly limit. Customers get nothing | supabase.com/docs/guides/auth/auth-smtp | Certain |
| The "sample domain" | The host's own name (nexus.crystalcloudhost.com) is not Saaz's and must not be the sender | | Likely |

**What Roundcube is:** a webmail screen for reading and writing mail by hand. It shows the hosting account can hold mailboxes; it is not, by itself, an email service for the app.

## Recommendation

Use a sending address on the Saaz domain, `noreply@saazinvestmentsltd.com` (see below), and plug it into Supabase as custom SMTP (Authentication, Emails, SMTP Settings). Two routes:

| Route | How | Good | Risk |
|---|---|---|---|
| A. Your hosting mail server | Create the mailbox in Webuzo; in Supabase enter host (usually the domain or mail.saazinvestmentsltd.com), port 465 (SSL) or 587 (TLS), the mailbox as username, its password | No new supplier; SPF and DKIM already match this server | Shared server: its reputation with Gmail is unknown; hosting plans often cap hourly sends |
| B. A sending service (Resend, Brevo, Postmark, Amazon SES) | Verify saazinvestmentsltd.com there; add its DKIM and SPF records; use its SMTP details in Supabase | Better delivery, bounce reports, higher limits | One more account; DNS changes |

My lean: start with A to unblock today, move to B before public launch (Likely better delivery; not measured).

After either: set DMARC to `p=quarantine` with a reports address once mail passes for two weeks; turn "Confirm email" back on; raise Supabase's email rate limit to fit.

**Verification still needed:** send a password reset to a Gmail address outside the team; check it arrives in the inbox, not spam; open "Show original" and confirm SPF, DKIM and DMARC say PASS.

## Sender addresses (decided 17 Oct 2026, Allan working on set-up)

| Address | Used for | Sent by |
|---|---|---|
| `noreply@saazinvestmentsltd.com` (created by Allan, 17 Oct 2026) | Account emails: confirm email, password reset, garage invite, email change. No replies expected | Supabase Auth, through custom SMTP |
| `info@saazinvestmentsltd.com` (created by Allan, 17 Oct 2026) | Replies and questions (named in every email's footer); later, messages to all users | Not built yet: needs the email queue below and a consent line in sign-up |

## Email journeys (built in the app 17 Oct 2026, delivery waits for SMTP)

| Journey | Email | Link lands on | Then |
|---|---|---|---|
| Garage added by admin, or member added by owner | "Set up your garage account" (`email-templates/invite-user.html`), from noreply | Set your password (verifies the email) | Garage dashboard, signed in as Garage team |
| Sign up as a seller | "Confirm your email" (`confirm-signup.html`) | Signed in | My cars, as Seller |
| Sign up as a buyer | Same | Signed in | Browse |
| Forgot password (anyone) | "Reset your password" (`reset-password.html`) | Set a new password | Their dashboard |
| Change email | "Confirm your new email" (`change-email.html`) | Account | |

## How the templates are made

`supabase/email-templates/email-config.json` holds the footer details (help address, phone, company name, address, TikTok, Instagram and YouTube links). `python3 tools/make_email_templates.py` writes the 6 templates from it. Set 17 Oct 2026: phones +256 705 298 524 and +256 705 276 226; TikTok and Instagram @saaz__automotive with the icons James supplied; YouTube link not given yet (hidden). Empty values are left out, so nothing invented ever goes out.

Images: an email can't carry the logo inside it. Email apps download it from the live site (`assets/img/brand/saaz-wordmark-black-240.png`), so it shows once the site is shipped. PNG, not WebP or SVG, because Gmail and Outlook don't show those reliably. Some apps hide images until the reader allows them; every image has alt text ("Saaz").

## Set-up steps in Supabase (once Allan has the mailbox)

1. Authentication, Emails, SMTP Settings: enable custom SMTP. Sender email `noreply@saazinvestmentsltd.com`, sender name `Saaz`, host, port (465 SSL or 587 TLS), username and password of that mailbox. Typed in the dashboard only.
2. Authentication, Emails, Templates: paste each file from `supabase/email-templates/` into its template, with these subjects:

| Supabase template | File | Subject | Needed by Saaz? |
|---|---|---|---|
| Confirm sign up | `confirm-signup.html` | Confirm your Saaz email | Yes: every new buyer and seller |
| Invite user | `invite-user.html` | You're invited to Saaz | Yes: garage owners and inspectors |
| Reset password | `reset-password.html` | Reset your Saaz password | Yes: everyone |
| Change email address | `change-email.html` | Confirm your new Saaz email | Yes: Account page |
| Reauthentication | `reauthentication.html` (shows a code) | Your Saaz security code | Only if "Secure password change" is turned on; branded in case |
| Magic link or OTP | `magic-link.html` | Your Saaz sign-in link | Not used (Saaz signs in with a password); branded so nothing unbranded can go out |
3. Authentication, URL Configuration: Site URL `https://jamesssemujju.github.io/saaz/app/`; Redirect URLs add `https://jamesssemujju.github.io/saaz/app/**` (the links carry `?next=seller` or `?next=garage`).
4. Authentication, Sign In / Providers, Email: turn "Confirm email" on.
5. Authentication, Rate Limits: raise emails per hour to fit (start at 30).
6. Test: sign up with a Gmail address that is not on the Supabase team, open the email, check SPF, DKIM and DMARC say PASS under "Show original".

## Emails by event

Auth emails (sent by Supabase once SMTP is set): sign-up confirmation, password reset, email change, invite (`invite-user` function). Templates: Supabase Authentication, Emails, Templates; brand them with the Saaz name, one clear button, the link expiry.

Business notices (stored in `notifications` with intended channels; delivered in-app today):

| Notice | Trigger | Recipient | Channels intended |
|---|---|---|---|
| garage_applied | Garage applies or resubmits | Admins | app |
| garage_certified, more_info, rejected, suspended | Admin decision | Garage owner | app, email, SMS |
| member_invited | Owner adds an existing user | That user | app, email, SMS |
| garage_in_play | Car put in play | Garage team; seller | app, SMS (garage) |
| garage_message, seller_message | Chat message | The other side | app |
| seller_agreed, seller_passed, garage_released, review_date, assigned | Garage line steps | Garage or seller | app |
| line_empty | No garage left | Admins; seller | app |
| review_issued | Review issued | Seller; admins if approval needed | app, email, SMS |
| listing_approve, changes, reject, unlist | Admin decision | Seller | app, email, SMS |
| review_void | Admin voids | Garage; seller | app |
| offer_received, offer_rejected, offer_auto_rejected, deal_counter, deal_propose | Offers | Seller or buyer | app, SMS (offer received) |
| deal_agreed, sale_completed | Deal | Buyer, seller, admins | app, email, SMS |

## What's missing for reliable email (F-14)

1. An `email_outbox` record per email: queued, sent, failed, attempts, last error (never the message body with tokens, never passwords).
2. A sender: an Edge Function that sends queued business emails through the same SMTP, retries 3 times with back-off, and marks failures.
3. An admin view: failed emails with safe details and a Retry button (Outbox tab has the place for it).
4. Templates: one Saaz layout, mobile-friendly, with a link back to the right page.

Built only after the sender (route A or B) is chosen, so it's tested against the real thing.

## Email links and invites (17 Oct 2026)

**Finding (Certain, Supabase auth log 17 Oct 12:21 UTC):** the first invite link to cenakamoga@gmail.com was opened twice in the same second, once from a Google address (Gmail checking the link) and once from the phone. The one-time link was used up, so the phone showed "This link has expired".

**Fix:** email buttons now open `app/?token_hash=...&type=...#/confirm`. The page uses the one-time code only when the person taps (and, for invites and resets, after they type a password). Link checkers open the page but don't tap. Templates use `{{ .TokenHash }}`, so they must be pasted again.

**Expiry:** emails say links work 24 hours. Set Supabase: Authentication > Sign In / Providers > Email > Email OTP Expiration = 86400. The database setting `email_link_hours` (24) drives the "link expires" time on the Team pages; keep both equal.

**Invites:** owners (Team page) and admins (garage page) see each invite: not sent yet, sent at, link expires at, or expired. Buttons: Send or Resend invite, Revoke. Resend to someone whose account exists but never set a password sends a set-password (reset) email. Revoke on an unsent invite marks it revoked (part 9); on a sent invite it removes the membership. Every action is in the audit log.
