"""Phase 3 outreach send boundary."""

from app.modules.cold_outreach.mail_sender import send_outreach_email


def test_gmail_send_disabled_by_default() -> None:
    result = send_outreach_email(
        to_email="hm@example.com",
        subject="Coffee chat",
        body="Hello",
        user_id="u1",
    )
    assert result["ok"] is False
    assert result["status"] == "send_disabled"
