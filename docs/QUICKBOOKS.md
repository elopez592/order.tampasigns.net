# QuickBooks custom-job link mode - v0.2

Standard online orders can optionally use the separate Stripe integration in `CHECKOUT.md`. The instructions below apply to custom quotes/wraps and manual QuickBooks receipts only. Automatic QuickBooks invoice creation, OAuth and reconciliation are still not connected. Never enter a Stripe receipt again as a manual QuickBooks payment in this app.

# QuickBooks payment links - implemented mode and integration boundary

## Implemented: links plus shop-verified payments

This release does not connect to your QuickBooks account. It stores a link created in QuickBooks, opens that link for the client, and tracks receipts that the owner verifies manually. No card data is collected or stored here.

1. Publish the reviewed quote and obtain customer acceptance.
2. Create the appropriate customer invoice/payment request in your own QuickBooks account. Confirm the customer, amount, deposit/balance treatment and permitted payment methods there.
3. In the job's **Payments** tab, attach the genuine online invoice payment URL and invoice reference. Prefer a job-specific invoice URL for a job that already has an invoice.
4. The client selects **Pay in QuickBooks**. The destination handles payment.
5. Verify the actual payment and its allocation in QuickBooks. Then use **Record verified payment** with amount and a unique transaction/reference identifier.
6. The app recalculates the local paid balance and deposit/production gates. Repeat with a distinct verified reference for the final payment.

Payment links must use HTTPS and an allowed Intuit/QuickBooks hostname. The code rejects lookalike suffixes, embedded credentials and nonstandard ports. Host validation does not prove that an invoice belongs to your business or matches the job: the owner must check it before sharing.

A client clicking **I paid** sends an unverified notice only. A return visit from a payment website, a screenshot of a payment, or a redirect is not treated as authoritative proof of receipt.

Repeated submission of the same payment reference and amount is idempotent. The app rejects a conflicting reused reference and a payment greater than its local outstanding balance. A **void/correction** reverses only the local bookkeeping entry. It does not issue a refund, change QuickBooks or cancel a payment.

## Invoice links and standalone payment links are different

Intuit documents that standalone payment links require QuickBooks Payments, cannot be used to follow up on a previously sent invoice, and produce sales receipts in QuickBooks Online. It also says customers cannot change the amount or make a partial payment through a standalone payment link. Do not treat a generic reusable link as automatic settlement of a particular invoice.

The application lets the owner label a destination as an **Invoice** or **Payment link**. This is a description, not an API reconciliation. Your bookkeeping process must match the kind of request you actually created.

Official source, reviewed September 17, 2026:

`https://quickbooks.intuit.com/learn-support/en-us/help-article/payment-methods/payment-links-quickbooks-desktop/L6onPNJpn_US_en_US`

## Next integration: not implemented yet

Automatic integration requires an Intuit developer application, your authorized QuickBooks Online company, proper OAuth credentials/redirect URLs, token storage/refresh, and sandbox testing. This source package does not include a pretend Connect button or placeholder credentials that suggest a live connection.

Proposed development sequence:

1. Add OAuth authorization with state validation, correct company/realm binding, encrypted refresh tokens, restricted secret access and a disconnect flow.
2. Map app customers/products/jobs to QuickBooks IDs. Decide invoice versus deposit/sales-receipt accounting behavior with the business before automating writes.
3. Create or update invoices with idempotency and record remote IDs. Obtain the actual customer-facing invoice payment URL where the authorized account/API supports it.
4. Receive and verify supported webhook notifications, then retrieve authoritative remote entities and reconcile payments to the matching invoice/job. Treat notifications as prompts to fetch state, not as unconditional proof of payment.
5. Handle partial payments, reversals, duplicate delivery, refunds and failed synchronization with a visible owner review queue.
6. Exercise sandbox scenarios, then perform a limited real-account launch with monitoring and reconciliation procedures.

Intuit's official authorization reference:

`https://developer.intuit.com/app/developer/qbo/docs/develop/authentication-and-authorization/oauth-2.0`

No credentials should be committed into the source repository or sent to clients. A browser automation/plugin connection in a chat is not a substitute for the deployed application's own authenticated Intuit integration.
