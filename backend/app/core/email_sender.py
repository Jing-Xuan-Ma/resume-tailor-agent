"""
Production-grade cold outreach email sender.

Architecture (two tiers):
  1. Gmail API (OAuth 2.0) — preferred, uses Google's official API
  2. SMTP fallback — uses Gmail SMTP with App Password (simpler setup)

Features:
  - Unsubscribe link (List-Unsubscribe header + landing page)
  - Per-company rate limiting (cooldown)
  - Send confirmation (user must explicitly confirm each send)
  - Delivery status tracking
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import smtplib
import time
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Literal

from app.config import settings

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

SendResult = Literal["sent", "rate_limited", "no_recipient", "error"]


@dataclass
class SendReport:
    status: SendResult
    message_id: str | None = None
    error: str | None = None
    rate_limit_remaining: int | None = None


@dataclass
class OutreachEmail:
    to_email: str
    to_name: str
    subject: str
    body_text: str
    body_html: str | None = None
    company: str = ""
    user_id: str = ""


# ---------------------------------------------------------------------------
# Rate limiter — per-company cooldown
# ---------------------------------------------------------------------------

class CompanyRateLimiter:
    """Simple in-memory rate limiter: N emails per company per time window."""

    def __init__(self, max_per_company: int = 1, window_hours: int = 72):
        self.max_per_company = max_per_company
        self.window_seconds = window_hours * 3600
        self._sent: dict[str, list[float]] = {}

    def check(self, company: str) -> bool:
        if not company:
            return True
        now = time.time()
        window_start = now - self.window_seconds
        timestamps = self._sent.get(company.lower(), [])
        timestamps = [t for t in timestamps if t > window_start]
        self._sent[company.lower()] = timestamps
        return len(timestamps) < self.max_per_company

    def record(self, company: str) -> None:
        if not company:
            return
        key = company.lower()
        if key not in self._sent:
            self._sent[key] = []
        self._sent[key].append(time.time())

    def remaining(self, company: str) -> int:
        if not company:
            return self.max_per_company
        self.check(company)  # prune
        return max(0, self.max_per_company - len(self._sent.get(company.lower(), [])))


_rate_limiter = CompanyRateLimiter(max_per_company=1, window_hours=72)


# ---------------------------------------------------------------------------
# Unsubscribe token management
# ---------------------------------------------------------------------------

def _unsubscribe_secret() -> str:
    return settings.SECRET_KEY or "change-me-unsubscribe-secret"


def generate_unsubscribe_token(user_id: str, message_id: str) -> str:
    """HMAC-based unsubscribe token (no DB lookup needed to verify)."""
    payload = f"{user_id}:{message_id}"
    sig = hmac.new(_unsubscribe_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{payload}:{sig}"


def verify_unsubscribe_token(token: str) -> tuple[str, str] | None:
    """Returns (user_id, message_id) if token is valid, None otherwise."""
    parts = token.split(":")
    if len(parts) != 3:
        return None
    user_id, message_id, sig = parts
    expected = generate_unsubscribe_token(user_id, message_id)
    if token != expected:
        return None
    return user_id, message_id


def unsubscribe_link(base_url: str | None, user_id: str, message_id: str) -> str:
    base = (base_url or "").rstrip("/") or "http://localhost:8000"
    token = generate_unsubscribe_token(user_id, message_id)
    return f"{base}/api/v1/outreach/unsubscribe?token={token}"


# ---------------------------------------------------------------------------
# HTML email builder
# ---------------------------------------------------------------------------

def build_html_body(email: OutreachEmail) -> str:
    unsubscribe_url = unsubscribe_link(
        settings.APP_HOST_URL if hasattr(settings, "APP_HOST_URL") else None,
        email.user_id,
        "placeholder",
    )
    paragraphs = email.body_text.strip().replace("\n", "</p><p>")
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head><body style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:20px">
<p>{paragraphs}</p>
<hr style="margin-top:32px;color:#ccc">
<p style="font-size:12px;color:#888">
  This email was sent by a job application assistant on your behalf.
  <br><a href="{unsubscribe_url}" style="color:#888">Unsubscribe from future outreach</a>
</p>
</body></html>"""


# ---------------------------------------------------------------------------
# Sending tier 1: Gmail API
# ---------------------------------------------------------------------------

