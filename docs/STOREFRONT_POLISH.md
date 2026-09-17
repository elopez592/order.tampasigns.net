# Storefront presentation update, September 17, 2026
This is a frontend-only update. No database migrations, rate changes, payment-provider activation, DNS changes, or modifications to saved orders are included.
- Scoped responsive storefront styling in `app/static/storefront.css`.
- Ten stable inline SVG product icons, keyed by product characteristics, not list order.
- Exact aliases for starter catalog names, preserving owner-renamed products and all stored order snapshots.
- Large public demonstration-pricing banner removed. Estimates still say Estimated total, and the order form and receipt explain that confirmation and payment are pending. Internal example-rate notices remain. Test-payment warnings remain.
- Standard products: Place order. Actual review-required product lines, oversized work, wraps and installation: Request a quote.
- Checkout is still gated by the server's aggregate review flag and provider availability. No paid status is inferred from submitting an order.
- Accessible pressed states, labeled dialogs, reduced-motion styling, scoped focus indicators, and static asset cache versioning.
- An input edit invalidates older in-flight pricing responses, and order details cannot open with stale dimensions.
## Verification
- Python regression suite: 75 passed in the local environment.
- `node --check app/static/app.js` passed.
- `node tests/test_storefront_ui.cjs`: 20 checks passed.
- Chromium desktop/mobile rendering and interactions exercised via a local in-process API bridge. Verified standard vs custom buttons, local test-order submission and portal confirmation, staff login/internal notice, quantity changes, oversized dimensions, and no horizontal document overflow at 320, 390, 768, 1024 and 1440 pixels. No JavaScript exceptions.
- Browser network navigation is restricted in the local environment; the browser/API bridge is not a hosted TLS, real-email, or payment-gateway test. No real customer orders or payments were created by these tests.
- Product illustrations are examples, not generated print-production files.

