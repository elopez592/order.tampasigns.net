# Delete company

Platform Control includes **Delete company** under each company card. Only the platform owner can use it. Type the exact company ID and submit the confirmation. Stripe companies also require the billing cancellation checkbox.

Removal hides the company from the active list and denies all workspace, storefront, login, support, billing and asset routes. The registry row, private company database, uploads, connections and invoice/tax history remain retained for recovery; this feature does not permanently erase files. Company IDs and hostnames remain reserved to protect those records and existing payment references. There is no customer-facing restore route.

## Billing cutoff

Before removal, the server uses only the stored platform billing IDs and credentials to:

- Retrieve and verify a pending signup Checkout Session, expiring it if still open.
- Discover a subscription from a completed checkout even if its webhook has not yet arrived.
- Retrieve and verify the ownership of linked subscriptions, then cancel them immediately with `invoice_now=false` and `prorate=false`. There is no automatic refund or final proration invoice.
- Verify cancellation before marking the workspace removed. Failed or unconfirmed billing calls leave the company in the list for review/retry.

Stripe invoices remain available in Stripe. Existing company order payments are separate from SaaS subscription billing. The archived company's signed order-payment webhook remains routable so already-started customer payments can settle, without restoring interactive access. Subscription lifecycle events cannot reopen a removed company.

## Server controls

`DELETE /api/platform/companies/{slug}` requires platform-owner authentication, CSRF, the latest integer `revision`, the exact `confirm_slug`, and explicit `cancel_billing=true` if linked billing or checkout exists. Removal is serialized with subscription checkout/webhook processing, audited, and idempotent. Support grants and pending signup records are revoked, and the cached workspace is removed. The included Tampa workspace has no deletable company registry entry.

Tests cover role and tenant isolation, confirmations, CSRF, stale revisions, retained files, revoked access/support, protected company IDs/domains, late events, checkout/subscription ownership, completed checkout before webhook, billing failures and unconfirmed cancellation, plus the browser confirmation flow.
