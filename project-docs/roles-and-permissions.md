# Roles and permissions

Enforced in the database: row-level read rules on every table, and every change through a function that checks the caller. Hiding a button is never the only control. Signed-out visitors can't call any action that needs an account (part 5).

| Area | Visitor | Buyer (any account) | Seller (any account, own cars) | Garage inspector | Garage owner | Admin |
|---|---|---|---|---|---|---|
| Browse live cars, reports, verify, what's selling | View | View | View | View | View | View |
| Account | Sign up | Own profile, password, email | same | same | same | Others: view; set trusted, suspended, admin (not own) |
| Listings | | | Create, edit draft, submit, price change, withdraw (until reserved), offer rules | See cars in play for their garage | same | View all; approve, request changes, reject, unlist; Saaz cars as seller |
| Garage line messages | | | Own cars | Own garage's cars | same | Counts only; full text on Saaz-owned cars |
| Pass reasons | | | Own | Never | Never | View |
| Reviews | Issued ones | same | Own cars incl. drafts status | Start, save, issue own draft; see team drafts | same | View all; void with reason |
| Offers and deals | | Make, counter, accept, withdraw own | Counter, accept, reject on own cars | | | Propose, mark agreed (note), complete, cancel |
| Contacts | | After agreement | After agreement | | | |
| Garages | | Apply | | | Add and remove members, resubmit | Approve, more info, reject, suspend, reinstate, add directly (reason) |
| Settings, audit, outbox | | | Own car history (admins shown as "Our team") | | | Full |
| Export | Not built for any role |

Tests that prove it (local stack): another user can't change a listing; buyers can't read messages; admins can't read non-Saaz messages; garages can't read pass reasons; users can't read other profiles; audit can't be deleted; visitors can't call internal or sign-in-only functions; admins can't change their own access. See `testing-and-release.md`.
