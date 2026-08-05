from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

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
from app.modules.cold_outreach.candidate_scorer import extract_jd_signals, rank_candidates
from app.modules.cold_outreach.crm_store import export_contacts_csv, list_contacts, upsert_contact
from app.modules.cold_outreach.email_finder import find_emails
from app.modules.cold_outreach.jd_ingest import ingest_jd_url
from app.modules.cold_outreach.schemas import (
    OutreachContactListResponse,
    OutreachContactRequest,
    OutreachContactResponse,
    OutreachDraftRequest,
    OutreachEmailFindRequest,
    OutreachEmailFindResponse,
    OutreachJdIngestRequest,
    OutreachJdIngestResponse,
    OutreachListResponse,
    OutreachMarkSentRequest,
    OutreachMessageResponse,
    OutreachRankRequest,
    OutreachRankResponse,
    OutreachRankedCandidate,
    OutreachSendRequest,
    OutreachSendResponse,
    UnsubscribeResponse,
)
from app.modules.safety.audit_log import audit


router = APIRouter()


def _resume_signal(user_id: str) -> str:
    resume = db.get_latest_resume(user_id)
    if not resume:
        return "data analysis, SQL, Python, and stakeholder reporting"
    parsed = resume.get("parsed") or {}
    skills = parsed.get("skills") or []
    if isinstance(skills, list) and skills:
        return ", ".join(str(skill) for skill in skills[:4])
    raw = str(resume.get("raw_text") or "").strip().splitlines()
    return raw[0] if raw else "data analysis and analytics"


def _resolve_job(job_id: str | None, user_id: str) -> dict | None:
    if not job_id:
        return None
    listing = db.get_job_listing(job_id)
    if listing:
        return {
            "id": listing["id"],
            "title": listing.get("title"),
            "company": listing.get("company"),
            "source_url": listing.get("source_url"),
        }
    return db.get_job(job_id, user_id=user_id)


def _compose_message(request: OutreachDraftRequest, job: dict | None, resume_signal: str) -> tuple[str, str, dict]:
    company = request.company or (job or {}).get("company") or "your team"
    role = (job or {}).get("title") or "the open role"
    contact = request.contact_name or "there"
    contact_role = request.contact_role or "Hiring Manager"
    template = request.template_type or "general"

    if request.tone == "formal":
        greeting = f"Dear {contact},"
        close = "Sincerely,"
    elif request.tone == "concise":
        greeting = f"Hi {contact},"
        close = "Thanks,"
    else:
        greeting = f"Hi {contact},"
        close = "Best,"

    if template == "linkedin_connect":
        # LinkedIn connection notes are ~300 chars; keep subject unused in UI.
        subject = f"LinkedIn connect — {role} at {company}"
        body = (
            f"Hi {contact} — I applied for {role} at {company}. "
            f"Background in {resume_signal}. Would value connecting; happy to share a short note on fit."
        )
        if len(body) > 280:
            body = body[:277] + "…"
    elif template == "coffee_chat":
        slots = (request.coffee_availability or "").strip()
        slot_line = (
            f"I am generally free {slots} — happy to adjust to your calendar."
            if slots
            else "Happy to work around your calendar — even a brief LinkedIn reply helps."
        )
        subject = f"Quick coffee chat — {role} at {company}" if company != "your team" else f"Coffee chat about {role}"
        body = (
            f"{greeting}\n\n"
            f"I recently applied / am preparing an application for {role} at {company}. "
            f"I would value a short 15-minute coffee chat to learn how your team approaches the work "
            f"(my background includes {resume_signal}).\n\n"
            f"{slot_line}\n\n"
            f"{close}\n"
        )
    elif template == "post_apply_thanks":
        subject = f"Thank you — application for {role}"
        body = (
            f"{greeting}\n\n"
            f"I just submitted my application for {role} at {company} and wanted to thank you for reviewing materials. "
            f"I am especially excited about the problems in the posting; my recent work covers {resume_signal}.\n\n"
            "If helpful, I can share a one-page project summary or walk through a relevant dashboard/analysis.\n\n"
            f"{close}\n"
        )
    elif template == "recruiter_ping":
        subject = f"Following up on {role} ({company})"
        body = (
            f"{greeting}\n\n"
            f"I applied for {role} at {company} and wanted to check whether you need any additional materials. "
            f"I can send a tailored resume focused on {resume_signal} right away.\n\n"
            f"{close}\n"
        )
    else:
        subject = f"Interest in {role} at {company}" if company != "your team" else f"Interest in {role}"
        body = (
            f"{greeting}\n\n"
            f"I noticed {role} at {company} and wanted to reach out directly. "
            f"My experience includes {resume_signal}, and I am especially interested in contributing to the problems described in the role.\n\n"
            "If it is useful, I would appreciate any guidance on the team, the hiring process, or whether my background could be a fit.\n\n"
            f"{close}\n"
        )

    metadata = {
        "safety": "draft_only_user_sends",
        "tone": request.tone,
        "template_type": template,
        "job_title": role,
        "contact_role": contact_role,
        "source_url": (job or {}).get("source_url"),
        "linkedin_url": request.linkedin_url,
        "contact_email": request.contact_email,
        "linkedin_search_hint": f"{company} {contact_role}",
    }
    return subject, body, metadata


