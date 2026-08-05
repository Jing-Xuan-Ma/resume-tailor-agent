"""Optional Gmail/SMTP sender — disabled by default (Phase 3+)."""

from __future__ import annotations

from typing import Any

from app.config import settings


def send_outreach_email(
    *,
    to_email: str,
    subject: str,
    body: str,
    user_id: str,
) -> dict[str, Any]:
    """Send only when ENABLE_GMAIL_SEND is true. Otherwise refuse."""
    if not bool(getattr(settings, "ENABLE_GMAIL_SEND", False)):
        return {
            "ok": False,
            "status": "send_disabled",
            "message": (
                "Gmail/SMTP send is frozen. Use mailto / copy + Mark sent, "
                "or set ENABLE_GMAIL_SEND=true with OAuth credentials."
            ),
            "to": to_email,
            "user_id": user_id,
        }
    # Placeholder for future OAuth Gmail / SMTP — never silent-send without audit.
    return {
        "ok": False,
        "status": "not_configured",
        "message": "ENABLE_GMAIL_SEND is on but Gmail OAuth / SMTP is not configured yet.",
        "subject": subject,
        "body_chars": len(body or ""),
    }
