# Customer visibility and staff workflows - v0.2

Customers see only **Order received / In production / Finished**. Their portal still shows relevant quote/payment information, artwork approval and messages. Internal tasks, departments, assignees, blocked reasons, time entries, internal notes and reference layouts are staff-only, enforced by the backend as well as the UI. Old public workflow events are filtered/sanitized for the customer projection.

All original detailed staff workflows remain. Standard online orders begin with an accepted, fixed quote and a full upfront payment requirement; production still requires the latest complete proof approval and prerequisite tasks. Custom jobs retain explicit quote acceptance and configurable deposit requirements. Opening a payment page or returning from checkout is not payment verification.

A refund/dispute can block subsequent production/delivery steps but cannot reverse completed physical work. Staff must review affected jobs and act operationally. Finishing remains derived from staff job progress, not a customer-editable status.

# Jobs, employees and proof approvals

## Roles

| Capability | Owner/admin | Employee | Private client link |
|---|---|---|---|
| View shop job board | Yes | Yes | No |
| View internal costs/margin | Yes | No | No |
| Create staff jobs and publish quotes | Yes | No | No |
| Create public estimate request | Yes | Yes | Public flow |
| Edit rates/settings/workflows/team | Yes | No | No |
| Claim jobs and tasks | Yes | Yes | No |
| Upload source artwork | Yes | Yes | Own job only |
| Publish a complete proof | Yes | Yes | No |
| Accept quote / decide proof | Through private client portal | Through private client portal | Own job only |
| Attach link / verify payment | Yes | No | No |
| Send updates | Yes | Yes | Own job only |

Employees are trusted shop staff who can view operational records across the shop, not only assigned jobs. They cannot see the internal price/cost snapshots returned to the owner. Job claiming records overall responsibility; individual tasks can be claimed by different employees.

## Task lifecycle

The queue shows available, owned and blocked work. Start/resume requires dependencies and applicable gates to be satisfied. Start opens a timer, pause/block closes it, and complete records completion and elapsed tracked time. Release clears the employee's task claim when allowed. Task time is operational tracking, not a payroll system or automatic invoice adjustment.

Claims use transactional checks so two employees cannot claim the same task successfully at once. Staff cannot overwrite someone else's task claim. Owners can change overall job ownership through the schedule dialog.

### Gates

| Gate | What must be true before starting |
|---|---|
| `none` | Prerequisites complete; active job |
| `quote` | Prerequisites plus current published quote accepted |
| `deposit` | Current quote accepted plus required deposit verified |
| `production` | Prerequisites, accepted quote, latest complete proof approved and required deposit verified |
| `delivery` | Production requirements plus full remaining balance verified |

The default templates allow intake first, purchasing after deposit, and design after quote acceptance. The first production step requires both purchasing and design to be done. Change these business rules deliberately in **Workflows** if your process differs.

Seed templates cover stickers/labels, banners, signs/storefronts, installed wraps and print-only wrap panels. They include printing, appropriate cure/lamination reminders, trimming/cutting, fabrication, quality checks and delivery. Material-specific cure times and installation procedures are instructions your shop must provide; the application does not invent or validate them.

Workflow changes affect future jobs only. Existing task checklists are snapshots. For a mixed-product job, the owner selects one job-level workflow and can add tasks before production; the software does not automatically merge all selected products' workflows.

Templates require at least one production-gated task and a final delivery-gated task. Dependencies point to earlier step numbers. Job status is derived from the quote, proof, payment and task records, not a free-form drag that bypasses checks. The board currently displays up to 500 recent active jobs; the queue displays up to 300 open tasks.

## Quote and proof versions

Customer quote acceptance records the current quote version, typed name and timestamp. Financial revisions clear acceptance and the previously attached payment link, requiring republishing and review. Product-rate edits do not retroactively alter a saved job.

A proof is a complete package covering every quoted item. Staff must confirm this when uploading a PNG/JPEG or a multipage PDF. The app cannot visually prove that an uploaded PDF covers every item; this is a staff responsibility.

Generated panel proofs require assigned image artwork for every item. A blank reference layout is never approval-eligible. Images are displayed at a consistent relative scale; they are not a full-size design/cutting template or a storefront placement drawing.

The customer can approve only the latest pending proof or request changes. Approval records the exact stored file's SHA-256, version, name, checklist statement and time. A new version becomes the current approval requirement without erasing older decisions. A change request requires a new proof package before approval can occur. Missing or altered proof files block approval.

After production starts, a new proof or financial revision requires a separate change-order job. The app does not silently replace approved artwork midway through production.

## Private links and file sharing

A customer link grants access to one job and expires after 14 days. Only a hash of its secret token is stored. The URL fragment token is exchanged for a job-scoped session, then removed from the browser address. Replacing the link invalidates previous links and existing portal sessions.

This is possession-based authorization. A typed name is not independently verified identity, and the system is not a certified e-signature service. Share links privately with the intended approver and use a stronger account/verification flow before use cases requiring it.

All uploaded job artwork is intended to be customer-visible on that job. Do not upload confidential shop-only production files there. Staff activity messages have a separate public/private choice; internal notes remain hidden from clients. Uploaded PDFs are downloadable rather than embedded, but no malware scanning is included.

Messages and review changes appear in the portal and job activity. Server-side email/SMS notifications are not configured: staff must check the board and share updates manually until a notification integration is added.
