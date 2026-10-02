# Company subscriptions

Platform Control: https://orders.tampasigns.net/platform
Mirakol billing and free access tests: https://mirakol.tampasigns.net/staff/billing

The platform owner’s Tampa workspace is included. Mirakol is enrolled as a free pilot, with no setup charge or recurring charge. Its owner can test active/trial access, failed renewal with seven days of grace, expired grace, cancellation at period end, cancellation, and recovery. Simulations are restricted to pilot companies and never create a Stripe customer or payment.

Draft monthly plans are Starter ($99, 3 staff seats), Studio ($199, 10 seats), and Business ($399, 25 seats). Seats include the owner. All include the branded ordering site, mobile staff app, CRM, estimates, proofs and production workflow. Review the rates and subscription tax requirements before enabling paid signup in Platform Control. A separate Product and recurring Price exist for each tier in Tampa’s Stripe account. No companies have been subscribed by deployment.

For a paying company, select Stripe billing in Platform Control. Publish its eligible plan and enable paid signup after reviewing prices and tax. The company owner chooses a plan from its billing page. Server-side checkout uses the published Stripe price, validates current staff count, prevents duplicate checkout/subscription creation, and preserves the workspace address. Checkout returns do not grant access.

Signed Stripe subscription and invoice events retrieve the current subscription before changing access. Repeated and reordered events are safe. Failed renewals receive seven days of grace without extension on retries. Cancellation at period end retains access until Stripe ends the subscription; immediate cancellation, incomplete/unpaid/paused subscriptions, expired trials and expired grace pause access. A stale active subscription period receives a maximum seven-day webhook outage buffer. Billing-page status refresh also reconciles provider state. Workspace data is retained. Company owners can still sign in to billing, update payment details, view invoices, change plans, and cancel through the Stripe portal. Portal upgrades invoice prorations; downgrades take effect at period end.

Platform billing uses root-only server credentials and a dedicated signing secret, independent of each tenant’s customer-order payment connections. On this deployment, `PLATFORM_BILLING_USE_SHOP_ACCOUNT=1` explicitly uses Tampa’s existing server Stripe key. A dedicated restricted key can replace it using `PLATFORM_BILLING_SECRET_KEY`. Required permissions cover Customers, Prices read, Subscriptions read, Checkout Sessions, Billing Portal, and Charges read for risk events. Keys/signing secrets stay in hosting variables and never enter the repository or browser. Mode/signature mismatches are rejected. The event endpoint is `/api/platform/billing/webhook`; existing order-payment webhooks continue separately.

Stripe Price changes require a replacement Price with matching currency, interval and amount. History preserves old subscribers’ financial terms and seat limits. Refund/dispute events flag the company for platform-owner review; they do not automatically destroy data or cancel a contract.

Subscription tax collection is not automatically enabled. Do not assume Stripe Tax collects tax without active registrations and the correct SaaS product tax code. Review tax settings/registration and validate a calculation before configuring collection. Paid signup is initially disabled and plans are initially unpublished, while all pilot test controls are available immediately.

Checks cover signed events, duplicate/reordered events, current-state reconciliation, historical prices, customer/subscription ownership, recovery routes, owner authorization, cross-company isolation, seat selection, pilot scenarios, and real Stripe SDK request encoding. Test fixtures do not charge cards. For real Stripe test cards/test clocks, connect a dedicated Stripe sandbox with its own platform key, webhook signing secret, price IDs and portal configuration; never use test cards in the live account.

## Feature tiers

| Plan | Staff seats (owner included) | Desktop storefront, CRM, quoting, manual proofs, production | Mobile staff app | Instant proofing | Product generators |
| --- | --- | --- | --- | --- | --- |
| Starter | 3 | Included | — | — | — |
| Studio | 10 | Included | Included | Included | Included |
| Business | 25 | Included | Included | Included | Included |

Capabilities are resolved from the company registry and subscription plan on every request. Pilot plan changes take effect immediately in cached tenant apps. Tampa's included workspace and legacy manual contracts retain their capabilities. Mirakol remains a free Studio pilot.

Starter products become quote/review products without changing stored catalog configuration. Uploaded manual proofs and their approvals remain available; new instant checkout/self-approval and panel generation are rejected server-side. Generated design payloads cannot bypass the calculator. The mobile entry point, manifest, worker, surveys and requests marked by the installed staff app are blocked on Starter. An installed app shows an upgrade screen on reconnect; a received denial clears its cached shell. Previously saved offline drafts remain on the device. Shared desktop APIs remain available for desktop workflows.

New or reactivated users are capped by the effective tier. After a downgrade, only the first allowed active seats (admins first, then creation order) can use authenticated staff actions; an owner can deactivate extra accounts or upgrade. Data and accounts are retained. Legacy contract seat overrides cannot increase paid-plan caps. Pilot seat counts come directly from the tested plan.
