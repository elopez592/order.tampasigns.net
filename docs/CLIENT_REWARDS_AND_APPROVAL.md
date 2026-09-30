# Client rewards, upload approval and work terms

When a client uploads finished artwork, they can review the instant previews,
assign the files to each printed product, explicitly approve the package and
continue to payment. The exact uploaded files become the approved proof. The
same artwork does not need a second approval. Uploading or paying by itself does
not approve artwork. Clients can choose a shop proof instead, and custom design,
installation and wrap projects retain shop review.

## Customer and owner behavior

- **Staff > Client rewards:** the owner can search registered customer accounts,
  add or deduct dollar credits and points, enter a reason visible to the client,
  and review the balance history. Employees cannot change balances or settings.
- **Customer account:** clients see available credits, points, their value and
  account history. A signed-in account must match the order email. Existing guest
  orders can be linked using their private order page and the matching account.
- **Checkout / private order page:** clients can apply credits or points before
  opening payment checkout. Balances are reserved immediately. Clients or the
  owner can safely return unused balances; an open provider checkout is expired
  first. A paid balance cannot be released as though it were unused.
- **Default program:** 1 point per eligible merchandise dollar paid, with each
  point worth 1 cent (1% back before rounding to whole points). The owner can
  change the earning rate, point value or pause earning and redemption. The
  earning rate for a recorded payment is retained for later adjustments.
- **Dollar credits:** promotional merchandise discounts recorded in the shop
  account. Granting credit does not execute a card refund. Credits and redeemed
  points reduce merchandise before tax and exclude shipping. They have no expiry
  or maintenance fee. The original $35 combined-cart minimum still applies.

Verified card payments and owner-verified payment records earn points. Refunds,
disputes and voided payment records reverse the associated earnings. Verified
card refunds return applied credit and points proportionally and only once.
If already-spent earned points are reversed, the account displays an adjustment
due; future points first cover it. A fully covered pickup order completes without
creating an unnecessary card charge.

## Artwork, sizing and site surveys

The versioned Artwork, Sizing & Production Terms are shown directly on the
website at checkout, quote acceptance and proof approval. The client order page
uses a required checkbox and an **Approve artwork & accept terms** action in the
same step. `/terms` is a branded public website page with the full terms and
links to every section. It is linked from customer navigation, the storefront
footer and the order proof area.
Acceptance records retain the signer, timestamp, method, exact terms, quote
scope and artwork manifest. The terms require clients to verify content,
dimensions, quantities and fit; explicitly approved artwork is final. Once
printed, client-requested corrections or resizing require a new paid order.
Production defects and work that differs from the approved proof can be reviewed
and corrected.

Each approved proof displays who approved the artwork and terms and when. The
accepted text remains accessible in the private order page even after a later
update to the public terms. Clients do not need to download or sign a PDF.
Pending portal proofs display the sizing and production notice and expandable
full terms beneath the artwork. Uploaded proofs, generated panel proofs and
proof resends all notify clients to review the artwork and terms together using
their private order link. The original artwork files remain the exact files
being approved.

The new upload-preview approval route requires the current terms version. Older
API clients remain compatible with existing checkout/proof routes, but requests
without an explicit terms version do not create a record claiming acceptance of
the new versioned contract.

A site survey is optional and costs extra. Its fee and appointment are confirmed
with the client separately. Selecting it at checkout creates a quote request
and holds printing. A requested survey also prevents artwork approval until the
owner records completion. If measurements change, revise the quote and obtain
approval of the changed artwork/scope. Production checks compare the approved
proof specifications with the current order, so an old sizing approval cannot
authorize a changed print. A price-only change can keep the same artwork proof.

## Validation and release

- Full Python regression suite: **181 passed**, including website terms,
  retained artwork/contract acceptance, proof notifications, checkout privacy and
  pre-upgrade backup restoration/failure behavior. Tests use isolated databases,
  demo identities and a fake payment gateway. No real orders, charges or client
  messages were created during verification.
- JavaScript: **all seven test files passed**, and every frontend module passed
  syntax checks. Coverage includes multi-product artwork assignment and complete
  selection before approval.
- Financial checks include concurrent redemption, owner permissions, duplicate
  requests/events, pickup tax, shipping exclusions, checkout expiration, verified
  payments, partial/full refunds, spent-point reversal and zero-charge checkout.
- Existing migration fixtures now remove subsequent schema versions when
  simulating an old database. Three incorrectly escaped source-match patterns in
  the existing embroidery test were corrected; its production code is unchanged.
- Browser verification is **pending**. This environment lacks an installed local
  Chromium, its browser download returned an invalid archive, and the available
  cloud browser blocks local preview addresses. The local-only
  `scripts/verify_rewards_preview_browser.mjs` describes the customer and owner
  desktop/mobile flow for an isolated demo using `FakeGateway`.

The database upgrade is additive schema version 11. Existing checkout/order
snapshots and owner-customized terms are preserved. Only the exact legacy
default checkout consent is replaced; missing reward settings receive defaults.
Before upgrading an existing database, startup automatically creates a private
`/data/backups/pre-v11-<timestamp>.zip` containing the original database and uploaded
artwork. Backup failure stops startup before schema changes; successful version
11 starts do not repeat the backup. The regression suite checks restoration and
failure behavior. Older application
versions that support only schema 10 reject a schema 11 database; roll back with
a matching backup or a schema-compatible corrective release.

The owner authorized publication and deployment on September 30, 2026. The active
customer portal is `https://orders.tampasigns.net/`, Railway project
`triumphant-clarity`, service `19538cdf-eceb-4865-b16f-8e50cefed24f`, production
environment `1343e23c-7aab-47ec-bd10-a38071d585b7`. Its existing `/data` volume,
production configuration and scheduled reminder service are retained.