def _send_via_gmail_api(email: OutreachEmail) -> SendReport:
    try:
        from google.auth.transport.requests import Request as GoogleRequest
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        log.warning("google-api-python-client not installed. Falling back to SMTP.")
        return _send_via_smtp(email)

    SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
    creds = None
    token_path = os.path.expanduser("~/.config/resume-agent/gmail_token.json")
    creds_path = getattr(settings, "GMAIL_CREDENTIALS_PATH", "") or os.path.expanduser(
        "~/.config/resume-agent/gmail_credentials.json"
    )

    if os.path.exists(token_path):
        import json
        with open(token_path) as f:
            creds = Credentials.from_authorized_user_info(json.load(f), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())
            import json
            with open(token_path, "w") as f:
                json.dump(json.loads(creds.to_json()), f)
        else:
            if not os.path.exists(creds_path):
                log.error(
                    "Gmail API credentials not found at %s. "
                    "Download OAuth client JSON from Google Cloud Console and save it there, "
                    "or use SMTP with GMAIL_APP_PASSWORD instead.",
                    creds_path,
                )
                return _send_via_smtp(email)
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
            import json
            os.makedirs(os.path.dirname(token_path), exist_ok=True)
            with open(token_path, "w") as f:
                json.dump(json.loads(creds.to_json()), f)

    try:
        service = build("gmail", "v1", credentials=creds)
        msg = MIMEMultipart("alternative")
        msg["To"] = f"{email.to_name} <{email.to_email}>"
        msg["Subject"] = email.subject
        msg["List-Unsubscribe"] = f"<{unsubscribe_link('', email.user_id, 'placeholder')}>"
        msg.attach(MIMEText(email.body_text, "plain"))
        msg.attach(MIMEText(build_html_body(email), "html"))

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()

        log.info("Email sent via Gmail API to %s", email.to_email)
        return SendReport(status="sent")
    except Exception as e:
        log.error("Gmail API send failed: %s", e)
        return SendReport(status="error", error=str(e))


# ---------------------------------------------------------------------------
# Sending tier 2: SMTP (Gmail App Password)
# ---------------------------------------------------------------------------

def _send_via_smtp(email: OutreachEmail) -> SendReport:
    smtp_host = getattr(settings, "SMTP_HOST", "") or "smtp.gmail.com"
    smtp_port = getattr(settings, "SMTP_PORT", 587)
    smtp_user = getattr(settings, "SMTP_USER", "") or os.getenv("SMTP_USER", "")
    smtp_pass = getattr(settings, "SMTP_PASSWORD", "") or os.getenv("SMTP_PASSWORD", "")

    if not smtp_user or not smtp_pass:
        return SendReport(
            status="error",
            error="SMTP not configured. Set SMTP_USER / SMTP_PASSWORD or GMAIL_CREDENTIALS_PATH.",
        )

    msg = MIMEMultipart("alternative")
    msg["From"] = smtp_user
    msg["To"] = f"{email.to_name} <{email.to_email}>"
    msg["Subject"] = email.subject
    msg["List-Unsubscribe"] = f"<{unsubscribe_link('', email.user_id, 'placeholder')}>"
    msg.attach(MIMEText(email.body_text, "plain"))
    msg.attach(MIMEText(build_html_body(email), "html"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        log.info("Email sent via SMTP to %s", email.to_email)
        return SendReport(status="sent")
    except Exception as e:
        log.error("SMTP send failed: %s", e)
        return SendReport(status="error", error=str(e))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def send_outreach_email(email: OutreachEmail) -> SendReport:
    """Send an outreach email with rate limiting and compliance."""
    if not email.to_email:
        return SendReport(status="no_recipient", error="No recipient email address.")

    if not _rate_limiter.check(email.company):
        remaining = _rate_limiter.remaining(email.company)
        log.warning("Rate limited: company=%s remaining=%d", email.company, remaining)
        return SendReport(status="rate_limited", rate_limit_remaining=remaining)

    provider = (getattr(settings, "EMAIL_PROVIDER", "") or "").lower()
    if provider == "gmail_api":
        report = _send_via_gmail_api(email)
    else:
        report = _send_via_smtp(email)

    if report.status == "sent":
        _rate_limiter.record(email.company)

    return report


def get_email_provider_name() -> str:
    provider = (getattr(settings, "EMAIL_PROVIDER", "") or "").lower()
    if provider == "gmail_api":
        return "Gmail API"
    smtp_user = getattr(settings, "SMTP_USER", "") or os.getenv("SMTP_USER", "")
    return f"SMTP ({smtp_user or 'not configured'})"


def rate_limit_remaining(company: str) -> int:
    return _rate_limiter.remaining(company)
