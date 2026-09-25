"""Owner/admin lightweight CRM built from existing customer and lead data."""
from __future__ import annotations

import csv
import io
import json
import hmac
import os
import sqlite3
from datetime import date, datetime, timezone, timedelta

from fastapi import Body, Depends, HTTPException, Request
from fastapi.responses import Response

from .db import audit, now, transaction
from .security import email, text
from .mailer import notify_one

STATUSES = (
    "new_lead",
    "contacted",
    "quote_sent",
    "awaiting_approval",
    "customer",
    "completed",
    "lost",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS crm_contacts (
 id INTEGER PRIMARY KEY,
 name TEXT NOT NULL,
 company TEXT NOT NULL DEFAULT '',
 email TEXT NOT NULL DEFAULT '' COLLATE NOCASE,
 phone TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'new_lead',
 source TEXT NOT NULL DEFAULT '',
 tags TEXT NOT NULL DEFAULT '[]',
 notes TEXT NOT NULL DEFAULT '',
 follow_up_date TEXT,
 auto_reminders INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS crm_contacts_email_unique
 ON crm_contacts(lower(email)) WHERE email <> '';
CREATE INDEX IF NOT EXISTS crm_contacts_status ON crm_contacts(status,follow_up_date);
CREATE TABLE IF NOT EXISTS crm_contact_jobs (
 contact_id INTEGER NOT NULL REFERENCES crm_contacts(id) ON DELETE CASCADE,
 job_id INTEGER NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE CASCADE,
 PRIMARY KEY(contact_id,job_id)
);
CREATE INDEX IF NOT EXISTS crm_contact_jobs_contact ON crm_contact_jobs(contact_id,job_id);
CREATE TABLE IF NOT EXISTS crm_reminders (
 id INTEGER PRIMARY KEY,
 contact_id INTEGER NOT NULL REFERENCES crm_contacts(id) ON DELETE CASCADE,
 job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
 recipient TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('sent','failed')),
 error TEXT NOT NULL DEFAULT '',
 sent_by INTEGER REFERENCES users(id),
 kind TEXT NOT NULL DEFAULT 'manual',
 reminder_key TEXT NOT NULL DEFAULT '',
 automatic INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS crm_reminders_contact ON crm_reminders(contact_id,id);
CREATE INDEX IF NOT EXISTS crm_reminders_key ON crm_reminders(reminder_key,status);
"""


def _upgrade_crm_schema(conn) -> None:
    contact_columns = {row[1] for row in conn.execute("PRAGMA table_info(crm_contacts)")}
    if "auto_reminders" not in contact_columns:
        conn.execute("ALTER TABLE crm_contacts ADD COLUMN auto_reminders INTEGER NOT NULL DEFAULT 1")
    reminder_columns = {row[1] for row in conn.execute("PRAGMA table_info(crm_reminders)")}
    if "kind" not in reminder_columns:
        conn.execute("ALTER TABLE crm_reminders ADD COLUMN kind TEXT NOT NULL DEFAULT 'manual'")
    if "reminder_key" not in reminder_columns:
        conn.execute("ALTER TABLE crm_reminders ADD COLUMN reminder_key TEXT NOT NULL DEFAULT ''")
    if "automatic" not in reminder_columns:
        conn.execute("ALTER TABLE crm_reminders ADD COLUMN automatic INTEGER NOT NULL DEFAULT 0")
    conn.execute("CREATE INDEX IF NOT EXISTS crm_reminders_key ON crm_reminders(reminder_key,status)")


def _optional_email(value) -> str:
    value = str(value or "").strip()
    return email(value) if value else ""


def _tags(value) -> list[str]:
    if isinstance(value, str):
        values = value.split(",")
    elif isinstance(value, list):
        values = value
    else:
        values = []
    clean = []
    for raw in values:
        item = text(str(raw).strip(), "Tag", 40)
        if item and item.lower() not in {x.lower() for x in clean}:
            clean.append(item)
    return clean[:20]


def _follow_up(value):
    value = str(value or "").strip()
    if not value:
        return None
    try:
        date.fromisoformat(value)
    except ValueError:
        raise HTTPException(422, "Follow-up date must be YYYY-MM-DD.")
    return value


def _source_label(value: str) -> str:
    return {
        "public": "Website quote",
        "custom": "Custom request",
        "checkout": "Website order",
        "staff": "Staff entered",
    }.get(str(value or "").lower(), str(value or "").strip())


def sync_jobs(conn) -> None:
    """Backfill/link CRM contacts from jobs without overwriting staff-maintained CRM fields."""
    rows = conn.execute(
        "SELECT id,customer_name,customer_email,phone,source,created_at FROM jobs ORDER BY id DESC"
    ).fetchall()
    for job in rows:
        address = str(job["customer_email"] or "").strip().lower()
        phone = str(job["phone"] or "").strip()
        contact = None
        if address:
            contact = conn.execute(
                "SELECT * FROM crm_contacts WHERE lower(email)=lower(?) LIMIT 1", (address,)
            ).fetchone()
        if not contact and phone:
            contact = conn.execute(
                "SELECT * FROM crm_contacts WHERE email='' AND phone=? LIMIT 1", (phone,)
            ).fetchone()
        if not contact:
            stamp = job["created_at"] or now()
            cursor = conn.execute(
                """INSERT INTO crm_contacts(name,email,phone,status,source,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (
                    job["customer_name"] or "Customer",
                    address,
                    phone,
                    "new_lead",
                    _source_label(job["source"]),
                    stamp,
                    stamp,
                ),
            )
            contact_id = cursor.lastrowid
        else:
            contact_id = contact["id"]
            updates = {}
            if not contact["name"] and job["customer_name"]:
                updates["name"] = job["customer_name"]
            if not contact["email"] and address:
                updates["email"] = address
            if not contact["phone"] and phone:
                updates["phone"] = phone
            if not contact["source"] and job["source"]:
                updates["source"] = _source_label(job["source"])
            if updates:
                updates["updated_at"] = now()
                clause = ",".join(f"{key}=?" for key in updates)
                conn.execute(
                    f"UPDATE crm_contacts SET {clause} WHERE id=?",
                    (*updates.values(), contact_id),
                )
        conn.execute(
            "INSERT OR IGNORE INTO crm_contact_jobs(contact_id,job_id) VALUES(?,?)",
            (contact_id, job["id"]),
        )


def _job_total(job) -> int:
    try:
        quote = json.loads(job["quote_snapshot"])
    except (TypeError, json.JSONDecodeError):
        quote = {}
    base = int(quote.get("subtotal_cents", 0) or 0)
    merchandise = (
        int(job["price_override_cents"])
        if job["price_override_cents"] is not None
        else base + int(job["extra_price_cents"] or 0)
    )
    return merchandise + int(job["shipping_cents"] or 0) + int(job["tax_cents"] or 0)


def _financial_maps(conn):
    manual = {
        row["job_id"]: int(row["paid"] or 0)
        for row in conn.execute(
            """SELECT job_id,COALESCE(SUM(amount_cents),0) AS paid
               FROM payments WHERE voided_at IS NULL GROUP BY job_id"""
        )
    }
    online = {
        row["job_id"]: int(row["paid"] or 0)
        for row in conn.execute(
            """SELECT job_id,COALESCE(SUM(CASE WHEN disputed=0
               THEN amount_cents-refunded_cents ELSE 0 END),0) AS paid
               FROM online_payments GROUP BY job_id"""
        )
    }
    return manual, online


def _contact_dict(row):
    item = dict(row)
    try:
        item["tags"] = json.loads(item.get("tags") or "[]")
    except json.JSONDecodeError:
        item["tags"] = []
    return item


def _snapshot(conn):
    sync_jobs(conn)
    contacts = [_contact_dict(row) for row in conn.execute(
        "SELECT * FROM crm_contacts ORDER BY updated_at DESC,id DESC"
    ).fetchall()]
    by_id = {item["id"]: item for item in contacts}
    for item in contacts:
        item.update(
            order_count=0,
            quoted_cents=0,
            paid_cents=0,
            balance_cents=0,
            last_activity=None,
        )
    manual, online = _financial_maps(conn)
    rows = conn.execute(
        """SELECT cj.contact_id,j.* FROM crm_contact_jobs cj
           JOIN jobs j ON j.id=cj.job_id ORDER BY j.id DESC"""
    ).fetchall()
    for job in rows:
        item = by_id.get(job["contact_id"])
        if not item:
            continue
        total = _job_total(job)
        paid = manual.get(job["id"], 0) + online.get(job["id"], 0)
        item["order_count"] += 1
        item["quoted_cents"] += total
        item["paid_cents"] += paid
        item["balance_cents"] += max(total - paid, 0)
        if not item["last_activity"] or job["created_at"] > item["last_activity"]:
            item["last_activity"] = job["created_at"]
    return contacts


def _open_job(conn, contact_id: int):
    return conn.execute(
        """SELECT j.* FROM crm_contact_jobs cj
           JOIN jobs j ON j.id=cj.job_id
           WHERE cj.contact_id=? AND j.archived=0
             AND EXISTS (SELECT 1 FROM tasks t WHERE t.job_id=j.id AND t.status!='done')
           ORDER BY j.id DESC LIMIT 1""",
        (contact_id,),
    ).fetchone()


def _detail(conn, contact_id: int):
    sync_jobs(conn)
    row = conn.execute("SELECT * FROM crm_contacts WHERE id=?", (contact_id,)).fetchone()
    if not row:
        raise HTTPException(404, "CRM contact not found.")
    contact = _contact_dict(row)
    manual, online = _financial_maps(conn)
    jobs = []
    for job in conn.execute(
        """SELECT j.* FROM crm_contact_jobs cj JOIN jobs j ON j.id=cj.job_id
           WHERE cj.contact_id=? ORDER BY j.id DESC LIMIT 200""",
        (contact_id,),
    ):
        total = _job_total(job)
        paid = manual.get(job["id"], 0) + online.get(job["id"], 0)
        if job["archived"]:
            state = "Archived"
        elif job["accepted_version"] == job["quote_version"]:
            state = "Accepted"
        elif job["published"]:
            state = "Quote sent"
        else:
            state = "Draft"
        jobs.append(
            {
                "id": job["id"],
                "number": job["number"],
                "title": job["title"],
                "created_at": job["created_at"],
                "state": state,
                "total_cents": total,
                "paid_cents": paid,
                "balance_cents": max(total - paid, 0),
            }
        )
    contact["jobs"] = jobs
    contact["order_count"] = len(jobs)
    contact["quoted_cents"] = sum(j["total_cents"] for j in jobs)
    contact["paid_cents"] = sum(j["paid_cents"] for j in jobs)
    contact["balance_cents"] = sum(j["balance_cents"] for j in jobs)
    open_job = _open_job(conn, contact_id)
    contact["reminder_job_id"] = open_job["id"] if open_job else None
    contact["can_remind"] = bool(contact["email"] and open_job and contact["status"] not in {"completed", "lost"})
    contact["reminders"] = [dict(row) for row in conn.execute(
        """SELECT id,job_id,recipient,status,error,created_at
           FROM crm_reminders WHERE contact_id=? ORDER BY id DESC LIMIT 20""",
        (contact_id,),
    )]
    return contact


def install(app, database, require_admin, issue_email_portal):
    with transaction(database, True) as conn:
        conn.executescript(SCHEMA)
        sync_jobs(conn)

    @app.get("/api/admin/crm")
    def crm_list(
        request: Request,
        status: str = "all",
        q: str = "",
        user=Depends(require_admin),
    ):
        if status != "all" and status not in STATUSES:
            raise HTTPException(422, "Invalid CRM status.")
        query = str(q or "").strip().lower()
        with transaction(database, True) as conn:
            contacts = _snapshot(conn)
        if status != "all":
            contacts = [item for item in contacts if item["status"] == status]
        if query:
            contacts = [
                item
                for item in contacts
                if query
                in " ".join(
                    [
                        item.get("name", ""),
                        item.get("company", ""),
                        item.get("email", ""),
                        item.get("phone", ""),
                        item.get("source", ""),
                        " ".join(item.get("tags", [])),
                    ]
                ).lower()
            ]
        today = date.today().isoformat()
        all_contacts = contacts
        totals = {
            "contacts": len(all_contacts),
            "leads": sum(
                item["status"] in {"new_lead", "contacted", "quote_sent", "awaiting_approval"}
                for item in all_contacts
            ),
            "customers": sum(item["status"] in {"customer", "completed"} for item in all_contacts),
            "follow_ups_due": sum(
                bool(item["follow_up_date"] and item["follow_up_date"] <= today)
                and item["status"] != "lost"
                for item in all_contacts
            ),
            "quoted_cents": sum(item["quoted_cents"] for item in all_contacts),
            "paid_cents": sum(item["paid_cents"] for item in all_contacts),
        }
        return {"contacts": all_contacts[:1000], "totals": totals, "statuses": list(STATUSES)}

    @app.get("/api/admin/crm.csv")
    def crm_csv(request: Request, user=Depends(require_admin)):
        with transaction(database, True) as conn:
            contacts = _snapshot(conn)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "Name",
                "Company",
                "Email",
                "Phone",
                "Status",
                "Source",
                "Tags",
                "Follow up",
                "Jobs",
                "Quoted",
                "Paid",
                "Balance",
                "Last activity",
                "Internal notes",
            ]
        )
        for item in contacts:
            writer.writerow(
                [
                    item["name"],
                    item["company"],
                    item["email"],
                    item["phone"],
                    item["status"],
                    item["source"],
                    ", ".join(item["tags"]),
                    item["follow_up_date"] or "",
                    item["order_count"],
                    f'{item["quoted_cents"] / 100:.2f}',
                    f'{item["paid_cents"] / 100:.2f}',
                    f'{item["balance_cents"] / 100:.2f}',
                    item["last_activity"] or "",
                    item["notes"],
                ]
            )
        return Response(
            output.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="tampa-signs-crm.csv"',
                "Cache-Control": "no-store",
            },
        )

    @app.get("/api/admin/crm/{contact_id}")
    def crm_detail(contact_id: int, request: Request, user=Depends(require_admin)):
        with transaction(database, True) as conn:
            return _detail(conn, contact_id)

    @app.post("/api/admin/crm")
    def crm_create(request: Request, payload: dict = Body(...), user=Depends(require_admin)):
        name = text(payload.get("name", ""), "Name", 120, True)
        company = text(payload.get("company", ""), "Company", 160)
        address = _optional_email(payload.get("email", ""))
        phone = text(payload.get("phone", ""), "Phone", 60)
        if not address and not phone:
            raise HTTPException(422, "Enter at least an email address or phone number.")
        status = payload.get("status", "new_lead")
        if status not in STATUSES:
            raise HTTPException(422, "Invalid CRM status.")
        source = text(payload.get("source", ""), "Lead source", 120)
        tags = _tags(payload.get("tags", []))
        notes = text(payload.get("notes", ""), "Internal notes", 10000)
        follow_up = _follow_up(payload.get("follow_up_date"))
        stamp = now()
        try:
            with transaction(database, True) as conn:
                cursor = conn.execute(
                    """INSERT INTO crm_contacts(name,company,email,phone,status,source,tags,notes,
                       follow_up_date,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        name,
                        company,
                        address,
                        phone,
                        status,
                        source,
                        json.dumps(tags),
                        notes,
                        follow_up,
                        stamp,
                        stamp,
                    ),
                )
                contact_id = cursor.lastrowid
                audit(
                    conn,
                    None,
                    f'{user["name"]} (staff #{user["id"]})',
                    "crm.contact_created",
                    {"contact_id": contact_id},
                )
                return _detail(conn, contact_id)
        except sqlite3.IntegrityError:
            raise HTTPException(409, "A CRM contact with that email already exists.")

    @app.patch("/api/admin/crm/{contact_id}")
    def crm_update(
        contact_id: int,
        request: Request,
        payload: dict = Body(...),
        user=Depends(require_admin),
    ):
        with transaction(database, True) as conn:
            current = conn.execute("SELECT * FROM crm_contacts WHERE id=?", (contact_id,)).fetchone()
            if not current:
                raise HTTPException(404, "CRM contact not found.")
            values = {
                "name": text(payload.get("name", current["name"]), "Name", 120, True),
                "company": text(payload.get("company", current["company"]), "Company", 160),
                "email": _optional_email(payload.get("email", current["email"])),
                "phone": text(payload.get("phone", current["phone"]), "Phone", 60),
                "status": payload.get("status", current["status"]),
                "source": text(payload.get("source", current["source"]), "Lead source", 120),
                "tags": json.dumps(_tags(payload.get("tags", json.loads(current["tags"] or "[]")))),
                "notes": text(payload.get("notes", current["notes"]), "Internal notes", 10000),
                "follow_up_date": _follow_up(payload.get("follow_up_date", current["follow_up_date"])),
                "updated_at": now(),
            }
            if values["status"] not in STATUSES:
                raise HTTPException(422, "Invalid CRM status.")
            if not values["email"] and not values["phone"]:
                raise HTTPException(422, "Enter at least an email address or phone number.")
            try:
                conn.execute(
                    """UPDATE crm_contacts SET name=?,company=?,email=?,phone=?,status=?,source=?,
                       tags=?,notes=?,follow_up_date=?,updated_at=? WHERE id=?""",
                    (
                        values["name"],
                        values["company"],
                        values["email"],
                        values["phone"],
                        values["status"],
                        values["source"],
                        values["tags"],
                        values["notes"],
                        values["follow_up_date"],
                        values["updated_at"],
                        contact_id,
                    ),
                )
            except sqlite3.IntegrityError:
                raise HTTPException(409, "A CRM contact with that email already exists.")
            audit(
                conn,
                None,
                f'{user["name"]} (staff #{user["id"]})',
                "crm.contact_updated",
                {"contact_id": contact_id, "status": values["status"]},
            )
            return _detail(conn, contact_id)

    @app.post("/api/admin/crm/{contact_id}/remind")
    def crm_remind(contact_id: int, request: Request, user=Depends(require_admin)):
        with transaction(database, True) as conn:
            sync_jobs(conn)
            contact = conn.execute("SELECT * FROM crm_contacts WHERE id=?", (contact_id,)).fetchone()
            if not contact:
                raise HTTPException(404, "CRM contact not found.")
            if contact["status"] in ("completed", "lost"):
                raise HTTPException(409, "This contact is completed or lost; no project reminder was sent.")
            if not contact["email"]:
                raise HTTPException(422, "Add an email address before sending a project reminder.")
            job = _open_job(conn, contact_id)
            if not job:
                raise HTTPException(409, "There is no open project to remind this customer about.")
            previous = conn.execute(
                "SELECT created_at FROM crm_reminders WHERE contact_id=? AND status='sent' ORDER BY id DESC LIMIT 1",
                (contact_id,),
            ).fetchone()
            if previous:
                try:
                    sent_at = datetime.fromisoformat(previous["created_at"])
                    if sent_at.tzinfo is None:
                        sent_at = sent_at.replace(tzinfo=timezone.utc)
                    if (datetime.now(timezone.utc) - sent_at).total_seconds() < 6 * 3600:
                        raise HTTPException(429, "A project reminder was already sent to this contact within the last 6 hours.")
                except ValueError:
                    pass
            portal_url = issue_email_portal(conn, job["id"], days=14)
            recipient = contact["email"]
            first_name = (contact["name"] or "there").strip().split()[0]
            title = "Don’t forget about your project"
            subject = "Your Tampa Signs project is still open"
            message = (
                f"Hi {first_name},\n\n"
                f"Just a quick reminder that your project “{job['title']}” is still open with Tampa Signs and Stickers. "
                "You can review your quote, proof, payment status, or continue your project anytime using the link below.\n\n"
                "If you have any questions or want to make changes, just reply to this email."
            )
        event_key = f"crm.project_reminder.{contact_id}.{job['id']}.{int(datetime.now(timezone.utc).timestamp())}"
        ok = notify_one(
            database,
            job["id"],
            event_key,
            recipient,
            "customer",
            subject,
            title,
            message,
            portal_url,
            "Continue my project",
        )
        with transaction(database, True) as conn:
            cursor = conn.execute(
                """INSERT INTO crm_reminders(contact_id,job_id,recipient,status,error,sent_by,created_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (contact_id, job["id"], recipient, "sent" if ok else "failed",
                 "" if ok else "Email delivery was not accepted.", user["id"], now()),
            )
            audit(
                conn,
                job["id"],
                f'{user["name"]} (staff #{user["id"]})',
                "crm.project_reminder_sent" if ok else "crm.project_reminder_failed",
                {"contact_id": contact_id, "reminder_id": cursor.lastrowid, "recipient": recipient},
            )
        if not ok:
            raise HTTPException(503, "The reminder could not be sent. Check email delivery settings and try again.")
        return {"ok": True, "message": "Project reminder sent.", "job_id": job["id"]}

