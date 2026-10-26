# app/services/mailer.py
"""Transactional email. Brevo's HTTP API is used because free hosts (e.g. Render) block SMTP.

Docs: https://developers.brevo.com/reference/sendtransacemail
"""
import html
import logging

import httpx

from app.config import get_settings
from app.services import oauth

log = logging.getLogger(__name__)
BREVO_SEND = "https://api.brevo.com/v3/smtp/email"


class EmailError(Exception):
    pass


def send(to: str, subject: str, text: str, html_body: str):
    s = get_settings()
    if s.email_delivery == "console":
        # Development only: the code shows up in the server log
        log.warning("EMAIL to %s | %s\n%s", to, subject, text)
        return
    if s.email_delivery != "brevo":
        raise EmailError("Email delivery is not configured")
    try:
        with oauth.http() as client:
            r = client.post(BREVO_SEND, headers={"api-key": s.brevo_api_key, "accept": "application/json"}, json={
                "sender": {"name": s.email_from_name, "email": s.email_from},
                "to": [{"email": to}],
                "subject": subject, "textContent": text, "htmlContent": html_body,
            })
    except httpx.HTTPError as e:
        raise EmailError("Couldn't reach the email service") from e
    if r.status_code not in (200, 201, 202):
        log.error("Brevo rejected an email: %s %s", r.status_code, r.text[:300])
        raise EmailError("The email service rejected the message")


def send_verification_code(to: str, code: str, minutes: int):
    s = get_settings()
    subject = f"{code} is your {s.app_name} code"
    text = (f"Your {s.app_name} verification code is {code}.\n\n"
            f"It expires in {minutes} minutes. If you didn't sign up, you can ignore this email.")
    spaced = " ".join(code)
    body = f"""<div style="font-family:system-ui,sans-serif;max-width:420px;margin:auto;padding:24px;color:#121218">
  <h2 style="margin:0 0 8px;font-size:18px">Confirm your email</h2>
  <p style="margin:0 0 20px;color:#5b5b6b">Enter this code in {html.escape(s.app_name)} to finish signing up.</p>
  <p style="font-size:30px;font-weight:700;letter-spacing:6px;margin:0 0 20px;font-family:monospace">{spaced}</p>
  <p style="margin:0;color:#8a8a99;font-size:13px">It expires in {minutes} minutes. If you didn't sign up, ignore this email.</p>
</div>"""
    send(to, subject, text, body)
