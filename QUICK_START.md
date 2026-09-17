# Tampa Signs and Stickers - web application v0.2

## What you have

This ZIP is the updated web app, backend, tests, logos and deployment instructions. It is not an executable and it is not live on the internet yet. Customers will use the website in a browser; they will not need Docker or an installation. Docker is only one way for the server administrator to host it.

The storefront, client portal and staff tools use your Tampa Signs and Stickers branding. Customer progress is only Order received / In production / Finished. Staff keep detailed tasks and internal notes privately. Staff access is at `/staff`, not a link in the public header.

## Standard products versus custom jobs

Eligible stickers, labels, magnets, banners and supply-only signs can use immediate purchase once configured. Each online order has one product/size/design and a quantity. Wraps (including print-only wrap panels), installation, oversized items and review-only products stay custom quotes. Supply-only products can be added separately from installed/replacement services.

Optional Stripe-hosted card checkout is implemented for immediate orders. QuickBooks invoice links remain available for custom jobs, with manual receipt verification. No payment account is connected by this archive. Stripe orders are not automatically synchronized with QuickBooks. Printing still waits for the latest complete proof approval after payment.

## First: choose where it will live

A possible public address is `orders.tampasigns.net`, if that is the subdomain you authorize. It has not been configured. Use one persistent HTTPS web server, with database/artwork storage, backups and access controls. The project includes a single-server Docker/Caddy deployment recipe and guidance for a managed host with persistent storage. These require an authorized hosting account/domain and may have ongoing costs.

The deployment instructions are `signshop-os/docs/DEPLOYMENT.md`. A deployer should use the separate `compose.production.yaml`, not the local demo Compose file, and verify it in staging. No Docker image or public deployment was tested in this environment.

## Then: configure the shop

Sign in to the staff workspace using the initial credentials printed securely by the server on first startup. Change the password and protect the startup logs.

In Products & rates, replace every sample rate with your real material/labor costs and selling prices. Set supported dimensions and quantity limits. Review instant purchase / installation / wrap flags. Catalog edits affect new orders; existing orders keep their saved pricing.

In Shop settings, confirm the business contact details, pricing, checkout terms, real pickup address, verified pickup tax and any shipping option. Online purchases remain off until the catalog and tax/delivery settings are confirmed and a payment account is configured.

## Connect payment in test mode first

Use `signshop-os/docs/CHECKOUT.md`. Put Stripe credentials in the server's protected secret/environment settings, never in this chat or browser code. Configure and test the signed event endpoint before accepting real payments. The included default is disconnected; the screenshots use a fake test gateway and synthetic receipts.

The current shipping option is US flat rate with Stripe Tax, not a carrier quote or shipping-label system. It must be configured and checked against your eligible products. Automatic order email/SMS is not connected; customers receive a private link on screen to save. Add reliable transactional email before unattended public launch.

## Local preview only

Extract the ZIP, open a terminal in `signshop-os`, then:

```sh
docker compose up --build
```

Open `http://localhost:8000/` and `http://localhost:8000/staff`. The owner email for a fresh local demo is `owner@example.test`; its password is generated and printed on first startup. This command does not publish the app. Do not use `down --volumes` or delete the data volume if it contains work you need.

## Upgrading an existing v0.1 installation

Back up database plus artwork first. Test v0.2 against a copy. It adds checkout tables and settings while retaining existing jobs. Preserve the existing data volume/project name. Do not overwrite your working database with any demonstration data. See the full backup/upgrade instructions before changing a live installation.

## Verification

75 backend tests passed. Actual interface render/interaction checks completed through a local DOM/API bridge. Real hosted checkout, Docker deployment, DNS/HTTPS and production security still need acceptance testing. Full details: `docs/TEST_REPORT.md`.
