# Tampa Signs and Stickers - web storefront and shop workspace

Version 0.2.0 | September 17, 2026 | Updated from SignShop OS 0.1

A connected web application: customers use a browser; staff use a private authenticated workspace on the same server. No customer desktop installation is required. This archive is application source and deployment configuration, **not an already hosted website**.

## What changed

- Supplied Tampa Signs and Stickers logos, teal/black interface, restrained orange accents. The PDF branding references informed the palette; the web colors are adaptations, not certified print color values.
- Public navigation is Products & pricing / Your order. Staff sign in directly at `/staff`; there is no public header link to staff tools.
- Customers see exactly **Order received / In production / Finished**. Production task names, assignments, internal notes, material-ordering checklists and internal reference layouts are removed from customer API responses. Staff retain the full checklist and time tracking.
- Eligible fixed-size, non-installed products can be purchased immediately once checkout is configured. All wraps, installation, oversized and review-only products remain custom quote requests. Catalog administrators can change eligibility, size limits and prices.
- Optional Stripe-hosted card checkout for standard orders. A verified provider event or authenticated provider reconciliation records payment; a success-page visit or a customer saying they paid does not.
- Existing QuickBooks invoice/payment links remain available for custom jobs with owner-verified receipts. Automatic QuickBooks synchronization is not included.
- Production still requires the accepted scope, latest complete approved proof, payment requirement and prerequisite tasks. Payment alone never approves artwork.

## Readiness

**Do not accept live orders until deployment, pricing, taxes/delivery, terms, security, and a real payment-provider test are reviewed.** The package defaults to demonstration prices and disabled online checkout. There is no connected Stripe or QuickBooks account in this archive.

The backend suite passed 75 tests. The actual frontend was rendered and exercised through a local DOM/API bridge; the public hosted site, Docker image, DNS/TLS, mobile devices and a real Stripe transaction have not been tested. See `docs/TEST_REPORT.md` for boundaries.

## Local evaluation (not internet deployment)

Extract the ZIP and open a terminal in `signshop-os`.

```sh
docker compose up --build
```

Open `http://localhost:8000/` for the storefront and `http://localhost:8000/staff` for staff. First start prints randomly generated credentials, unless an initial password was explicitly configured. The local demo owner's email is `owner@example.test`. Save credentials privately and change them after sign-in. Keep the terminal/server running.

The local Compose file intentionally listens only on loopback, loads demonstration jobs and stores data in the named `signshop_data` volume. `docker compose down` stops services without deliberately deleting the volume. **Do not use `--volumes` or `down -v` with data you need.**

A Python alternative, exercised with Python 3.13:

```sh
python -m venv .venv
# macOS/Linux:
. .venv/bin/activate
# Windows PowerShell instead: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run.py --demo
```

The included Dockerfile selects Python 3.12. Its build still requires verification in a Docker-capable environment. The app reads process environment variables, not arbitrary `.env` files automatically.

## Put it on the internet

Use a single persistent server, a real domain/subdomain, HTTPS, backups and monitoring. A deployment operator can use the included `compose.production.yaml` + Caddy example. **Do not use the local demo Compose file as a public deployment recipe.** See `docs/DEPLOYMENT.md`.

A suggested URL structure, not a provisioned domain:

```text
https://orders.your-domain.example/         Customer storefront
https://orders.your-domain.example/portal   Customer private-link entry
https://orders.your-domain.example/staff    Staff login
```

A managed Docker host with a persistent disk is another option. This version uses SQLite/local uploads and one app instance; it is not a stateless/serverless or multi-replica package.

## Activate standard-product checkout

1. Deploy a separate HTTPS staging environment. Keep live customer traffic away from it.
2. Configure server-only Stripe **test** credentials and the webhook endpoint described in `docs/CHECKOUT.md`. Never put secret keys in frontend code, screenshots, source control or a chat message.
3. Review each product's material, dimensions, cost, labor, selling price, minimum and quantity bands. Sample pricing is not a supplier quote or recommended retail price.
4. In Shop settings, review shop identity, public rates, checkout terms, pickup address/tax and optional US flat-rate shipping. Shipping also requires completed Stripe Tax setup.
5. Enable checkout and explicitly confirm reviewed tax/delivery settings. Products must also permit instant purchase and not require installation or be wraps.
6. Exercise complete test orders: paid/cancelled, proof revision/approval, duplicate webhook, refund, delivery and task gates. Then deliberately switch to live keys and a live endpoint secret after sign-off.

Each standard order is one product/size/design, with quantity. There is no multi-product cart. Artwork may be uploaded at order time or later in the portal. The order is paid upfront; printing waits for proof approval.

## Staff and customers

Staff: Job board / My task queue / Products & rates / Workflows / Team / Shop settings. Admins manage products/rates, employee roles, manual custom-job payment verification and workflow templates. Employees claim jobs/tasks, start/pause work, record blockers and finish tasks.

Customers: receive a private one-job link to accept custom quotes, review/approve a proof, upload artwork, view simple progress, send a message and pay. Links expire after 14 days or replacement; sessions expire after 8 hours. These are bearer links, not verified customer accounts. Keep them private. Staff can create replacement links. **Automatic order emails/SMS are not connected**; the public order flow displays a link for the customer to save. Add transactional email before unattended public launch.

The original $1,400 storefront job remains a demonstration draft, not a verified profit statement. Existing real v0.1 installations must back up their data before upgrade; never replace an actual database with the preview database.

## Deliberate limitations

No automatic QuickBooks invoice creation/reconciliation, no card entry in this app, no live-account credentials, no tax/legal assurance, no automated emails, MFA or verified customer accounts. Shipping is optional US flat rate, not carrier quoting or label generation. Label core/roll direction and other material variants need separately configured products or a custom quote. No supplier ordering, inventory decrementing, AI artwork/photo compositing, print-ready RIP/cut export, multi-instance persistence or offline sync.

Uploaded PNG/JPEG files are normalized. PDFs are download-only with limited format checks; add scanning/quarantine, quotas and retention before broad public uploads. Complete a production security review and backup/restore test.

## Source and tests

```text
app/main.py        HTTP, authentication and authorized routes
app/checkout.py    hosted sessions, immutable orders, signatures, receipts
app/domain.py      job totals, privacy projections, approval/payment gates
app/pricing.py     server-side Decimal pricing and eligibility
app/static/        responsive UI and the supplied logo assets
app/schema.sql     schema versions 1 and 2 (additive checkout tables)
manage.py          backup and local staff password recovery
compose.yaml       local demonstration only
compose.production.yaml / deploy/Caddyfile   single-server HTTPS recipe
docs/              deployment, checkout, pricing, workflows, test report
```

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Read `docs/CHECKOUT.md`, `docs/DEPLOYMENT.md`, `docs/PRICING.md`, `docs/QUICKBOOKS.md`, `docs/WORKFLOWS.md`, `docs/TEST_REPORT.md`. Third-party packages retain their own licenses. The supplied logo artwork remains the user's branding.
