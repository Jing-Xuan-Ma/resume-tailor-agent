"""Job list service — backed by real DB data and three-stage scoring pipeline."""

import logging
from typing import Any

from app import db
from app.modules.job_discovery.scoring_pipeline import score_all_jobs, stage3_score

logger = logging.getLogger(__name__)


def _build_job_listing(job: dict, user_id: str = "") -> dict:
    s3 = job.get("_stage3_result")
    return {
        "id": job["id"],
        "company": job.get("company") or "",
        "title": job.get("title") or "",
        "source": job.get("source_platform") or "",
        "originalUrl": job.get("source_url") or "",
        "scrapedAt": job.get("created_at") or "",
        "passedStage1": job.get("_passed_stage1", False),
        "stage2Score": job.get("_stage2_score"),
        "stage3Result": s3,
        "status": _resolve_status(job.get("id", ""), user_id),
        "linkedApplicationId": _resolve_linked_app(job.get("id", ""), user_id),
    }


def _resolve_status(job_id: str, user_id: str = "") -> str:
    """Determine latest status from job actions."""
    actions = db.get_job_actions(user_id, job_id) if user_id else []
    if not actions:
        return "unprocessed"
    action_map = {
        "resume_prepared": "resume_generated",
        "prepared_for_submit": "applied",
        "auto_submitted": "applied",
        "submitted_by_user": "applied",
    }
    for a in reversed(actions):
        mapped = action_map.get(a.get("action", ""))
        if mapped:
            return mapped
    return "unprocessed"


def _resolve_linked_app(job_id: str, user_id: str = "") -> str | None:
    actions = db.get_job_actions(user_id, job_id) if user_id else []
    if actions:
        for a in reversed(actions):
            meta = a.get("metadata") or {}
            rid = meta.get("application_run_id")
            if rid:
                return rid
    return None


class JobListService:

    def list_jobs(
        self,
        threshold: float = 0,
        sort_by: str = "score",
        top_n: int = 0,
        source: str = "",
        search: str = "",
        user_id: str = "",
    ) -> dict:
        # Load jobs from DB
        raw_jobs = db.list_jobs(user_id, limit=200) if user_id else []

        # Get resume for scoring
        resume_text = ""
        resume_parsed: dict | None = None
        if user_id:
            resume = db.get_latest_resume(user_id)
            if resume:
                resume_text = resume.get("raw_text") or ""
                resume_parsed = resume.get("parsed")

        # Fallback if no DB jobs
        if not raw_jobs:
            return {"jobs": [], "total": 0, "filtered_total": 0}

        # Source filter (applied before scoring to save work)
        if source:
            raw_jobs = [j for j in raw_jobs if (j.get("source_platform") or "") == source]

        # Search filter
        if search:
            s = search.lower()
            raw_jobs = [
                j for j in raw_jobs
                if s in (j.get("title") or "").lower() or s in (j.get("company") or "").lower()
            ]

        # Run scoring pipeline
        scored = score_all_jobs(raw_jobs, resume_text, resume_parsed, skip_stage2=True)

        # Build listings
        listings = [_build_job_listing(j, user_id) for j in scored]

        # Separate scored and unscored
        scored_listings = [
            j for j in listings
            if j["passedStage1"] and j.get("stage3Result") and j["stage3Result"].get("hardConditionsPassed", True)
        ]
        unscored_listings = [j for j in listings if j not in scored_listings]

        # Apply threshold (spec: applies before topN)
        threshold_pct = threshold / 100.0
        above = [j for j in scored_listings if (j.get("stage3Result") or {}).get("finalScore", 0) >= threshold_pct]

        # Apply topN on threshold-filtered results (spec: Section 3)
        if top_n > 0 and len(above) > top_n:
            above.sort(key=lambda j: (j.get("stage3Result") or {}).get("finalScore", 0), reverse=True)
            above = above[:top_n]

        # Sort
        if sort_by == "score":
            above.sort(key=lambda j: (j.get("stage3Result") or {}).get("finalScore", 0), reverse=True)
        else:
            above.sort(key=lambda j: j.get("scrapedAt", ""), reverse=True)

        result = above + unscored_listings

        return {
            "jobs": result,
            "total": len(result),
            "filtered_total": len(above),
        }

    def get_summary(self, job_id: str) -> dict | None:
        job = db.get_job(job_id)
        if not job:
            return None

        resume = db.get_latest_resume(job.get("user_id", ""))
        resume_text = (resume.get("raw_text") or "") if resume else ""
        resume_parsed = (resume.get("parsed") or {}) if resume else None

        s3 = stage3_score(job, resume_text, resume_parsed)
        return {
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "atsScore": s3.get("atsScore", 0),
            "semanticScore": s3.get("semanticScore", 0),
            "finalScore": s3.get("finalScore", 0),
            "coveredKeywords": s3.get("coveredKeywords", []),
            "missingKeywords": s3.get("missingKeywords", []),
            "hasHardConditionIssues": not s3.get("hardConditionsPassed", True),
            "hardConditionIssues": s3.get("hardConditionIssues", []),
            "status": _resolve_status(job_id),
        }

    def trigger_scoring(self, job_id: str) -> dict | None:
        job = db.get_job(job_id)
        if not job:
            return None
        resume = db.get_latest_resume(job.get("user_id", ""))
        resume_text = (resume.get("raw_text") or "") if resume else ""
        resume_parsed = (resume.get("parsed") or {}) if resume else None
        s3 = stage3_score(job, resume_text, resume_parsed)
        return {"stage3Result": s3}

    def to_resume_workspace(self, job_id: str, user_id: str) -> dict | None:
        job = db.get_job(job_id)
        if not job:
            return None
        session = db.create_jd_session(
            user_id=user_id,
            job_id=job_id,
            jd_text=job.get("raw_text", ""),
        )
        return {"sessionId": session["id"], "jobId": job_id}

    def get_available_sources(self, user_id: str = "") -> list[str]:
        if not user_id:
            return []
        jobs = db.list_jobs(user_id, limit=500)
        sources = set()
        for j in jobs:
            sp = j.get("source_platform")
            if sp:
                sources.add(sp)
        return sorted(sources)


job_list_service = JobListService()
