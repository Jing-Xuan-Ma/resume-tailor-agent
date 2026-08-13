from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app import db
from app.config import settings
from app.core.rate_limit import rate_limiter
from app.modules.cold_outreach.schemas import (
    OutreachDraftRequest,
    OutreachListResponse,
    OutreachMarkSentRequest,
    OutreachMessageResponse,
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

    if template == "coffee_chat":
        subject = f"Quick coffee chat — {role} at {company}" if company != "your team" else f"Coffee chat about {role}"
        body = (
            f"{greeting}\n\n"
            f"I recently applied / am preparing an application for {role} at {company}. "
            f"I would value a short 15-minute coffee chat to learn how your team approaches the work "
            f"(my background includes {resume_signal}).\n\n"
            "Happy to work around your calendar — even a brief LinkedIn reply helps.\n\n"
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


@router.post("/draft", response_model=OutreachMessageResponse)
async def draft_outreach(request: OutreachDraftRequest):
    rate_limiter.check(str(request.user_id), "cold_outreach", settings.MAX_DAILY_EMAILS)
    job = None
    if request.job_id:
        job = _resolve_job(str(request.job_id), str(request.user_id))
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
    subject, body, metadata = _compose_message(request, job, _resume_signal(str(request.user_id)))
    message_id = db.save_outreach_message(
        user_id=str(request.user_id),
        job_id=str(request.job_id) if request.job_id else None,
        contact_name=request.contact_name,
        contact_role=request.contact_role,
        company=request.company or (job or {}).get("company"),
        channel=request.channel,
        subject=subject,
        body=body,
        metadata=metadata,
    )
    message = db.get_outreach_message(message_id, user_id=str(request.user_id))
    audit(str(request.user_id), "outreach_draft_created", {"message_id": message_id, "template": request.template_type}, application_run_id=None)
    return message


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
