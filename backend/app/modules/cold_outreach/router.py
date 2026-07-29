from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app import db
from app.config import settings
from app.core.email_sender import (
    OutreachEmail,
    generate_unsubscribe_token,
    get_email_provider_name,
    rate_limit_remaining,
    send_outreach_email,
    verify_unsubscribe_token,
)
from app.core.rate_limit import rate_limiter
from app.modules.cold_outreach.schemas import (
    OutreachDraftRequest,
    OutreachListResponse,
    OutreachMarkSentRequest,
    OutreachMessageResponse,
    OutreachSendRequest,
    OutreachSendResponse,
    UnsubscribeResponse,
)
from app.modules.safety.audit_log import audit


router = APIRouter()


def _resume_signal(user_id: str) -> str:
    resume = db.get_latest_resume(user_id)
    if not resume:
        return "your background"
    parsed = resume.get("parsed") or {}
    skills = parsed.get("skills") or []
    if isinstance(skills, list) and skills:
        return ", ".join(str(skill) for skill in skills[:4])
    raw = str(resume.get("raw_text") or "").strip().splitlines()
    return raw[0] if raw else "your background"


def _compose_message(request: OutreachDraftRequest, job: dict | None, resume_signal: str) -> tuple[str, str, dict]:
    company = request.company or (job or {}).get("company") or "your team"
    role = (job or {}).get("title") or "the open role"
    contact = request.contact_name or "there"
    subject = f"Interest in {role} at {company}" if company != "your team" else f"Interest in {role}"
    if request.tone == "formal":
        greeting = f"Dear {contact},"
        close = "Sincerely,"
    else:
        greeting = f"Hi {contact},"
        close = "Best,"
    body = (
        f"{greeting}\n\n"
        f"I noticed {role} at {company} and wanted to reach out directly. "
        f"My experience includes {resume_signal}, and I am especially interested in contributing to the problems described in the role.\n\n"
        "If it is useful, I would appreciate any guidance on the team, the hiring process, or whether my background could be a fit. "
        "I am happy to send a tailored resume or a short summary of relevant work.\n\n"
        f"{close}\n"
    )
    metadata = {
        "safety": "draft_only_user_sends",
        "tone": request.tone,
        "job_title": role,
        "source_url": (job or {}).get("source_url"),
    }
    return subject, body, metadata


@router.post("/draft", response_model=OutreachMessageResponse)
async def draft_outreach(request: OutreachDraftRequest):
    rate_limiter.check(str(request.user_id), "cold_outreach", settings.MAX_DAILY_EMAILS)
    job = None
    if request.job_id:
        job = db.get_job(str(request.job_id), user_id=str(request.user_id))
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
    company = request.company or (job or {}).get("company") or ""
    subject, body, metadata = _compose_message(request, job, _resume_signal(str(request.user_id)))

    # Pre-generate message_id so we can embed it in the unsubscribe token
    from uuid import uuid4
    message_id = str(uuid4())
    unsubscribe_token = generate_unsubscribe_token(str(request.user_id), message_id)

    db.save_outreach_message(
        message_id=message_id,
        user_id=str(request.user_id),
        job_id=str(request.job_id) if request.job_id else None,
        contact_name=request.contact_name,
        contact_role=request.contact_role,
        company=company,
        channel=request.channel,
        subject=subject,
        body=body,
        metadata=metadata,
        unsubscribe_token=unsubscribe_token,
    )

    message = db.get_outreach_message(message_id, user_id=str(request.user_id))
    audit(str(request.user_id), "outreach_draft_created", {"message_id": message_id}, application_run_id=None)
    return message


@router.post("/{message_id}/send", response_model=OutreachSendResponse)
async def send_outreach(message_id: str, request: OutreachSendRequest):
    """Confirm and send an outreach email."""
    if not request.confirm_send:
        raise HTTPException(status_code=400, detail="Set confirm_send=true to send this outreach email.")

    message = db.get_outreach_message(message_id, user_id=str(request.user_id))
    if not message:
        raise HTTPException(status_code=404, detail="Outreach message not found")
    if message["status"] == "sent":
        return OutreachSendResponse(
            id=message_id,
            status="already_sent",
            delivery_status=message.get("delivery_status"),
            sent_at=message.get("sent_at"),
            provider=get_email_provider_name(),
        )

    rate_limiter.check(str(request.user_id), "cold_outreach", settings.MAX_DAILY_EMAILS)

    company = message.get("company") or ""
    remaining = rate_limit_remaining(company)

    # Build recipient email
    contact_name = message.get("contact_name") or "there"
    to_email = request.to_email or ""
    if not to_email:
        raise HTTPException(status_code=400, detail="No recipient email. Provide to_email or set it on the draft.")

    email = OutreachEmail(
        to_email=to_email,
        to_name=contact_name,
        subject=message["subject"],
        body_text=message["body"],
        company=company,
        user_id=str(request.user_id),
    )

    report = send_outreach_email(email)
    if report.status == "error":
        db.update_outreach_send_status(message_id, str(request.user_id), "failed", report.error)
        raise HTTPException(status_code=502, detail=f"Email send failed: {report.error}")

    if report.status == "rate_limited":
        raise HTTPException(
            status_code=429,
            detail=f"Rate limited for company '{company}'. Remaining slots: {remaining}",
        )

    updated = db.update_outreach_send_status(message_id, str(request.user_id), "delivered")
    audit(str(request.user_id), "outreach_email_sent", {"message_id": message_id}, application_run_id=None)

    return OutreachSendResponse(
        id=message_id,
        status="sent",
        delivery_status="delivered",
        sent_at=updated.get("sent_at") if updated else None,
        provider=get_email_provider_name(),
        rate_limit_remaining=remaining - 1 if remaining > 0 else 0,
    )


@router.get("/unsubscribe", response_model=UnsubscribeResponse)
async def unsubscribe(token: str = Query(...)):
    """Unsubscribe from future outreach emails."""
    result = verify_unsubscribe_token(token)
    if not result:
        raise HTTPException(status_code=400, detail="Invalid or expired unsubscribe token.")

    user_id, message_id = result
    message = db.get_outreach_by_unsubscribe_token(token)
    if message:
        db.mark_outreach_unsubscribed(token)
        audit(user_id, "outreach_unsubscribed", {"message_id": message_id}, application_run_id=None)
        return UnsubscribeResponse(
            status="unsubscribed",
            message="You have been unsubscribed from future outreach emails.",
        )

    return UnsubscribeResponse(
        status="already_unsubscribed",
        message="This token has already been processed.",
    )


@router.get("", response_model=OutreachListResponse)
async def list_outreach(user_id: UUID = Query(...), limit: int = Query(50, ge=1, le=100)):
    return OutreachListResponse(messages=db.list_outreach_messages(str(user_id), limit=limit))


@router.post("/{message_id}/mark-sent", response_model=OutreachMessageResponse)
async def mark_outreach_sent(message_id: str, request: OutreachMarkSentRequest):
    message = db.update_outreach_status(message_id, str(request.user_id), "sent_by_user")
    if not message:
        raise HTTPException(status_code=404, detail="Outreach message not found")
    audit(str(request.user_id), "outreach_marked_sent_by_user", {"message_id": message_id}, application_run_id=None)
    return message
