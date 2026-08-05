from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app import db
from app.config import settings
from app.core.events import JobDiscoveredEvent, event_bus
from app.core.rate_limit import rate_limiter
from app.modules.application_engine.artifacts import create_application_artifacts
from app.modules.application_engine.application_saver import save_application_plan
from app.modules.application_engine.planner import ApplicationPlanner
from app.modules.job_discovery.orchestrator import discover_all
from app.modules.job_discovery import job_index
from app.modules.job_discovery.categories import (
    classify_job,
    label_for,
    slug_for_label,
    ui_categories,
)
from app.modules.job_discovery.schemas import (
    JobBookmarkRequest,
    JobBookmarkResponse,
    JobDiscoverRequest,
    JobHistoryRecord,
    JobHistoryResponse,
    JobIndexIngestRequest,
    JobIndexLeadRequest,
    JobIndexLeadResponse,
    JobIndexStatsResponse,
    JobIngestRequest,
    JobListResponse,
    JobPrepareApplicationRequest,
    JobPrepareApplicationResponse,
    JobRecommendResponse,
    JobResponse,
)
from app.modules.job_discovery.scorer import score_job_detailed, tokenize
from app.modules.resume_tailor.nodes.cover_letter import CoverLetterNode
from app.modules.resume_tailor.service import ResumeTailorService
from app.modules.resume_tailor.nodes.parse_jd import JDParsingNode
from app.modules.job_discovery.job_list_service import job_list_service
from app.modules.safety.audit_log import audit
from app.modules.safety.daily_limits import check_application_limit


router = APIRouter()
parser = JDParsingNode()
tailor_service = ResumeTailorService()
cover_letter_node = CoverLetterNode()
application_planner = ApplicationPlanner()


def _resolve_category(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip()
    if not raw or raw.lower() in {"all", "any"}:
        return None
    return slug_for_label(raw) or raw.lower().replace(" ", "_")


@router.post("/discover", response_model=JobListResponse)
async def discover_jobs(request: JobDiscoverRequest):
    rate_limiter.check(str(request.user_id), "job_discovery", settings.MAX_DAILY_APPLICATIONS)
    min_score = request.min_match_score if request.min_match_score is not None else 0.5
    if request.min_score_100 is not None:
        min_score = request.min_score_100
    resume_text = job_index.resume_text_for_user(str(request.user_id))

    provider_jobs: list[dict] = []
    if request.live or not settings.JOB_INDEX_ENABLED:
        # Write-through live path: fan-out providers, upsert into index, return.
        live_jobs = await discover_all(
            query=request.query,
            location=request.location,
            limit=request.limit,
            min_score=min_score if min_score <= 1 else min_score / 100.0,
            sites=request.sites if request.sites else None,
            hours_old=request.hours_old,
            country_indeed=request.country_indeed,
            user_id=str(request.user_id),
        )
        for lead in live_jobs:
            job_index.upsert_lead(lead)
        provider_jobs = live_jobs
        if request.work_model:
            wm = request.work_model.lower()
            provider_jobs = [
                j for j in provider_jobs
                if job_index.infer_work_model(j.get("location"), j.get("raw_text")) == wm
            ]
        if request.source_platform:
            sp = request.source_platform.lower()
            provider_jobs = [
                j for j in provider_jobs
                if (j.get("source_platform") or "").lower() == sp
            ]
    else:
        # JR-1 default: read local catalog only (no provider fan-out).
        provider_jobs = job_index.search_index(
            query=request.query,
            location=request.location,
            limit=request.limit,
            min_score=min_score,
            resume_text=resume_text,
            max_age_hours=request.hours_old,
            work_model=request.work_model,
            source_platform=request.source_platform,
            category=_resolve_category(request.category),
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
                "match_score": 50.0,
            }
            for idx in range(request.limit)
        ]

    jobs = []
    for idx, lead in enumerate(provider_jobs[: request.limit]):
        # Iter-7: avoid LLM JD parse on discover fan-out; use local token parse.
        raw_text = lead.get("raw_text") or ""
        keywords = sorted(tokenize(raw_text) | tokenize(request.query))[:40]
        meta = lead.get("metadata") or {}
        detail = score_job_detailed(
            {
                "title": lead.get("title") or request.query.title(),
                "raw_text": raw_text,
                "required_skills": [],
                "preferred_skills": [],
                "ats_keywords": keywords,
                "key_responsibilities": [],
            },
            request.query,
            resume_text=resume_text,
        )
        parsed = {
            "title": lead.get("title") or request.query.title(),
            "company": lead.get("company"),
            "location": lead.get("location") or request.location,
            "raw_text": raw_text,
            "required_skills": [],
            "preferred_skills": [],
            "key_responsibilities": [],
            "company_values": [],
            "ats_keywords": keywords,
            "listing_id": meta.get("listing_id"),
            "from_index": bool(meta.get("from_index")),
            "score_breakdown": meta.get("score_breakdown") or detail["score_breakdown"],
            "matched_skills": meta.get("matched_skills") or detail["matched_skills"],
            "missing_skills": meta.get("missing_skills") or detail["missing_skills"],
            "jd_skills": detail.get("jd_skills") or [],
            "category": meta.get("category") or lead.get("category"),
            "category_label": meta.get("category_label")
            or label_for(meta.get("category") or lead.get("category") or "other"),
        }
        match_score = lead.get("match_score")
        if match_score is None:
            match_score = detail["match_score"]
        final_score = round(float(match_score), 1)
        job_id = db.save_job(
            user_id=str(request.user_id),
            title=parsed.get("title") or lead.get("title") or request.query.title(),
            company=parsed.get("company") or lead.get("company") or f"Target Company {idx + 1}",
            location=parsed.get("location") or lead.get("location") or request.location,
            source_url=lead.get("source_url"),
            source_platform=lead.get("source_platform") or "local_phase2",
            raw_text=raw_text,
            parsed=parsed,
            match_score=final_score,
        )
        await event_bus.publish(JobDiscoveredEvent(
            user_id=request.user_id,
            job_id=UUID(job_id),
            source_platform=lead.get("source_platform") or "local_phase2",
            match_score=final_score,
        ))
        jobs.append(db.get_job(job_id, str(request.user_id)) or db.list_jobs(str(request.user_id), limit=1)[0])
    return JobListResponse(jobs=jobs)


