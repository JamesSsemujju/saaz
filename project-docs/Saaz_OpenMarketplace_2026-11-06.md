# Open marketplace and the Build Assistant for staff (6 Nov 2026)

## Open marketplace (part 26)

Allan's request: every car can be on Saaz, marked Inspected or Not inspected. One switch: Admin, Settings, `open_market` (type `true` or `false`). It is off when part 26 is run.

With it on:
- Seller: "List now, not inspected" next to "Submit for a Saaz inspection". Saaz approves the car, it goes live marked Not inspected. The inspection path is unchanged.
- Buyer, on a Not inspected or expired car: make an offer as it is, or "Ask for a Saaz inspection". The usual garage line runs while the car stays on sale. The garage is told the buyer pays its fee. When the seller books the garage, the buyer gets the garage's name and phone to agree the fee. No money moves through Saaz.
- The report goes on the car for everyone (James).
- A safety Fail does not take the car off sale. Every Saaz report of the car (same VIN, across listings) shows on its page, pass or fail (James: transparency). Saaz can approve a car whose report failed.
- An expired inspection leaves the car on sale, shown as Inspection expired.
- Buy cars: the heading reads "Cars on Saaz" and an "Inspected only" filter appears once any car on sale isn't inspected. With only inspected cars it reads "Saaz certified cars", as before.

Who asked for an inspection is stored (`reviews.requested_by`) and never shown to the garage, the seller or other buyers.

Fixed on the way (Certain): since part 21 a seller opening Edit on their own draft got "Couldn't load this page" (vehicles were readable by admins only). Part 26 lets a seller read their own cars' vehicle record again.

Not built: the seller asking for a Saaz inspection on a car that is already live (today they can when listing). Payment through Saaz.

## Build Assistant for the whole team (part 27)

- Everyone on the Saaz team (Admin or Staff, after their authenticator) can open the Build Assistant.
- An admin's request is queued at once. A staff request shows "Waiting for admin approval"; admins are told; an admin presses Approve (queued for the agent) or Decline (with a reason the staff member sees). Staff can edit their request until it is approved.
- Only admins switch the assistant on or off and approve.

## Sign-up email (6 Nov 2026)

Allan's sign-up failed with "Error sending confirmation email". Auth log (Certain): the mail server answered `550 Unrouteable address` for `allanl@saazinvestsmentsltd.com`. The domain has an extra "s" (saazinvest**s**mentsltd). No account was created. The page now says: "We couldn't send an email to that address. Check it for typing mistakes".
To add Allan as staff: he creates his account with the right address, confirms the email, then an admin adds him on Admin, Team.
