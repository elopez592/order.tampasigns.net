# Test and verification report - v0.2.0

September 17, 2026. Tests were run against the updated source, not the old spreadsheet or static interface sketches.

## Backend

Observed full run: **75 passed in 63.25 seconds** on Python 3.13.5. The retained output is `test-output.txt`. It includes the original 43 backend cases plus 32 new/parameterized checkout and privacy cases.

Covered: pricing validation and rate snapshots; session/role/CSRF checks; customer-only visibility; private artwork/proof access; complete current-proof approval gates; standard-product eligibility; wraps/installation/oversize rejection; immutable server-priced orders; idempotent request/session creation; signed webhook validation, test/live and amount mismatch rejection; duplicate receipt prevention; payment success redirects not proving payment; tax/shipping reconciliation; partial refund/dispute and early adjustment handling; expired-session retry; task prerequisites, employee actions and financial gates.

Payment network requests used the test FakeGateway. Signature validation and local reconciliation were exercised with synthetic events. **No real Stripe or QuickBooks account, credit card, charge, refund, transfer or accounting action was performed.** The passing cases are not a penetration test or guarantee of financial correctness for every provider/account configuration.

## Frontend and rendering

`node --check app/static/app.js` passed. The actual CSS/JavaScript was rendered in Chromium using local DOM content and an HTTPX bridge to the running local backend. Quantity selection updated pricing; print-only wraps switched to quote requests; customer portal displayed exactly three stages without staff tasks; complete proof actions and a synthetic paid receipt rendered; staff tasks and owner checkout controls rendered; a 390-pixel storefront had no horizontal page overflow. No JavaScript page errors were captured in this harness. Screenshots were visually inspected.

Browser network navigation to local HTTP was blocked by the execution environment's administrator policy. That policy was not bypassed. Therefore these are actual-UI render/interaction checks through a controlled bridge, **not an end-to-end browser-network test of the deployed site**. Screenshots contain synthetic customers, demonstration prices and a synthetic payment receipt; they are not evidence of a live store.

See `ui-render-report.json` and `previews/`.

## Not yet verified

- Docker build/run with the selected Python 3.12 image; Caddy server recipe; deployment provider, domain, DNS, TLS and proxy behavior.
- Real Stripe test-account and live-account hosted checkout, actual webhook delivery/retries, automatic tax configuration or QuickBooks account integration.
- External mobile devices/browsers, load/concurrency capacity, dependency security audit, penetration testing or accessibility certification.
- Supplier prices, tax/legal correctness, refund policy, shipping sufficiency, real job profit or business availability.
- A production backup/restore drill and an upgrade rehearsal on the owner's real data copy.

Use a separate staging site and complete the launch checklist in DEPLOYMENT.md and CHECKOUT.md before public ordering.
