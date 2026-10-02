# Company platform operations

This release adds owner-managed company branding and a platform control console.
Visit `/staff#company` for identity, image uploads, draft preview, publication,
branding history and restrictive employee profiles. Existing products, rates,
workflows, team accounts and payment policy controls remain company-local.

The platform console at `/platform` requires an active admin whose email matches
`PLATFORM_OWNER_EMAIL`, or `ADMIN_EMAIL` when that optional variable is absent.
It never grants company owners access to other companies. Configure that address
explicitly if the shop's initial account email differs from the current operator.

## Provisioning and domains

Company creation installs the standard catalog without copying the root shop's
jobs, customers, staff, uploaded files, prices edited in the root shop, integration
secrets or sessions. A temporary password is returned once. Each company keeps
its own database and private files under `DATA_DIR/companies/<slug>/`. All
companies share one deployment and repository for the initial pilot; this is
process-level hosting with separate storage, not separate containers. Browser
storage and cookies remain isolated by distinct company origins.

Company domains must be registered in Platform Control and attached to the
existing Railway service, with the DNS records returned by hosting configured
and verified. This console does not change DNS. Do not share a workspace until
its certificate and domain are ready. Unknown hosts return 404 and never route
to Tampa Signs. Root production domains are reserved. Change a registered
company domain through its platform card; configured redirect URLs at external
providers must be updated independently.

## Platform owner support access

Use **Manage company** on a connected company's card to enter its workspace
without using its password. **Company sign-in** remains the normal login for
the subscribing business. Companies without a domain show a connection notice;
entering a hostname here does not provision hosting or DNS.

Support access uses a company/hostname-bound, single-use link that expires in
60 seconds, passed only in the URL fragment and removed before exchange. Its
host-only session lasts at most one hour and is checked against the original
platform owner session on every request. Signing out of the platform, disabling
the platform owner, changing the domain, pausing the company or ending its trial
invalidates support access. This creates no staff seat and changes no password.
Support actions identify the platform operator in activity logs. The workspace
banner identifies the company and **Return to Platform Control** ends the support
session before returning. The owner password form is unavailable in support mode.

Connect each shop's own sales-payment account through its company connections.
Use the company's displayed webhook URL. The root sales account and email
provider never become defaults for new companies. Secret values are stored in
private, mode-0600 files and are never returned by list endpoints or audit logs.
An operator with filesystem access can read them. Backups contain those secrets
and must be protected. Only trusted platform operators may configure connections.

## Access and subscription contracts

Statuses: trial, active and past_due allow access; suspended and closed deny
workspace access while retaining all records. A configured trial end denies
access on the following UTC date. A blank end date does not expire a trial.
Status changes are checked on every request, even for existing sessions.

Staff seats count all active owner and employee accounts. Creating or activating
an account beyond the limit is denied. Disable excess staff before reducing a
limit. Role changes revoke all affected sessions. Existing owner/employee role
checks still apply: restrictive profiles do not grant owner capabilities.
`employee` retains prior employee behavior; sales, designer, production,
survey_install and read_only restrict staff write operations server-side. Staff
read access remains the existing employee scope. This version does not add
fine-grained visibility controls or delegated company-admin roles.

Monthly/setup prices and billing notes are manual contract records only. There
is no automatic SaaS subscription charging, cancellation portal, invoice retry,
subscription webhook or automatic past-due policy in this release. The shop's
existing product/order checkout remains separate. A later subscription phase
must connect dedicated platform billing credentials, signed idempotent webhooks,
customer/subscription IDs, recurring checkout, a billing portal and a defined
grace/cancellation policy before promising automatic subscriptions.

## Branding publication and recovery

Brand drafts use optimistic version checks. Publish changes branding/contact
fields, not quote/order snapshots. Restoring a historical revision loads its
branding fields into a draft; it does not silently restore old rates or payment
settings. The original staff icon remains the fallback until customized. Logo
and icon uploads accept sanitized PNG/JPEG only, up to 5 MB.

Run `python manage.py backup` while writes are paused, as before. Backups now
include the root and every company database, uploads, brand assets and company
connections. Restore the entire data folder together to preserve the registry
and per-company data. Deploy exactly one process/container with its persistent
volume: SQLite storage is not a horizontal-scaling architecture.

Next release: dedicated automated platform subscriptions, draft/publish catalog
revisions, granular data visibility, storage/usage quotas and customer billing
self-service. No real customer companies were provisioned by this implementation.