@router.post("/index/ingest")
async def ingest_job_index(request: JobIndexIngestRequest):
    """Manual write-path trigger for the shared job catalog."""
    result = await job_index.ingest_queries(
        queries=request.queries or None,
        location=request.location,
        limit_per_query=request.limit_per_query,
        hours_old=request.hours_old,
        country_indeed=request.country_indeed,
        sites=request.sites or None,
    )
    return result


def _extension_token_ok(token: str | None) -> bool:
    expected = (settings.EXTENSION_BRIDGE_TOKEN or "").strip()
    if not expected:
        # Empty token config: allow only in development.
        return settings.APP_ENV == "development"
    provided = (token or "").strip()
    return bool(provided) and provided == expected


def _workbench_urls(job_id: str) -> dict[str, str]:
    base = (settings.FRONTEND_BASE_URL or "http://localhost:3000").rstrip("/")
    root = f"{base}/?view=resume&jobId={job_id}"
    return {
        # Jobright already shows JD — open Tailor (agent + PDF) directly.
        "workspace_url": f"{root}&step=tailor",
        "apply_step_url": f"{root}&step=apply",
        # Outreach is a dedicated page — never embed beside the PDF.
        "outreach_step_url": f"{base}/outreach?jobId={job_id}",
    }


@router.post("/index/leads", response_model=JobIndexLeadResponse)
async def upsert_index_lead(
    request: JobIndexLeadRequest,
    x_extension_token: str | None = Header(default=None, alias="X-Extension-Token"),
):
    """Upsert one job into the shared catalog (Jobright extension / import bridge)."""
    if not _extension_token_ok(x_extension_token):
        raise HTTPException(status_code=401, detail="Invalid or missing X-Extension-Token")

    meta = dict(request.metadata or {})
    jobright_url = (request.jobright_url or meta.get("jobright_url") or meta.get("page_url") or "").strip() or None
    page_url = (meta.get("page_url") or jobright_url or "").strip() or None
    apply_url = (meta.get("apply_url") or "").strip() or None
    # Jobright Apply = company ATS when usable; thin Workday roots fall back to board.
    from app.modules.job_discovery.apply_url import (
        is_usable_job_apply_url,
        normalize_apply_url,
        prefer_official_apply_url,
    )

    apply_url = normalize_apply_url(apply_url)
    platform = (request.source_platform or "jobright_extension").strip()
    if (
        apply_url
        and is_usable_job_apply_url(apply_url)
        and (
            ("jobright" in platform.lower() and "jobright.ai" not in apply_url.lower())
            or "utm_source=jobright" in apply_url.lower()
        )
    ):
        source_url = apply_url
    else:
        source_url = prefer_official_apply_url(
            request.source_url,
            apply_url,
            jobright_url if jobright_url and "jobright.ai" not in jobright_url.lower() else None,
            page_url if page_url and "jobright.ai" not in page_url.lower() else None,
            board_fallback=jobright_url or page_url or request.source_url,
        )
    if jobright_url:
        meta["jobright_url"] = jobright_url
    if page_url:
        meta["page_url"] = page_url
    if apply_url:
        meta["apply_url"] = apply_url
    meta["has_external_apply"] = bool(
        apply_url and "jobright.ai" not in apply_url.lower()
    )
    if request.category:
        meta["category"] = request.category

    lead = {
        "title": request.title.strip(),
        "company": request.company.strip(),
        "location": request.location,
        "source_url": source_url,
        "source_platform": request.source_platform or "jobright_extension",
        "raw_text": request.raw_text,
        "work_model": request.work_model,
        "category": request.category,
        "metadata": meta,
    }

    from app.modules.job_discovery.quality import assess_listing_quality

    verdict = assess_listing_quality(lead, min_chars=int(settings.JOB_INDEX_MIN_JD_CHARS))
    quality_ok = bool(verdict.get("ok"))
    quality_reason = str(verdict.get("reason") or "unknown")
    if settings.JOB_INDEX_QUALITY_GATE and not quality_ok and not request.force:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Listing failed quality gate",
                "reason": quality_reason,
                "body_len": verdict.get("body_len"),
                "hint": "Paste a fuller JD, add an http(s) apply URL, or retry with force=true.",
            },
        )

    meta["quality"] = {
        "ok": quality_ok,
        "reason": quality_reason,
        "body_len": verdict.get("body_len"),
        "forced": bool(request.force and not quality_ok),
    }
    lead["metadata"] = meta

    listing_id, created = job_index.upsert_lead(lead)
    urls = _workbench_urls(listing_id)
    return JobIndexLeadResponse(
        id=listing_id,
        created=created,
        source_platform=str(lead["source_platform"]),
        quality_ok=quality_ok,
        quality_reason=quality_reason,
        **urls,
    )

