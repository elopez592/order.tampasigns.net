# Deployment and operational handoff

Version 0.2 is a locally tested, single-shop web pilot. The included source is not already deployed and has not received an independent security review. Use a staging environment before real customer traffic.

## Supported deployment shape

One persistent Python application instance with a local SQLite database and local uploads, behind an HTTPS reverse proxy. The container runs as a non-root user. Its `/data` directory must remain on a persistent volume across restarts and upgrades.

Do not deploy this version as stateless serverless functions, multiple replicas with unrelated local disks, or a shared SQLite file on a network filesystem. A multi-instance deployment should first migrate persistence to PostgreSQL and private object storage and add versioned migrations and a worker/notification queue.

The frontend and API share the same origin. For an existing shop website, a dedicated shop/portal subdomain is the simplest integration target for this version. Its current security policy blocks embedding in an iframe; use a regular link rather than assuming an iframe will work.

## Configuration

| Variable | Meaning |
|---|---|
| `APP_ENV=production` | Requires HTTPS public URL; enables Secure cookies and HSTS |
| `PUBLIC_URL` | Exact canonical HTTPS origin used for customer links |
| `DATA_DIR` | Persistent local directory containing database and uploads |
| `ALLOWED_HOSTS` | Comma-separated actual hostnames; no wildcard in production |
| `DEMO_SEED=0` | Do not create synthetic customer jobs or employee account |
| `ADMIN_EMAIL` | Owner address for first database initialization |
| `ADMIN_PASSWORD` | Optional initial password only; omit for a random one |
| `HOST` / `PORT` | Listening interface and port; Docker uses 0.0.0.0 and 8000 |
| `TRUST_PROXY` | Enable only behind a known proxy |
| `FORWARDED_ALLOW_IPS` | Only actual trusted proxy IPs, never blindly `*` |
| `STRIPE_SECRET_KEY` | Optional server-only Stripe account credential |
| `STRIPE_WEBHOOK_SECRET` | Signing secret for the exact Stripe event destination |

The app reads process environment variables. `.env.example` is not automatically loaded. The local `compose.yaml` hardcodes demo settings. The separate `compose.production.yaml` explicitly loads `.env.production`; do not combine these two Compose files.

Include the health-check loopback host in allowed hosts when using the Docker health check. Set `PUBLIC_URL` to include a custom local port when testing on a port other than 8000. Staff passwords are not changed by modifying initial environment variables after the account already exists.

Use TLS termination with an appropriately configured reverse proxy, body/time/rate limits and access controls. Keep the service port private and route only the public origin through the proxy. Correct client IP forwarding is important because application rate limits use client IPs. Otherwise all customers may share the proxy's throttle bucket.

## Launch checklist

- Start with a separate clean production data directory; never promote the sample orders/payments as genuine records.
- Set shop identity and verified contact information. Replace every demonstration product cost and price. Review tax/delivery handling and below-target overrides on representative jobs.
- Verify HTTPS, hostname checks, Secure/HttpOnly/SameSite cookies, CSRF protection and negative authorization tests on the deployed host.
- Review pinned dependencies against current security advisories and retest updates. The pins describe the tested build, not a promise they are the latest or vulnerability-free.
- Add file malware scanning/quarantine before broadly accepting untrusted PDFs. Current PDF checks are extension/header and download-only behavior, not content sanitization. Define storage quotas and retention.
- Establish encrypted off-server backups and perform a restore drill. Protect both the database and private artwork. The application's directories/files restrict local permissions where the operating system permits.
- Restrict staff roles, protect credentials and bootstrap logs, remove unused employees, and decide whether public launch requires MFA and stronger customer identity verification.
- Configure privacy/terms/approval wording, authorized approvers, retention/deletion processes and customer support appropriate to the business.
- Define who monitors job messages and manually verifies QuickBooks payments. Add outbound email/SMS only with an authenticated provider and delivery/error handling.
- Perform a real-device/browser acceptance test and controlled payment-link test using an invoice you are authorized to test. Do not mark a real job paid based on demo UI actions.
- Add uptime/error/storage monitoring. No alerts or remote monitoring service is configured in this package.

## Backups and restore

For a local install, pause application writes before creating a consistent database-and-files backup:

```sh
python manage.py backup --output backups
```

The command creates a SQLite backup snapshot and includes private files in one ZIP. It does not encrypt the ZIP. Encrypt it using your chosen backup system, store it off-server with restricted access, and verify restore regularly. The backup contains customer information, password hashes and potentially live session/link hashes.

