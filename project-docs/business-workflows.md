# Business workflows

Every step below is enforced by a database function (named in brackets). The website only calls them. Each change writes an `audit_log` row; notices go to the in-app inbox (email blocked, see F-01).

## Workflow matrix

| Workflow | Entry point, who | Inputs and rules | Status changes | Notices | Failure and recovery | Final outcome, how the user knows | Admin view |
|---|---|---|---|---|---|---|---|
| Sign up | `#/signup`, anyone | Name, email, mobile, password 8+. Uganda only | account created, profile made (trigger `handle_new_user`) | Confirmation email (blocked, F-01) | Neutral error, no account enumeration | Signed in, or "check your email" | Users, account page |
| Password reset | `#/forgot` | Email | none | Reset email (blocked) | Expired link page offers a new one | "Set a new password" page, then signed in | Account history |
| Change password, email | `#/account`, signed in | Password twice; new email | | Email confirmation for email change (blocked) | Mismatch and re-sign-in messages | Toast | |
| List a car | `#/sell/new`, seller | VIN 6 to 17 (17 never I, O, Q); UG plate; year 1980 to next year; mileage not below Saaz readings; 4 to 12 photos; 30+ characters; price from UGX 1,000,000; logbook or authorisation; 3 active unless trusted (`save_listing`, `submit_listing`) | draft, awaiting_review | Garage and seller told who is in play | Each rule returns a plain sentence | Car page shows the progress strip | Cars, car page |
| Garage line | automatic on submit (`put_next_in_play`) | Nearest certified garage in Uganda with an Active member (part 6), not the seller's own, not tried this round | conversation in_play | Garage (app, SMS) and seller | Pass (`seller_respond`), decline (`garage_respond`), 24-hour time-out (`tick`); empty line tells admins; restart or assign (`admin_restart_line`, `admin_assign_garage`); re-queue when a garage is ready (part 6) | Seller sees the garage and the chat | Garage line counts; car page |
| Agree and book | seller agrees after the garage messages | Garage must have messaged | agreed; listing review_booked | Garage | Release by garage brings the next garage | Garage sets the review date | |
| Saaz review | `#/garage/review/<id>`, garage member | All 12 checks; notes if not all Pass; odometer; in-person box (`start_review`, `save_review`, `issue_review`) | review issued; listing awaiting_approval, or live for trusted sellers, Saaz cars, Pass with no odometer flag | Seller (app, email, SMS); admins | Draft locked to one member; discard; void by admin brings the line back | Report with number, score and verify code | Car review reports |
| Approve listing | `#/admin/car/<id>` | Note needed for changes, reject and unlist; safety Fail can't be approved (`admin_decide_listing`) | live, changes_requested, rejected, withdrawn | Seller | Seller edits and resubmits | Car public on Saaz | |
| Offer and deal | `#/car/<ref>`, buyer | At least 50% of asking; seller rules; one open offer per car (`make_offer`, `deal_action`) | negotiating, auto_rejected, agreed (car reserved, others on hold), completed (car sold), cancelled | Seller, buyer, admins | Auto-reject tells the rule, never the minimum; cancel reopens held offers | Contacts appear after agreement | Deals |
| Garage application | `#/garage/apply` | Business details; honest-reviews declaration (`apply_garage`) | applied, more_info, certified, rejected, suspended (`admin_decide_garage`) | Admins; owner | Resubmit after more info; suspension passes cars on | Garage team sign-in opens | Garage page with history |
| Garage added by admin | `#/admin/garage-new` | Reason required (`admin_add_garage`) | certified at once; owner invited | Invite email (needs F-01, F-21) | Owner can sign up with that email instead | Owner becomes Owner on sign-up | |
| Team member | `#/garage/team`, owner | Email, role (`add_garage_member`) | invited, active on first garage sign-in, removed | Invite email (blocked) | Removal discards their drafts | | Garage page |

## Listing states

draft → awaiting_review → review_booked → awaiting_approval → live → reserved → sold.
Side states: changes_requested (back to draft edits), rejected, withdrawn (seller, until reserved), re_review_due (review older than 60 days; resubmit).

## Proposed workflow: enquiries (not built, needs approval)

Entry: "Ask about this car" or "Report this listing" on a car page, and "Help" for general questions. Inputs: topic, message; for reports a reason. Status: open, assigned, answered, closed (with reason). Rules: one open enquiry per person per car; contact details hidden as in the garage line; seller answers car questions, admins handle reports and help. Notices: seller or admins on new; asker on answer. Admin: queue with filters, assign, close.