@router.get("/index/stats", response_model=JobIndexStatsResponse)
async def job_index_stats():
    from app.modules.job_discovery.categories import all_ingest_queries

    return JobIndexStatsResponse(
        active_total=db.count_job_listings("active"),
        enabled=settings.JOB_INDEX_ENABLED,
        interval_minutes=settings.JOB_INDEX_INGEST_INTERVAL_MINUTES,
        default_queries=all_ingest_queries()
        if (settings.JOB_INDEX_DEFAULT_QUERIES or "").strip().lower() in {"", "auto"}
        else [q.strip() for q in settings.JOB_INDEX_DEFAULT_QUERIES.split(",") if q.strip()],
    )


@router.get("/providers/jobspy/health")
async def jobspy_health():
    """Fast JobSpy readiness check (no live scrape)."""
    import os
    from pathlib import Path

    from app.modules.job_discovery.providers.jobspy_provider import _SCRAPER, _worker_python

    py = _worker_python()
    configured = (settings.JOBSPY_PYTHON or "").strip()
    path_ok = Path(py).exists() if (os.path.isabs(py) or "\\" in py or "/" in py) else True
    worker_ok = _SCRAPER.exists()
    enabled = bool(settings.JOB_INDEX_ENABLE_JOBSPY)
    status = "ok" if enabled and worker_ok and path_ok else "degraded"
    return {
        "status": status,
        "enabled": enabled,
        "worker_python": py,
        "jobspy_python_configured": bool(configured),
        "worker_script_exists": worker_ok,
        "python_path_ok": path_ok,
    }


@router.get("/categories")
async def list_job_categories():
    return {
        "categories": ui_categories(),
        "counts": db.count_job_listings_by_category("active"),
    }


@router.post("/index/reclassify")
async def reclassify_job_index():
    n = db.backfill_listing_categories(classify_job)
    return {"updated": n, "counts": db.count_job_listings_by_category("active")}

class AutoDiscoverRequest(BaseModel):
    user_id: UUID
    query: str | None = None
    location: str | None = None
    limit: int = Field(default=20, ge=1, le=50)


@router.post("/auto-discover", response_model=JobListResponse)
async def auto_discover_jobs(request: AutoDiscoverRequest):
    """Auto-discover jobs based on the user's latest resume."""
    query = request.query
    if not query:
        resume = db.get_latest_resume(str(request.user_id))
        if resume:
            parsed = resume.get("parsed") or {}
            query = parsed.get("title") or ""
        if not query:
            raise HTTPException(status_code=400, detail="No resume found. Please upload a resume or provide a search query.")

    discover_request = JobDiscoverRequest(
        user_id=request.user_id,
        query=query,
        location=request.location,
        limit=request.limit,
    )
    return await discover_jobs(discover_request)


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