For Docker, stop the app and run the management command in a one-off container against the same named data volume, writing to a separately mounted backup destination with suitable permissions. Review the command with the deployer; do not delete or recreate the volume as a backup method.

To restore: stop the app; back up the current data first; extract a trusted matching backup into an empty data directory; restore `signshop.sqlite3` and the `uploads` directory together; ensure application ownership; start the same compatible application version; verify jobs, proof downloads and record counts before resuming writes. Do not mix a restored database with old WAL/SHM sidecars or unrelated upload directories. Backups should be treated as trusted administrative input, not arbitrary customer files.

## Password recovery

For a local account recovery, use an interactive terminal with the correct `DATA_DIR`:

```sh
python manage.py reset-password --email owner@your-domain.example
```

This prompts for a new password and invalidates that staff account's sessions. There is no public email-based password reset endpoint. Normal password changes are available after staff sign-in.

## Version and migration limits

Version 0.2 supports version 1 databases and adds version 2 checkout tables at startup. Existing jobs, approvals and payments are preserved; defaults for new checkout/eligibility settings are merged. This is one explicit additive upgrade, not a general migration system. Back up database plus uploads first, test against a copy, then deploy. Do not copy a demo database over an existing real installation or roll old code back against changed data without a tested restore plan. Preserve the Docker volume/project name during upgrades.

Official FastAPI container deployment reference:

`https://fastapi.tiangolo.com/deployment/docker/`


## Included internet-server recipe

This is for a Linux server you control, not the owner's workstation. The domain, server, billing authorization and secrets are not provisioned by this archive.

1. Provision a host with Docker Engine and Compose, storage, firewall and backups. Review current patches and dependencies.
2. Point the intended domain/subdomain's DNS A/AAAA records at that host. Ensure public ports 80 and 443 reach it; do not publicly expose port 8000.
3. Copy the project and `.env.production.example` to `.env.production`. Set `SITE_HOST` to a hostname only, e.g. `orders.your-domain.example` (no scheme/path). Set the real initial owner email. Keep secret credentials out of source control. Restrict the file to the deploying account.
4. Inspect `compose.production.yaml`: one app instance, persistent data volume, Caddy HTTPS, and a private Docker network. The static subnet `172.29.40.0/24` must not conflict with existing networks. If changing it, update both service IPs and the app's trusted-proxy IP together.
5. Run only this explicit production recipe:

```sh
cp .env.production.example .env.production
# EDIT .env.production before proceeding.
chmod 600 .env.production
docker compose --env-file .env.production -f compose.production.yaml config --quiet
docker compose --env-file .env.production -f compose.production.yaml up -d --build
docker compose --env-file .env.production -f compose.production.yaml logs -f signshop
```

Avoid printing a fully interpolated Compose configuration into a public terminal/log because it can expose environment secrets. Initial credentials may also appear in startup logs; protect them and change the password after login.

Caddy's automatic HTTPS requires the domain to resolve to this server, externally reachable 80/443, and writable/persistent certificate storage. Verify HTTPS and secure cookies on the real host. The included Caddy image tag should be pinned to the operator's reviewed version/digest before production use.

The app's `DEMO_SEED=0` means no synthetic customer jobs are added to a fresh database. Seed product examples still exist and remain explicitly demonstration pricing until reviewed. Use a fresh production volume, not the local preview volume. Set a deliberate Compose project name and preserve it across upgrades so Docker uses the correct data volume.

## Managed hosting alternative

A Docker web service with a persistent disk, for example Render, is an alternative to the Caddy recipe. Deploy from a private source repository, set the real HTTPS `PUBLIC_URL`/allowed hosts, attach storage at `/data`, set `DEMO_SEED=0`, and use exactly one application instance. Ensure the non-root container UID 10001 can write the disk mount. Confirm the host's current trusted-proxy configuration before enabling forwarded headers; do not blindly trust all callers.

Render's persistent disks require an eligible paid service; a default ephemeral filesystem is not sufficient for jobs or artwork. This archive does not create that service, connect a repository or incur hosting fees. A provider's snapshot feature is not a substitute for a tested SQLite-plus-artwork backup and restore procedure.

Official hosting references checked September 17, 2026:

- https://render.com/docs/docker
- https://render.com/docs/disks
- https://caddyserver.com/docs/automatic-https
- https://caddyserver.com/docs/caddyfile/directives/reverse_proxy
