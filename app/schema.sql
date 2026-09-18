PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);
INSERT OR IGNORE INTO schema_version VALUES (1);
CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL COLLATE NOCASE UNIQUE,
 password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','employee')),
 active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY, csrf TEXT NOT NULL, user_id INTEGER REFERENCES users(id),
 portal_job_id INTEGER, portal_generation TEXT, expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS rate_limits (bucket TEXT PRIMARY KEY, count INTEGER NOT NULL, resets_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS workflows (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, steps TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS products (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
 active INTEGER NOT NULL DEFAULT 1, public INTEGER NOT NULL DEFAULT 1,
 workflow_id INTEGER NOT NULL REFERENCES workflows(id), config TEXT NOT NULL,
 version INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
 id INTEGER PRIMARY KEY, number TEXT UNIQUE, title TEXT NOT NULL,
 customer_name TEXT NOT NULL, customer_email TEXT NOT NULL, phone TEXT NOT NULL DEFAULT '',
 notes TEXT NOT NULL DEFAULT '', source TEXT NOT NULL, created_at TEXT NOT NULL,
 due_date TEXT, priority TEXT NOT NULL DEFAULT 'normal', assignee_id INTEGER REFERENCES users(id),
 quote_snapshot TEXT NOT NULL, quote_version INTEGER NOT NULL DEFAULT 1,
 published INTEGER NOT NULL DEFAULT 0, accepted_version INTEGER, accepted_name TEXT, accepted_at TEXT,
 extra_price_cents INTEGER NOT NULL DEFAULT 0, extra_cost_cents INTEGER NOT NULL DEFAULT 0,
 adjustment_note TEXT NOT NULL DEFAULT '', price_override_cents INTEGER,
 shipping_cents INTEGER NOT NULL DEFAULT 0, tax_cents INTEGER NOT NULL DEFAULT 0,
 charges_verified INTEGER NOT NULL DEFAULT 0, deposit_percent TEXT NOT NULL DEFAULT '50',
 workflow_id INTEGER NOT NULL REFERENCES workflows(id), archived INTEGER NOT NULL DEFAULT 0,
 portal_hash TEXT, portal_expires REAL,
 payment_url TEXT, payment_kind TEXT NOT NULL DEFAULT 'invoice', invoice_reference TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS tasks (
 id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL REFERENCES jobs(id), position INTEGER NOT NULL,
 title TEXT NOT NULL, department TEXT NOT NULL, gate TEXT NOT NULL,
 dependencies TEXT NOT NULL DEFAULT '[]', status TEXT NOT NULL DEFAULT 'todo',
 assignee_id INTEGER REFERENCES users(id), note TEXT NOT NULL DEFAULT '',
 started_at TEXT, completed_at TEXT, UNIQUE(job_id,position)
);
CREATE TABLE IF NOT EXISTS time_entries (
 id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL REFERENCES tasks(id),
 user_id INTEGER NOT NULL REFERENCES users(id), started_at TEXT NOT NULL, stopped_at TEXT
);
CREATE TABLE IF NOT EXISTS assets (
 id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL REFERENCES jobs(id),
 filename TEXT NOT NULL, stored_name TEXT NOT NULL UNIQUE, mime TEXT NOT NULL,
 sha256 TEXT NOT NULL, size INTEGER NOT NULL, kind TEXT NOT NULL, created_at TEXT NOT NULL,
 uploaded_by TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS proofs (
 id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL REFERENCES jobs(id),
 version INTEGER NOT NULL, asset_id INTEGER NOT NULL REFERENCES assets(id),
 label TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'pending',
 specs TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(job_id,version)
);
CREATE TABLE IF NOT EXISTS proof_decisions (
 id INTEGER PRIMARY KEY, proof_id INTEGER NOT NULL REFERENCES proofs(id),
 action TEXT NOT NULL, signer_name TEXT NOT NULL, comment TEXT NOT NULL,
 statement TEXT NOT NULL, quote_version INTEGER NOT NULL, file_hash TEXT NOT NULL,
 created_at TEXT NOT NULL, method TEXT NOT NULL DEFAULT 'private_job_link'
);
CREATE TABLE IF NOT EXISTS payments (
 id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL REFERENCES jobs(id),
 amount_cents INTEGER NOT NULL CHECK(amount_cents > 0), reference TEXT NOT NULL,
 note TEXT NOT NULL DEFAULT '', verified_by INTEGER NOT NULL REFERENCES users(id),
 created_at TEXT NOT NULL, voided_at TEXT, void_reason TEXT,
 UNIQUE(job_id,reference)
);
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY, job_id INTEGER REFERENCES jobs(id),
 actor TEXT NOT NULL, action TEXT NOT NULL, details TEXT NOT NULL,
 public INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS tasks_job ON tasks(job_id);
CREATE INDEX IF NOT EXISTS events_job ON events(job_id,id);
CREATE INDEX IF NOT EXISTS proofs_job ON proofs(job_id,version);
CREATE INDEX IF NOT EXISTS session_expiry ON sessions(expires_at);

-- Version 2: additive web checkout tables. Existing jobs and files are retained.
CREATE TABLE IF NOT EXISTS checkout_orders (
 id TEXT PRIMARY KEY, job_id INTEGER NOT NULL UNIQUE REFERENCES jobs(id),
 request_id TEXT NOT NULL UNIQUE, request_hash TEXT NOT NULL, owner_session TEXT NOT NULL,
 fulfillment TEXT NOT NULL CHECK(fulfillment IN ('pickup','shipping')),
 policy TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS checkout_sessions (
 id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES checkout_orders(id),
 stripe_id TEXT UNIQUE, url TEXT, status TEXT NOT NULL DEFAULT 'creating',
 quote_version INTEGER NOT NULL, merchandise_cents INTEGER NOT NULL,
 shipping_cents INTEGER NOT NULL DEFAULT 0, request_body TEXT,
 expires_at REAL NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS online_payments (
 id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL REFERENCES jobs(id),
 session_id TEXT NOT NULL UNIQUE, payment_intent TEXT NOT NULL UNIQUE,
 amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
 refunded_cents INTEGER NOT NULL DEFAULT 0, disputed INTEGER NOT NULL DEFAULT 0,
 event_id TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS webhook_events (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, received_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS payment_adjustments (
 payment_intent TEXT PRIMARY KEY, refunded_cents INTEGER NOT NULL DEFAULT 0,
 disputed INTEGER NOT NULL DEFAULT 0, dispute_updated INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS checkout_order_sessions ON checkout_sessions(order_id);
CREATE INDEX IF NOT EXISTS online_payments_job ON online_payments(job_id);


-- Version 3: transactional email delivery log and non-rotating email portal links.
CREATE TABLE IF NOT EXISTS email_notifications (
 id INTEGER PRIMARY KEY,
 job_id INTEGER NOT NULL REFERENCES jobs(id),
 event_key TEXT NOT NULL,
 recipient TEXT NOT NULL,
 audience TEXT NOT NULL CHECK(audience IN ('customer','staff')),
 status TEXT NOT NULL CHECK(status IN ('sent','failed')),
 error TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(job_id,event_key,recipient)
);
CREATE TABLE IF NOT EXISTS portal_links (
 token_hash TEXT PRIMARY KEY,
 job_id INTEGER NOT NULL REFERENCES jobs(id),
 expires_at REAL NOT NULL,
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS email_notifications_job ON email_notifications(job_id,id);
CREATE INDEX IF NOT EXISTS portal_links_expiry ON portal_links(expires_at);


-- Version 4: reusable wholesale client pricing profiles.
CREATE TABLE IF NOT EXISTS wholesale_clients (
 id INTEGER PRIMARY KEY,
 name TEXT NOT NULL,
 email TEXT NOT NULL COLLATE NOCASE UNIQUE,
 code_hash TEXT NOT NULL,
 discount_percent TEXT NOT NULL DEFAULT '0',
 active INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS wholesale_product_discounts (
 client_id INTEGER NOT NULL REFERENCES wholesale_clients(id) ON DELETE CASCADE,
 product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
 discount_percent TEXT NOT NULL,
 PRIMARY KEY(client_id, product_id)
);
CREATE TABLE IF NOT EXISTS wholesale_sessions (
 token_hash TEXT PRIMARY KEY,
 client_id INTEGER NOT NULL REFERENCES wholesale_clients(id) ON DELETE CASCADE,
 expires_at REAL NOT NULL,
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS wholesale_sessions_expiry ON wholesale_sessions(expires_at);
