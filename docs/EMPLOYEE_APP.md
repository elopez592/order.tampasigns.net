# Tampa Signs employee phone app

Open **https://orders.tampasigns.net/staff/app** and sign in with a staff account.

- **iPhone:** open in Safari → Share → Add to Home Screen. Enable Open as Web App if offered.
- **Android:** open in Chrome → menu → Install app / Add to Home Screen.
- Create staff accounts in the existing shop workspace: **Team**. Employees use their individual staff credentials; customers use the customer portal.

## Employee workflow

**Today** shows the employee's accepted task queue, owned projects and unsynced survey drafts. **Queue** separates My queue, Available and All tasks. Accept a task to claim it, start/pause its timer, record a blocker, and finish it. Existing quote, deposit, proof, survey and task dependency gates still apply.

**Clients** reads and writes the same CRM used by the owner. Employees can add/update contact details and notes. An email address is needed for an order estimate. Existing-email duplicates are rejected. Client pricing profiles are matched to the existing wholesale account by its saved email; no separate rate table is maintained.

**Surveys** capture a site address, on-site contact, access/installation notes, surface conditions, removal requirements, labeled measured areas and photos/PDFs. Every area has its own width, height, quantity, unit and suggested product. Units can be inches, feet, millimeters or centimeters. Original units are retained; estimates use server-normalized inches.

Device drafts auto-save while entering measurements and retain selected photo files in IndexedDB. Save to shop uploads the survey and files. Submit for review locks the survey. The owner verifies measurements against the order and proof or reopens the survey. An owner can also open **Record completed survey** in the desktop project or **Review & complete survey** in the mobile project. These forms show the current quote alongside every saved field survey and its photos. Each pending survey requires its own confirmation; completing the review verifies the exact saved versions together. Save any phone drafts to the shop first. A linked pending survey continues to block production. Verifying one survey does not clear other pending surveys for the same project. Linking a previously verified standalone survey to a new order requires reviewing it against that new order.

Use **New client** next to the survey's client selector to create and select a CRM contact without leaving the survey or losing measurements/photos. Client creation requires a connection. A saved survey or a survey linked to an existing project keeps its original client.

Every measured panel and estimate line has **Add panel photo (optional)**. Survey panel photos stay with their panel when areas are added or removed, survive offline draft saves, and carry into estimates made from that survey. Choose, replace or remove a photo before saving the estimate. Staff can also update photos from the project's scope before customer acceptance or production. Panel reference photos appear beside the corresponding quote line in the staff workspace, printable documents and the customer's private quote portal. General survey photos/files remain staff-only. Panel photos use separate records and do not count as artwork proofs or approvals. Upload retries preserve one estimate and one current photo per line; older invoice snapshots retain their original images.

Create an estimate from a submitted survey to carry its dimensions and notes into product lines. Choose and review the product, material, laminate, finishing, quantities and finished sizes. Saved rates and quantity breaks are calculated by the same server pricing engine. Apparel supports garment colors, sizes and placements; different colors/placements can be separate lines. Mixed products retain the applicable production workflow branches. Employees cannot override rates, costs, taxes or the owner's financial controls.

Standard estimates can be sent after rates and configured pickup tax have been reviewed. Custom/installation estimates require owner review in the existing shop workspace. Location-specific tax and shipping/delivery are reviewed by the owner; the field calculation displays the configured pickup tax rate. Saving an estimate creates an assigned project and links it to the existing CRM client and source survey.

**Invoices** are immutable, numbered records of the order scope and financial totals at creation. Accepted, published, charge-reviewed scopes create issued invoices; other scopes create clearly marked draft invoices. Repeated creation of the same version/status returns the existing invoice. Draft and issued records remain distinct. View the document and use Print / Save PDF. Payments recorded elsewhere in this system remain authoritative; invoice documents show payments/balance when created. Use **Approve price & send invoice** in the mobile project when the client agrees to the scope and total in person. Confirm the client name, quoted scope, tax-inclusive total and recipient email; the system records the staff witness, quote version and total, then creates an issued invoice and emails its private link. Owners can explicitly review the displayed charges in this form; employees need prior owner review for unreviewed charges. Already accepted orders offer **Send client invoice**. Failed email delivery leaves the issued invoice intact and offers retry or copying the private link. The client can open, print / save a PDF and return to the order page from that link. Price approval and invoicing do not approve artwork, record payments or complete pending measurement reviews. These documents do not create or synchronize QuickBooks invoices.

**Proofs** are attached in the project's Proofs tab. Upload a complete PNG/JPEG/PDF package and confirm it covers all items and finished sizes. The existing portal and versioned artwork/sizing terms are used. The app reports whether email delivery was accepted. A failed send leaves the proof in the portal and offers a retry. No client approval is recorded by an employee upload, and the existing instant-preview approval behavior remains unchanged.

## Offline behavior

The installable shell is available after the first connected visit. Existing device survey drafts, including selected photos, can be reopened without a connection within eight hours of the last authenticated visit. New CRM changes, price calculations, task actions, proof sends and invoices require a current server session and connectivity. Reconnect and explicitly save drafts to the shop; there is no promise of background uploading while the app is closed. Do not clear browser/app storage before syncing device drafts.

The header and bottom menu sit outside the scrolling content area in a fixed app frame. Content scrolls inside that frame on phones, including short landscape screens. New app-shell versions update cached styles and scripts on a connected reload; close/reopen the installed app after an update if an old view is still open.

Drafts are partitioned by staff identity and retained on the same device for the employee's next sign-in. Signing out clears the remembered identity and live workspace data. Device storage is not a replacement for a server backup. Server survey saves, photo uploads and estimate creation use identifiers so retrying a dropped request does not duplicate records. Survey versions detect conflicting edits instead of overwriting another employee's work.

## Integration and verification

The `/staff/app` companion uses the existing staff session, CSRF boundary, SQLite database, CRM, pricing engine, task action endpoints, proof publication and transactional email. New tables are additive and survey photos remain private to staff. The service worker caches only static/public shell resources, never staff API responses, files, credentials or CRM lists.

Backend coverage is in `tests/test_employee_mobile.py`. `scripts/verify_employee_browser.mjs` exercises sign-in, client creation, offline photo/measurement recovery, sync, survey-to-estimate conversion, catalog/tax totals, draft/issued invoices, task claim/timers, proof attachments and owner measurement verification against an isolated demo app. `scripts/verify_survey_invoice_browser.mjs` covers owner survey review from desktop and mobile, on-site approval, invoice delivery failure/retry, and the private client invoice link. The browser check reports are stored with the source under `docs/previews/`. Preview screenshots are generated locally and excluded from the public release.