@router.get("/recommended", response_model=JobRecommendResponse)
async def recommended_jobs(user_id: UUID = Query(...), top_n: int = Query(10, ge=1, le=50)):
    """Jobs with match_score >= 85, sorted descending, excluding already-processed jobs."""
    all_jobs = db.list_jobs(str(user_id), limit=200)
    processed = db.list_processed_job_ids(str(user_id))
    filtered = [
        {"id": j["id"], "title": j["title"], "company": j["company"], "location": j["location"],
         "source_platform": j["source_platform"], "source_url": j["source_url"],
         "match_score": j.get("match_score"), "raw_text": j["raw_text"], "parsed": j["parsed"],
         "created_at": j["created_at"]}
        for j in all_jobs
        if j.get("match_score") is not None and j["match_score"] >= 85 and j["id"] not in processed
    ]
    filtered.sort(key=lambda x: x["match_score"] or 0, reverse=True)
    top = filtered[:top_n]
    return JobRecommendResponse(jobs=top, total_candidates=len(filtered), already_processed=len(processed))


@router.get("/history", response_model=JobHistoryResponse)
async def job_history(user_id: UUID = Query(...), limit: int = Query(50, ge=1, le=200)):
    records = db.list_job_history_with_details(str(user_id), limit=limit)
    return JobHistoryResponse(records=records)


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
    db.record_job_action(str(request.user_id), str(job_id), "resume_prepared",
                         {"tailored_resume_id": tailored.get("tailored_resume_id")})

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
        action = "auto_submitted" if planned["plan"]["mode"] == "auto_submit" else "prepared_for_submit"
        db.record_job_action(str(request.user_id), str(job_id), action,
                             {"application_run_id": run_id, "ats_type": planned["plan"]["ats_type"]})
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


@router.get("/{job_id}/actions", response_model=dict)
async def get_job_actions(job_id: UUID, user_id: UUID = Query(...)):
    actions = db.get_job_actions(str(user_id), str(job_id))
    return {"job_id": str(job_id), "actions": actions}


@router.get("/list", response_model=dict)
async def list_user_jobs_filtered(
    user_id: str = Query(...),
    threshold: float = Query(0, ge=0, le=100),
    sort_by: str = Query("score"),
    top_n: int = Query(0, ge=0, le=100),
    source: str = Query(""),
    search: str = Query(""),
    category: str = Query(""),
):
    return job_list_service.list_jobs(
        threshold=threshold,
        sort_by=sort_by,
        top_n=top_n,
        source=source,
        search=search,
        category=_resolve_category(category) or "",
        user_id=user_id,
    )


@router.post("/translate-segments", response_model=dict)
async def translate_jd_segments(body: dict):
    """Bilingual JD helper: translate Required/Preferred bullets EN→zh."""
    from app.modules.job_discovery.translate import translate_segments

    texts = body.get("texts") or []
    if not isinstance(texts, list):
        raise HTTPException(status_code=400, detail="texts must be a list of strings")
    target = str(body.get("target_lang") or "zh-CN")
    return await translate_segments([str(t) for t in texts], target_lang=target)


@router.get("/{job_id}/summary", response_model=dict)
async def job_summary(job_id: str, user_id: str | None = Query(None)):
    summary = job_list_service.get_summary(job_id, user_id=user_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Job not found")
    return summary


@router.get("/{job_id}/detail", response_model=dict)
async def job_detail(job_id: str, user_id: str | None = Query(None)):
    job = job_list_service.get_job(job_id, user_id=user_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    summary = job_list_service.get_summary(job_id, user_id=user_id) or {}
    return {"job": job, "summary": summary}


@router.post("/{job_id}/score", response_model=dict)
async def score_job_endpoint(job_id: str):
    result = job_list_service.trigger_scoring(job_id)
    if not result:
        raise HTTPException(status_code=404, detail="Job not found")
    return result


@router.post("/{job_id}/to-resume-workspace", response_model=dict)
async def to_resume_workspace(job_id: str, user_id: str = Query(...)):
    result = job_list_service.to_resume_workspace(job_id, user_id)
    if not result:
        raise HTTPException(status_code=404, detail="Job not found")
    return result


@router.get("/sources/list", response_model=dict)
async def list_sources(user_id: str = Query(...)):
    return {"sources": job_list_service.get_available_sources(user_id=user_id)}


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
