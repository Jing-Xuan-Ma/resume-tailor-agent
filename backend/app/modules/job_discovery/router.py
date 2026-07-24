from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app import db
from app.config import settings
from app.core.events import JobDiscoveredEvent, event_bus
from app.core.rate_limit import rate_limiter
from app.modules.application_engine.artifacts import create_application_artifacts
from app.modules.application_engine.application_saver import save_application_plan
from app.modules.application_engine.planner import ApplicationPlanner
from app.modules.job_discovery.providers.jobspy_provider import JobSpyProvider
from app.modules.job_discovery.schemas import (
    JobBookmarkRequest,
    JobBookmarkResponse,
    JobDiscoverRequest,
    JobIngestRequest,
    JobListResponse,
    JobPrepareApplicationRequest,
    JobPrepareApplicationResponse,
    JobResponse,
)
from app.modules.job_discovery.scorer import score_job
from app.modules.resume_tailor.nodes.cover_letter import CoverLetterNode
from app.modules.resume_tailor.service import ResumeTailorService
from app.modules.resume_tailor.nodes.parse_jd import JDParsingNode
from app.modules.safety.audit_log import audit
from app.modules.safety.daily_limits import check_application_limit


router = APIRouter()
parser = JDParsingNode()
jobspy_provider = JobSpyProvider()
tailor_service = ResumeTailorService()
cover_letter_node = CoverLetterNode()
application_planner = ApplicationPlanner()


def _synthetic_job_text(query: str, location: str | None, idx: int) -> str:
    title = query.title()
    company = f"Target Company {idx + 1}"
    loc = location or "Remote"
    return f"""{title}
Company: {company}
Location: {loc}

Responsibilities:
- Deliver projects related to {query}
- Collaborate with cross-functional teams and communicate progress
- Improve workflows, quality, and measurable outcomes

Requirements:
- Experience with {query}
- Strong analytical, communication, and execution skills
- Ability to work in a fast-paced environment
"""


@router.post("/discover", response_model=JobListResponse)
async def discover_jobs(request: JobDiscoverRequest):
    """Phase 2 entrypoint: create candidate job leads for a query.

    This starts with deterministic local discovery so the product flow is usable
    without third-party job-board credentials. External providers can be added
    behind this API without changing the frontend contract.
    """
    rate_limiter.check(str(request.user_id), "job_discovery", settings.MAX_DAILY_APPLICATIONS)
    provider_jobs = []
    if request.provider == "jobspy":
        provider_jobs = jobspy_provider.discover(
            query=request.query,
            location=request.location,
            limit=request.limit,
            sites=request.sites,
            hours_old=request.hours_old,
            country_indeed=request.country_indeed,
        )

    if not provider_jobs:
        provider_jobs = [
            {
                "title": request.query.title(),
                "company": f"Target Company {idx + 1}",
                "location": request.location or "Remote",
                "source_url": None,
                "source_platform": "local_phase2",
                "raw_text": _synthetic_job_text(request.query, request.location, idx),
            }
            for idx in range(request.limit)
        ]

    jobs = []
    for idx, lead in enumerate(provider_jobs[: request.limit]):
        raw_text = lead["raw_text"]
        parsed_model = await parser.parse(raw_text)
        parsed = parsed_model.model_dump()
        match_score = score_job(parsed, request.query)
        job_id = db.save_job(
            user_id=str(request.user_id),
            title=parsed.get("title") or lead.get("title") or request.query.title(),
            company=parsed.get("company") or lead.get("company") or f"Target Company {idx + 1}",
            location=parsed.get("location") or lead.get("location") or request.location,
            source_url=lead.get("source_url"),
            source_platform=lead.get("source_platform") or "local_phase2",
            raw_text=raw_text,
            parsed=parsed,
            match_score=match_score,
        )
        await event_bus.publish(JobDiscoveredEvent(user_id=request.user_id, job_id=UUID(job_id), source_platform=lead.get("source_platform") or "local_phase2", match_score=match_score))
        jobs.append(db.list_jobs(str(request.user_id), limit=1)[0])
    return JobListResponse(jobs=jobs)