@router.post("/jd-ingest", response_model=OutreachJdIngestResponse)
async def outreach_jd_ingest(request: OutreachJdIngestRequest):
    """Paste Greenhouse/Lever/LinkedIn Jobs URL → company, position, JD snippet."""
    result = await ingest_jd_url(request.url, jd_text_override=request.jd_text_override)
    audit(
        str(request.user_id),
        "outreach_jd_ingest",
        {"ok": result.get("ok"), "platform": result.get("platform"), "url": result.get("source_url")},
        application_run_id=None,
    )
    return OutreachJdIngestResponse(**result)


@router.post("/rank-candidates", response_model=OutreachRankResponse)
async def outreach_rank_candidates(request: OutreachRankRequest):
    """Score pasted LinkedIn-public candidate rows (no email lookup)."""
    if not request.candidates:
        return OutreachRankResponse(candidates=[], jd_signals=extract_jd_signals(request.jd_text, request.position))
    raw = [c.model_dump() for c in request.candidates]
    ranked = rank_candidates(
        raw,
        jd_text=request.jd_text,
        position=request.position,
        company_size=request.company_size,
    )
    signals = extract_jd_signals(request.jd_text, request.position)
    audit(
        str(request.user_id),
        "outreach_candidates_ranked",
        {"count": len(ranked), "company": request.company, "top_score": ranked[0]["score"] if ranked else 0},
        application_run_id=None,
    )
    return OutreachRankResponse(
        candidates=[OutreachRankedCandidate(**row) for row in ranked],
        jd_signals=signals,
    )


@router.post("/find-email", response_model=OutreachEmailFindResponse)
async def outreach_find_email(request: OutreachEmailFindRequest):
    """User-click single-person email lookup (Hunter if keyed, else format inference)."""
    if not (request.name or "").strip():
        raise HTTPException(status_code=400, detail="name required")
    # Soft rate limit: reuse cold_outreach bucket so enrichment cannot be spammed.
    rate_limiter.check(str(request.user_id), "cold_outreach", settings.MAX_DAILY_EMAILS)
    result = await find_emails(
        name=request.name.strip(),
        company=request.company,
        domain=request.domain,
        website=request.website,
        use_hunter=request.use_hunter,
    )
    audit(
        str(request.user_id),
        "outreach_email_lookup",
        {
            "name": request.name,
            "domain": result.get("domain"),
            "hunter": result.get("hunter_used"),
            "hits": len(result.get("candidates") or []),
        },
        application_run_id=None,
    )
    return OutreachEmailFindResponse(**result)


@router.post("/draft", response_model=OutreachMessageResponse)
async def draft_outreach(request: OutreachDraftRequest):
    rate_limiter.check(str(request.user_id), "cold_outreach", settings.MAX_DAILY_EMAILS)
    job = None
    if request.job_id:
        job = _resolve_job(str(request.job_id), str(request.user_id))
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
    company = request.company or (job or {}).get("company") or ""
    subject, body, metadata = _compose_message(request, job, _resume_signal(str(request.user_id)))
    if request.save_to_crm and (
        request.contact_name or request.linkedin_url or request.contact_email
    ):
        contact = upsert_contact(
            str(request.user_id),
            {
                "name": request.contact_name or "",
                "role": request.contact_role or "",
                "company": company or "",
                "job_id": str(request.job_id) if request.job_id else None,
                "linkedin_url": request.linkedin_url or "",
                "email": request.contact_email or "",
                "coffee_availability": request.coffee_availability or "",
                "status": "drafted",
                "notes": f"Last draft: {request.template_type}",
            },
        )
        metadata = {**metadata, "crm_contact_id": contact.get("id")}

    # Pre-generate message_id so we can embed it in the unsubscribe token
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
    audit(
        str(request.user_id),
        "outreach_draft_created",
        {"message_id": message_id, "template": request.template_type, "crm": request.save_to_crm},
        application_run_id=None,
    )
    return message


@router.get("/contacts", response_model=OutreachContactListResponse)
async def get_outreach_contacts(user_id: UUID = Query(...)):
    rows = list_contacts(str(user_id))
    return OutreachContactListResponse(contacts=rows)


@router.post("/contacts", response_model=OutreachContactResponse)
async def save_outreach_contact(request: OutreachContactRequest):
    if not (request.name or request.linkedin_url or request.email):
        raise HTTPException(status_code=400, detail="name, linkedin_url, or email required")
    row = upsert_contact(
        str(request.user_id),
        {
            "id": request.id,
            "name": request.name or "",
            "role": request.role or "",
            "company": request.company or "",
            "job_id": request.job_id,
            "linkedin_url": request.linkedin_url or "",
            "email": request.email or "",
            "coffee_availability": request.coffee_availability or "",
            "notes": request.notes or "",
            "status": request.status or "identified",
            "reply_status": request.reply_status or "none",
            "coffee_slots": request.coffee_slots or [],
        },
    )
    audit(
        str(request.user_id),
        "outreach_contact_upserted",
        {"contact_id": row.get("id"), "company": row.get("company")},
        application_run_id=None,
    )
    return row


@router.get("/contacts/export")
async def export_outreach_contacts(user_id: UUID = Query(...)):
    csv_text = export_contacts_csv(str(user_id))
    audit(
        str(user_id),
        "outreach_crm_exported",
        {"bytes": len(csv_text)},
        application_run_id=None,
    )
    return PlainTextResponse(
        csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="outreach_crm.csv"'},
    )


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
