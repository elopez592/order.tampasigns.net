# Tampa Signs employee phone app

Open **https://orders.tampasigns.net/staff/app** and sign in with a staff account.

- **iPhone:** open in Safari → Share → Add to Home Screen. Enable Open as Web App if offered.
- **Android:** open in Chrome → menu → Install app / Add to Home Screen.
- Create staff accounts in the existing shop workspace: **Team**. Employees use their individual staff credentials; customers use the customer portal.

## Employee workflow

**Today** shows the employee's accepted task queue, owned projects and unsynced survey drafts. **Queue** separates My queue, Available and All tasks. Accept a task to claim it, start/pause its timer, record a blocker, and finish it. Existing quote, deposit, proof, survey and task dependency gates still apply.

**Clients** reads and writes the same CRM used by the owner. Employees can add/update contact details and notes. An email address is needed for an order estimate. Existing-email duplicates are rejected. Client pricing profiles are matched to the existing wholesale account by its saved email; no separate rate table is maintained.

**Surveys** capture a site address, on-site contact, access/installation notes, surface conditions, removal requirements, labeled measured areas and photos/PDFs. Every area has its own width, height, quantity, unit and suggested product. Units can be inches, feet, millimeters or centimeters. Original units are retained; estimates use server-normalized inches.

Device drafts auto-save while entering measurements and retain selected photo files in IndexedDB. Save to shop uploads the survey and files. Submit for review locks the survey. The owner verifies measurements against the order and proof or reopens the survey. A linked pending survey continues to block production. Verifying one survey does not clear other pending surveys for the same project. Linking a previously verified standalone survey to a new order requires reviewing it against that new order.

Create an estimate from a submitted survey to carry its dimensions and notes into product lines. Choose and review the product, material, laminate, finishing, quantities and finished sizes. Saved rates and quantity breaks are calculated by the same server pricing engine. Apparel supports garment colors, sizes and placements; different colors/placements can be separate lines. Mixed products retain the applicable production workflow branches. Employees cannot override rates, costs, taxes or the owner's financial controls.

Standard estimates can be sent after rates and configured pickup tax have been reviewed. Custom/installation estimates require owner review in the existing shop workspace. Location-specific tax and shipping/delivery are reviewed by the owner; the field calculation displays the configured pickup tax rate. Saving an estimate creates an assigned project and links it to the existing CRM client and source survey.

**Invoices** are immutable, numbered records of the order scope and financial totals at creation. Accepted, published, charge-reviewed scopes create issued invoices; other scopes create clearly marked draft invoices. Repeated creation of the same version/status returns the existing invoice. Draft and issued records remain distinct. View the document and use Print / Save PDF. Payments recorded elsewhere in this system remain authoritative; invoice documents show payments/balance when created. These documents do not create or synchronize QuickBooks invoices.

**Proofs** are attached in the project's Proofs tab. Upload a complete PNG/JPEG/PDF package and confirm it covers all items and finished sizes. The existing portal and versioned artwork/sizing terms are used. The app reports whether email delivery was accepted. A failed send leaves the proof in the portal and offers a retry. No client approval is recorded by an employee upload, and the existing instant-preview approval behavior remains unchanged.

## Offline behavior

The installable shell is available after the first connected visit. Existing device survey drafts, including selected photos, can be reopened without a connection within eight hours of the last authenticated visit. New CRM changes, price calculations, task actions, proof sends and invoices require a current server session and connectivity. Reconnect and explicitly save drafts to the shop; there is no promise of background uploading while the app is closed. Do not clear browser/app storage before syncing device drafts.

Drafts are partitioned by staff identity and retained on the same device for the employee's next sign-in. Signing out clears the remembered identity and live workspace data. Device storage is not a replacement for a server backup. Server survey saves, photo uploads and estimate creation use identifiers so retrying a dropped request does not duplicate records. Survey versions detect conflicting edits instead of overwriting another employee's work.

## Integration and verification

The `/staff/app` companion uses the existing staff session, CSRF boundary, SQLite database, CRM, pricing engine, task action endpoints, proof publication and transactional email. New tables are additive and survey photos remain private to staff. The service worker caches only static/public shell resources, never staff API responses, files, credentials or CRM lists.

Backend coverage is in `tests/test_employee_mobile.py`. `scripts/verify_employee_browser.mjs` exercises sign-in, client creation, offline photo/measurement recovery, sync, survey-to-estimate conversion, catalog/tax totals, draft/issued invoices, task claim/timers, proof attachments and owner measurement verification against an isolated demo app. The browser check report is stored with the source under `docs/previews/`. Preview screenshots are generated locally and excluded from the public release.
