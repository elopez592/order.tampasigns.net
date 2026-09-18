from __future__ import annotations
import html
import json
import logging
import os
import httpx

from .db import now, transaction

log = logging.getLogger('tampasigns.email')


def enabled() -> bool:
    return bool(os.getenv("RESEND_API_KEY") and os.getenv("EMAIL_FROM"))


def public_status() -> dict:
    return {"enabled": enabled(), "provider": "resend" if enabled() else None}


def _send(to_address: str, subject: str, html_body: str, text_body: str) -> tuple[bool, str]:
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    from_address = os.getenv("EMAIL_FROM", "").strip()
    if not api_key or not from_address:
        return False, "Email delivery is not configured."
    payload = {
        "from": from_address,
        "to": [to_address],
        "subject": subject,
        "html": html_body,
        "text": text_body,
    }
    reply_to = os.getenv("EMAIL_REPLY_TO", "").strip()
    if reply_to:
        payload["reply_to"] = reply_to
    try:
        with httpx.Client(timeout=12.0) as client:
            response = client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
        if 200 <= response.status_code < 300:
            log.info("Transactional email accepted recipient=%s subject=%s", to_address, subject)
            return True, ""
        error = f"Email provider returned HTTP {response.status_code}: {response.text[:180]}"
        log.error("Transactional email failed recipient=%s subject=%s error=%s", to_address, subject, error)
        return False, error
    except (httpx.HTTPError, OSError) as exc:
        error = f"Email provider could not be reached: {type(exc).__name__}"
        log.error("Transactional email failed recipient=%s subject=%s error=%s", to_address, subject, error)
        return False, error


def _brand_html(title: str, message: str, action_url: str | None = None, action_label: str = "View order") -> str:
    safe_title = html.escape(title)
    safe_message = html.escape(message).replace("\n", "<br>")
    button = ""
    if action_url:
        button = f'<p style="margin:28px 0"><a href="{html.escape(action_url, quote=True)}" style="display:inline-block;background:#079a99;color:#fff;text-decoration:none;font-weight:700;padding:12px 18px;border-radius:8px">{html.escape(action_label)}</a></p>'
    return f"""<!doctype html><html><body style="margin:0;background:#f5f8f7;font-family:Arial,sans-serif;color:#101516">
    <div style="max-width:620px;margin:0 auto;padding:30px 18px">
      <div style="background:#0b0f10;padding:20px 24px;border-radius:12px 12px 0 0;color:#fff;font-size:18px;font-weight:800">Tampa Signs and Stickers</div>
      <div style="background:#fff;border:1px solid #dce6e4;border-top:4px solid #079a99;padding:28px 24px;border-radius:0 0 12px 12px">
        <h1 style="font-size:24px;margin:0 0 14px">{safe_title}</h1>
        <p style="font-size:15px;line-height:1.6;color:#53646a">{safe_message}</p>
        {button}
        <p style="margin-top:28px;font-size:12px;color:#7b8a8f">Tampa Signs and Stickers · (813) 749-4500</p>
      </div>
    </div></body></html>"""


def _record(database, job_id: int, event_key: str, recipient: str, audience: str, status: str, error: str = ""):
    with transaction(database, True) as conn:
        conn.execute(
            """INSERT INTO email_notifications(job_id,event_key,recipient,audience,status,error,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(job_id,event_key,recipient) DO UPDATE SET
               status=excluded.status,error=excluded.error,updated_at=excluded.updated_at""",
            (job_id, event_key, recipient, audience, status, error[:300], now(), now()),
        )


def notify_one(database, job_id: int, event_key: str, recipient: str, audience: str,
               subject: str, title: str, message: str, action_url: str | None = None,
               action_label: str = "View order", force: bool = False) -> bool:
    if not enabled() or not recipient:
        return False
    with transaction(database) as conn:
        prior = conn.execute(
            "SELECT status FROM email_notifications WHERE job_id=? AND event_key=? AND recipient=?",
            (job_id, event_key, recipient),
        ).fetchone()
        if prior and prior["status"] == "sent" and not force:
            return True
    ok, error = _send(recipient, subject, _brand_html(title, message, action_url, action_label),
                      f"{title}\n\n{message}" + (f"\n\n{action_url}" if action_url else ""))
    _record(database, job_id, event_key, recipient, audience, "sent" if ok else "failed", error)
    return ok


def staff_addresses(database) -> list[str]:
    with transaction(database) as conn:
        return [row["email"] for row in conn.execute("SELECT email FROM users WHERE active=1 ORDER BY role DESC,id")]


def notify_staff(database, job_id: int, event_key: str, subject: str, title: str, message: str, public_url: str):
    for address in staff_addresses(database):
        notify_one(database, job_id, event_key, address, "staff", subject, title, message,
                   public_url.rstrip("/") + f"/staff#job/{job_id}", "Open job")


def notify_customer(database, job_id: int, event_key: str, subject: str, title: str,
                    message: str, portal_url: str | None = None, force: bool = False):
    with transaction(database) as conn:
        job = conn.execute("SELECT customer_email FROM jobs WHERE id=?", (job_id,)).fetchone()
    if job:
        return notify_one(database, job_id, event_key, job["customer_email"], "customer",
                          subject, title, message, portal_url, "View order", force=force)
    return False