@router.post("/ingest", response_model=JobResponse)
async def ingest_job(request: JobIngestRequest):
    rate_limiter.check(str(request.user_id), "job_discovery", settings.MAX_DAILY_APPLICATIONS)
    parsed_model = await parser.parse(request.raw_text)
    parsed = parsed_model.model_dump()
    job_id = db.save_job(
        user_id=str(request.user_id),
        title=parsed.get("title") or "Imported Job",
        company=parsed.get("company"),
        location=parsed.get("location"),
        source_url=request.source_url,
        source_platform=request.source_platform,
        raw_text=request.raw_text,
        parsed=parsed,
        match_score=None,
    )
    job = db.list_jobs(str(request.user_id), limit=1)[0]
    if job["id"] != job_id:
        raise HTTPException(status_code=500, detail="Failed to retrieve ingested job")
    return job


@router.get("", response_model=JobListResponse)
async def list_user_jobs(user_id: UUID = Query(...), limit: int = Query(20, ge=1, le=100)):
    return JobListResponse(jobs=db.list_jobs(str(user_id), limit=limit))


@router.post("/bookmarks", response_model=JobBookmarkResponse)
async def bookmark_job(request: JobBookmarkRequest):
    job = db.get_job(str(request.job_id), user_id=str(request.user_id))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    bookmark = db.bookmark_job(str(request.user_id), str(request.job_id), request.notes)
    return JobBookmarkResponse(bookmark=bookmark)


@router.get("/bookmarks", response_model=JobListResponse)
async def list_bookmarks(user_id: UUID = Query(...), limit: int = Query(50, ge=1, le=100)):
    return JobListResponse(jobs=db.list_bookmarked_jobs(str(user_id), limit=limit))


@router.post("/{job_id}/prepare-application", response_model=JobPrepareApplicationResponse)
async def prepare_application_for_job(job_id: UUID, request: JobPrepareApplicationRequest):
    check_application_limit(str(request.user_id))
    job = db.get_job(str(job_id), user_id=str(request.user_id))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    tailored = await tailor_service.tailor(
        user_id=request.user_id,
        resume_id=request.resume_id,
        jd_text=job["raw_text"],
        job_id=job_id,
    )

    cover_letter = None
    if request.include_cover_letter:
        original_resume = tailor_service._rebuild_resume_data(str(request.user_id))
        generated = await cover_letter_node.run(
            job=job,
            tailored_resume=tailored.get("tailored_resume") or {},
            original_resume=original_resume,
        )
        cover_letter_id = db.save_cover_letter(
            user_id=str(request.user_id),
            job_id=str(job_id),
            tailored_resume_id=tailored.get("tailored_resume_id"),
            text=generated["text"],
            metadata={"model": generated.get("model"), "source": generated.get("source")},
        )
        cover_letter = {"id": cover_letter_id, **generated}

    application_plan = None
    if request.include_application_plan:
        user = db.get_user(str(request.user_id)) or {}
        profile = {**user, **(db.get_profile(str(request.user_id)) or {}), **request.user_profile}
        artifacts = create_application_artifacts(
            user_id=str(request.user_id),
            application_run_id=str(job_id),
            draft=tailor_service.get_draft(request.user_id, tailored.get("draft_id")) if tailored.get("draft_id") else None,
            cover_letter=cover_letter,
        )
        planned = application_planner.build_plan(
            job=job,
            user_profile=profile,
            tailored_resume_id=tailored.get("tailored_resume_id"),
            auto_submit=request.auto_submit,
            submit_mode=request.submit_mode,
            artifacts=artifacts,
        )
        planned["plan"]["cover_letter_id"] = cover_letter["id"] if cover_letter else None
        run_id = save_application_plan(
            user_id=str(request.user_id),
            job_id=str(job_id),
            tailored_resume_id=tailored.get("tailored_resume_id"),
            ats_type=planned["plan"]["ats_type"],
            plan=planned["plan"],
            answers=planned["answers"],
            submit_mode=planned["plan"]["mode"],
        )
        audit(str(request.user_id), "job_application_package_prepared", {"job_id": str(job_id)}, application_run_id=run_id)
        status = "prepared_for_auto_submit" if planned["plan"]["mode"] == "auto_submit" else "prepared_pending_manual_review"
        db.update_application_run_status(run_id=run_id, user_id=str(request.user_id), status=status, submission_result={})
        application_plan = {"application_run_id": run_id, "status": status, **planned}

    return JobPrepareApplicationResponse(
        job=job,
        tailored=tailored,
        cover_letter=cover_letter,
        application_plan=application_plan,
    )
