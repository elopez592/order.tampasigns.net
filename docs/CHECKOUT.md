# Hosted checkout and payment handoff - v0.2

This integration is optional and disabled initially. No real account or payment is included. Fake providers exist only in the automated tests, not the running application entrypoint.

## Two separate payment paths

**Standard online orders:** Stripe-hosted card checkout, full payment upfront, signed payment events saved automatically. No card details enter this application's forms/database. A verified receipt does not approve a proof. These orders are immutable in price/fulfillment after submission; changed scope should be a new reviewed job with refund/cancellation handled deliberately.

**Custom jobs/wraps/installation:** staff-reviewed quote, customer's explicit quote acceptance, QuickBooks invoice link, admin verifies actual receipt in QuickBooks and records its reference. This is manual QuickBooks bookkeeping integration, not OAuth or synchronization. Do not add an additional manual payment to a Stripe order; the app blocks that double-counting path.

The Stripe addition is an alternative for immediate purchases, not a change made to the owner's QuickBooks account. Stripe fees, account eligibility and accounting synchronization are outside this package. If the shop requires every instant purchase to use QuickBooks instead, leave Stripe disabled and implement/test a separate Intuit invoice/payment integration before enabling instant purchases. A reusable generic payment link does not establish a trusted per-order paid total.

## Server configuration

Required process environment variables:

```text
STRIPE_SECRET_KEY=<server-side Stripe secret for this account and environment>
STRIPE_WEBHOOK_SECRET=<signing secret for this exact webhook destination>
PUBLIC_URL=https://orders.your-domain.example
APP_ENV=production
```

Use test credentials for staging and a separate live endpoint/key set for production. No publishable key is needed for the redirect-to-hosted-page approach in this release. Credentials are not editable in a browser form and are not returned to staff/customer APIs. Use the hosting provider's secret store or a tightly permissioned untracked environment file. Never commit or send secret keys through chat.

Create a Stripe webhook destination at:

```text
https://orders.your-domain.example/api/payments/stripe/webhook
```

Subscribe to these snapshot event types:

```text
checkout.session.completed
checkout.session.async_payment_succeeded
checkout.session.async_payment_failed
checkout.session.expired
charge.refunded
charge.dispute.created
charge.dispute.closed
```

The application pins REST calls to `2026-02-25.clover`. Use and test a compatible webhook snapshot API version with the session/charge fields consumed by `app/checkout.py`. Configure the destination secret on the server and restart. Monitor the provider's event deliveries and application logs. A general API secret and the webhook signing secret are different values.

## Shop settings checklist

- Catalog reviewed (`rates_live`).
- Checkout enabled (`checkout_enabled`).
- Verified confirmation of tax/delivery/terms (`checkout_tax_reviewed`).
- At least one configured fulfillment option.
- Eligible product: instant enabled, within supported dimensions/quantity, no wrap or installation classification.

Both provider secrets must be present. If any setup requirement is missing, the calculator falls back to a quote request and does not present a working purchase button. The backend enforces the same rule even if a browser request is modified. A test connection displays a test-storefront notice.

## Tax and delivery

**Pickup:** enter the actual pickup address and the applicable rate the shop has independently verified. No rate is assumed correct. A matching Stripe TaxRate is applied to the merchandise and included in the frozen order calculation. Zero is permitted for properly verified situations, but is not an assertion that the shop's sales are tax-free.

**Shipping:** optional US-only flat charge per order. Hosted Checkout collects the shipping address and uses Stripe Tax automatic calculation. Finish Stripe Tax registration and default product-tax configuration in the account before enabling. Tax completion, server-priced subtotal and fixed shipping are checked before crediting payment. There are no carrier rates, dimensional shipping, address-validation service or label purchase. Confirm a single rate actually covers every enabled product/size; otherwise keep shipping disabled or restrict eligible products.

Owner attestation is a release control, not tax advice. Handling mixed taxability, exemptions, international orders or per-product shipping needs further implementation/review.

## Payment integrity

- Server creates a price snapshot from the validated product, size, quantity and current catalog, never from a browser-supplied amount.
- Terms, customer confirmation, fulfillment settings and tax/shipping policy are saved with the submitted order.
- The order/request id and hosted session are idempotent. Repeated clicks reuse a saved open session; expired sessions are checked before replacement.
- Webhooks require raw-body HMAC validation, a current signature timestamp, expected test/live mode and an event id. CSRF is exempt only on this signed provider endpoint.
- A matching checkout reference, currency, paid status, current quote version, merchandise subtotal, tax and shipping are required. Mismatches require review instead of clearing a balance.
- Paid-page navigation, a customer payment notice and an unverified provider URL do not credit the job.
- Duplicate events and session receipts do not create duplicate credit. Refund/dispute notifications reduce available credit and affect subsequent production/delivery gates. Already completed physical work cannot be undone by a webhook.
- Process refunds in Stripe; this version does not issue refunds from staff UI. Monitor refund/dispute events and reconcile periodically. There is no scheduled accounting-reconciliation service.

## Provider acceptance test still required

The automated suite uses fake network sessions and signed synthetic events. Before launch, make a controlled end-to-end Stripe test purchase on the staging URL, verify the exact hosted amount and tax, cancel/retry, replay a webhook, approve/revise artwork, refund, verify portal/staff balances and test delivery gates. No live money was moved during development. Do not assume the supplied Docker or hosting configuration has been deployed/tested.

Official references checked September 17, 2026:

- https://docs.stripe.com/checkout/quickstart
- https://docs.stripe.com/api/checkout/sessions/create?api-version=2026-02-25.clover
- https://docs.stripe.com/webhooks/signature
- https://docs.stripe.com/tax/checkout
