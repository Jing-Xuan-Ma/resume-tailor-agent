from typing import Any
from uuid import uuid4
from datetime import UTC, datetime, timedelta
from app import db
from app.modules.job_discovery.posted_at import display_age_iso
from app.modules.job_discovery.apply_url import resolve_listing_apply_url


_META = {
    "mock_job_001": {"location": "Mountain View, CA", "workModel": "Hybrid", "salary": "$180k - $260k"},
    "mock_job_002": {"location": "Menlo Park, CA", "workModel": "Remote", "salary": "$170k - $240k"},
    "mock_job_003": {"location": "Seattle, WA", "workModel": "On Site", "salary": "$160k - $220k"},
    "mock_job_004": {"location": "San Francisco, CA", "workModel": "Hybrid", "salary": "$190k - $280k"},
    "mock_job_005": {"location": "New York, NY", "workModel": "Remote", "salary": "$165k - $230k"},
    "mock_job_006": {"location": "Remote", "workModel": "Remote", "salary": "N/A"},
    "mock_job_007": {"location": "Redmond, WA", "workModel": "Hybrid", "salary": "$200k - $300k"},
    "mock_job_008": {"location": "San Francisco, CA", "workModel": "On Site", "salary": "$220k - $320k"},
    "mock_job_009": {"location": "Cupertino, CA", "workModel": "On Site", "salary": "$150k - $210k"},
    "mock_job_010": {"location": "Los Gatos, CA", "workModel": "Hybrid", "salary": "$210k - $310k"},
}


def _enrich(job: dict[str, Any]) -> dict[str, Any]:
    meta = _META.get(job["id"], {"location": "N/A", "workModel": "Remote", "salary": "N/A"})
    return {**job, **meta}


def _fresh_mock_jobs() -> list[dict[str, Any]]:
    """Demo fixtures with relative ages so empty-catalog UI never looks weeks stale."""
    now = datetime.now(UTC)
    offsets_hours = (2, 5, 8, 12, 18, 24, 30, 36, 42, 48)
    out: list[dict[str, Any]] = []
    for job, hours in zip(MOCK_JOBS, offsets_hours, strict=False):
        cloned = dict(job)
        cloned["scrapedAt"] = (now - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
        out.append(cloned)
    return out


MOCK_JOBS: list[dict[str, Any]] = [
    {
        "id": "mock_job_001",
        "company": "Google",
        "title": "Senior Software Engineer, Infrastructure",
        "source": "linkedin",
        # Demo fixtures intentionally have no live posting URL (avoid fake amazon.com/jobs/N redirects).
        "originalUrl": "",
        "scrapedAt": "2026-07-27T08:00:00Z",
        "passedStage1": True,
        "stage2Score": 82,
        "stage3Result": {
            "atsScore": 0.78, "semanticScore": 0.85, "hardConditionsPassed": True,
            "finalScore": 0.83, "coveredKeywords": ["Python", "Go", "Kubernetes", "Docker", "distributed systems"],
            "missingKeywords": ["Terraform", "Istio"],
        },
        "status": "unprocessed",
    },
    {
        "id": "mock_job_002",
        "company": "Meta",
        "title": "Backend Engineer - ML Platform",
        "source": "linkedin",
        "originalUrl": "",
        "scrapedAt": "2026-07-27T07:30:00Z",
        "passedStage1": True,
        "stage2Score": 78,
        "stage3Result": {
            "atsScore": 0.72, "semanticScore": 0.80, "hardConditionsPassed": True,
            "finalScore": 0.77, "coveredKeywords": ["Python", "Go", "Kafka", "PostgreSQL"],
            "missingKeywords": ["PyTorch", "ML pipelines", "Ray"],
        },
        "status": "unprocessed",
    },
    {
        "id": "mock_job_003",
        "company": "Amazon",
        "title": "SDE II - AWS Infrastructure",
        "source": "jobspy",
        "originalUrl": "",
        "scrapedAt": "2026-07-26T18:00:00Z",
        "passedStage1": True,
        "stage2Score": 91,
        "stage3Result": {
            "atsScore": 0.90, "semanticScore": 0.88, "hardConditionsPassed": True,
            "finalScore": 0.89, "coveredKeywords": ["Python", "Kubernetes", "Docker", "AWS", "microservices"],
            "missingKeywords": ["Java", "CloudFormation"],
        },
        "status": "resume_generated",
        "linkedApplicationId": "run_003",
    },
    {
        "id": "mock_job_004",
        "company": "Stripe",
        "title": "Senior Backend Engineer - Payments",
        "source": "jobspy",
        "originalUrl": "",
        "scrapedAt": "2026-07-26T16:00:00Z",
        "passedStage1": True,
        "stage2Score": 65,
        "stage3Result": {
            "atsScore": 0.55, "semanticScore": 0.70, "hardConditionsPassed": True,
            "finalScore": 0.61, "coveredKeywords": ["PostgreSQL", "Redis", "distributed systems"],
            "missingKeywords": ["Ruby", "PCI compliance", "idempotency"],
        },
        "status": "unprocessed",
    },
    {
        "id": "mock_job_005",
        "company": "Datadog",
        "title": "Software Engineer - Observability",
        "source": "indeed",
        "originalUrl": "",
        "scrapedAt": "2026-07-25T12:00:00Z",
        "passedStage1": True,
        "stage2Score": 88,
        "stage3Result": {
            "atsScore": 0.85, "semanticScore": 0.92, "hardConditionsPassed": True,
            "finalScore": 0.88, "coveredKeywords": ["Go", "Kubernetes", "Kafka", "distributed systems", "monitoring"],
            "missingKeywords": ["OpenTelemetry"],
        },
        "status": "applied",
        "linkedApplicationId": "run_005",
    },
    {
        "id": "mock_job_006",
        "company": "Cloudflare",
        "title": "Network Engineer",
        "source": "linkedin",
        "originalUrl": "",
        "scrapedAt": "2026-07-25T10:00:00Z",
        "passedStage1": False,
        "stage2Score": None,
        "stage3Result": None,
        "status": "unprocessed",
    },
    {
        "id": "mock_job_007",
        "company": "Microsoft",
        "title": "Principal Software Engineer - Azure",
        "source": "linkedin",
        "originalUrl": "",
        "scrapedAt": "2026-07-24T09:00:00Z",
        "passedStage1": True,
        "stage2Score": 72,
        "stage3Result": {
            "atsScore": 0.68, "semanticScore": 0.75, "hardConditionsPassed": False,
            "finalScore": 0.72, "coveredKeywords": ["Azure", "Kubernetes", "Docker", "distributed systems"],
            "missingKeywords": ["C#", "Terraform"],
        },
        "status": "unprocessed",
    },
    {
        "id": "mock_job_008",
        "company": "Uber",
        "title": "Staff Engineer - Marketplace",
        "source": "jobspy",
        "originalUrl": "",
        "scrapedAt": "2026-07-24T08:00:00Z",
        "passedStage1": True,
        "stage2Score": 95,
        "stage3Result": {
            "atsScore": 0.93, "semanticScore": 0.90, "hardConditionsPassed": True,
            "finalScore": 0.92, "coveredKeywords": ["Go", "Kafka", "Redis", "PostgreSQL", "microservices"],
            "missingKeywords": [],
        },
        "status": "replied",
        "linkedApplicationId": "run_008",
    },
    {
        "id": "mock_job_009",
        "company": "Apple",
        "title": "Data Engineer - Siri",
        "source": "linkedin",
        "originalUrl": "",
        "scrapedAt": "2026-07-23T14:00:00Z",
        "passedStage1": True,
        "stage2Score": 60,
        "stage3Result": {
            "atsScore": 0.50, "semanticScore": 0.65, "hardConditionsPassed": True,
            "finalScore": 0.57, "coveredKeywords": ["Python", "PostgreSQL"],
            "missingKeywords": ["Spark", "Airflow", "TensorFlow", "Data modeling"],
        },
        "status": "rejected",
    },
    {
        "id": "mock_job_010",
        "company": "Netflix",
        "title": "Senior Platform Engineer",
        "source": "indeed",
        "originalUrl": "",
        "scrapedAt": "2026-07-23T12:00:00Z",
        "passedStage1": True,
        "stage2Score": 85,
        "stage3Result": {
            "atsScore": 0.80, "semanticScore": 0.88, "hardConditionsPassed": True,
            "finalScore": 0.84, "coveredKeywords": ["Python", "Go", "Docker", "Kubernetes", "AWS", "distributed systems"],
            "missingKeywords": ["Chaos engineering"],
        },
        "status": "unprocessed",
    },
]


def _scoring_query(search: str, category: str) -> str:
    """Stable match query — never use the job's own title (that yields a flat 35%)."""
    if search and search.strip():
        return search.strip()
    from app.modules.job_discovery.categories import CATEGORY_INGEST_QUERIES

    queries = CATEGORY_INGEST_QUERIES.get(category) or []
    if queries:
        # Role phrases + common DA stack so skill_hit_rate can differentiate JDs
        return " ".join(queries[:3]) + " sql python tableau excel r statistics pandas"
    return "data analyst sql python tableau excel r statistics pandas"


def _age_hours_from_iso(age_iso: str | None) -> float | None:
    if not age_iso:
        return None
    try:
        dt = datetime.fromisoformat(str(age_iso).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return max(0.0, (datetime.now(UTC) - dt).total_seconds() / 3600.0)
    except Exception:
        return None


class JobListService:

    def list_jobs(
        self,
        threshold: float = 0,
        sort_by: str = "score",
        top_n: int = 0,
        source: str = "",
        search: str = "",
        category: str = "",
        user_id: str = "",
    ) -> dict:
        from app.modules.job_discovery.categories import classify_job, label_for
        from app.modules.job_discovery.job_index import resume_text_for_user
        from app.modules.job_discovery.scorer import score_job_detailed

        resume_text = resume_text_for_user(user_id or None)
        score_query = _scoring_query(search, category)

        # Prefer real catalog when available
        listings = db.search_job_listings(
            query=search or None,
            status="active",
            limit=200,
            category=category or None,
            source_platform=source if source and source != "all" else None,
        )

        catalog: list[dict[str, Any]] = []
        for item in listings:
            age_iso = display_age_iso(
                scraped_at=item.get("scraped_at"),
                metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else None,
            )
            parsed_score = score_job_detailed(
                {
                    "title": item.get("title") or "",
                    "raw_text": item.get("raw_text") or "",
                    "age_hours": _age_hours_from_iso(age_iso),
                },
                score_query,
                resume_text=resume_text,
            )
            score01 = float(parsed_score["match_score"]) / 100.0
            cat = item.get("category") or "other"
            wm = item.get("work_model") or "unknown"
            work_label = {
                "remote": "Remote",
                "hybrid": "Hybrid",
                "onsite": "On Site",
            }.get(str(wm).lower(), "Remote")
            catalog.append(
                {
                    "id": item["id"],
                    "company": item.get("company") or "Unknown",
                    "title": item.get("title") or "Untitled",
                    "source": item.get("source_platform") or "job_index",
                    "originalUrl": resolve_listing_apply_url(item) or item.get("source_url") or "",
                    "scrapedAt": age_iso,
                    "passedStage1": True,
                    "stage2Score": int(parsed_score["match_score"]),
                    "stage3Result": {
                        "atsScore": float(parsed_score.get("ats_score") or 0),
                        "semanticScore": float(parsed_score.get("skill_score") or 0),
                        "hardConditionsPassed": True,
                        "finalScore": score01,
                        "coveredKeywords": parsed_score.get("matched_skills")
                        or parsed_score.get("jd_skills")
                        or [],
                        "missingKeywords": parsed_score.get("missing_skills") or [],
                        "scoreBreakdown": parsed_score.get("score_breakdown") or {},
                    },
                    "status": "unprocessed",
                    "location": item.get("location") or "N/A",
                    "workModel": work_label,
                    "salary": "N/A",
                    "category": cat,
                    "categoryLabel": (item.get("metadata") or {}).get("category_label")
                    or label_for(cat),
                    "fromDb": True,
                }
            )

        # Mocks only when the real index is empty — never mix high-score fixtures
        # with live rows (that made the UI look ~10 days stale under score sort).
        if not catalog:
            filtered = [_enrich(j) for j in _fresh_mock_jobs()]
            for j in filtered:
                classified = classify_job(title=j.get("title") or "", raw_text=j.get("title") or "")
                j["category"] = classified["category"]
                j["categoryLabel"] = classified["category_label"]

            if category:
                filtered = [j for j in filtered if j.get("category") == category]
            if source and source != "all":
                filtered = [j for j in filtered if j["source"] == source]
            if search:
                s = search.lower()
                filtered = [
                    j
                    for j in filtered
                    if s in j["company"].lower() or s in j["title"].lower()
                ]
            catalog.extend(filtered)

        scored = [
            j
            for j in catalog
            if j.get("passedStage1")
            and j.get("stage3Result")
            and j["stage3Result"].get("hardConditionsPassed")
        ]
        unscored = [j for j in catalog if j not in scored]

        threshold_pct = threshold / 100.0
        scored_above = [
            j for j in scored if j["stage3Result"]["finalScore"] >= threshold_pct
        ]

        if top_n > 0 and len(scored_above) > top_n:
            scored_above.sort(key=lambda j: j["stage3Result"]["finalScore"], reverse=True)
            scored_above = scored_above[:top_n]

        if sort_by == "score":
            scored_above.sort(key=lambda j: j["stage3Result"]["finalScore"], reverse=True)
        else:
            scored_above.sort(key=lambda j: j.get("scrapedAt") or "", reverse=True)

        result = scored_above + unscored
        return {
            "jobs": result,
            "total": len(result),
            "filtered_total": len(scored_above),
            "category": category or None,
        }

    def get_job(self, job_id: str, user_id: str | None = None) -> dict | None:
        for job in MOCK_JOBS:
            if job["id"] == job_id:
                enriched = _enrich(job)
                from app.modules.job_discovery.categories import classify_job

                c = classify_job(title=enriched.get("title") or "", raw_text=enriched.get("title") or "")
                enriched["category"] = c["category"]
                enriched["categoryLabel"] = c["category_label"]
                return enriched
        real = db.get_job(job_id)
        if real:
            parsed = real.get("parsed") or {}
            score = float(real.get("match_score") or 0)
            score01 = score / 100.0 if score > 1 else score
            work = (parsed.get("work_model") or "Remote")
            if isinstance(work, str) and work.islower():
                work = {"remote": "Remote", "hybrid": "Hybrid", "onsite": "On Site"}.get(work, work.title())
            return {
                "id": real["id"],
                "company": real.get("company") or "Unknown",
                "title": real.get("title") or "Untitled",
                "source": real.get("source_platform") or "job_index",
                "originalUrl": resolve_listing_apply_url(real) or real.get("source_url") or "",
                "scrapedAt": real.get("created_at") or "",
                "passedStage1": True,
                "stage2Score": int(score) if score > 1 else int(score * 100),
                "stage3Result": {
                    "atsScore": score01,
                    "semanticScore": score01,
                    "hardConditionsPassed": True,
                    "finalScore": score01,
                    "coveredKeywords": parsed.get("matched_skills")
                    or parsed.get("jd_skills")
                    or (parsed.get("ats_keywords") or [])[:12],
                    "missingKeywords": parsed.get("missing_skills") or [],
                    "scoreBreakdown": parsed.get("score_breakdown") or {},
                },
                "status": "unprocessed",
                "location": real.get("location") or "N/A",
                "workModel": work if isinstance(work, str) else "Remote",
                "salary": "N/A",
                "raw_text": real.get("raw_text") or "",
                "category": parsed.get("category") or "other",
                "categoryLabel": parsed.get("category_label") or parsed.get("category") or "Other",
                "fromDb": True,
            }

        listing = db.get_job_listing(job_id)
        if not listing:
            return None
        from app.modules.job_discovery.categories import label_for
        from app.modules.job_discovery.scorer import score_job_detailed

        from app.modules.job_discovery.job_index import resume_text_for_user

        cat_for_score = listing.get("category") or "data_analysis"
        age_iso = display_age_iso(
            scraped_at=listing.get("scraped_at"),
            metadata=listing.get("metadata") if isinstance(listing.get("metadata"), dict) else None,
        )
        detail = score_job_detailed(
            {
                "title": listing.get("title") or "",
                "raw_text": listing.get("raw_text") or "",
                "age_hours": _age_hours_from_iso(age_iso),
            },
            _scoring_query("", cat_for_score),
            resume_text=resume_text_for_user(user_id),
        )
        score01 = float(detail["match_score"]) / 100.0
        wm = listing.get("work_model") or "unknown"
        work_label = {"remote": "Remote", "hybrid": "Hybrid", "onsite": "On Site"}.get(
            str(wm).lower(), "Remote"
        )
        cat = listing.get("category") or "other"
        return {
            "id": listing["id"],
            "company": listing.get("company") or "Unknown",
            "title": listing.get("title") or "Untitled",
            "source": listing.get("source_platform") or "job_index",
            "originalUrl": resolve_listing_apply_url(listing) or listing.get("source_url") or "",
            "scrapedAt": age_iso,
            "passedStage1": True,
            "stage2Score": int(detail["match_score"]),
            "stage3Result": {
                "atsScore": float(detail.get("ats_score") or 0),
                "semanticScore": float(detail.get("skill_score") or 0),
                "hardConditionsPassed": True,
                "finalScore": score01,
                "coveredKeywords": detail.get("matched_skills") or detail.get("jd_skills") or [],
                "missingKeywords": detail.get("missing_skills") or [],
                "scoreBreakdown": detail.get("score_breakdown") or {},
            },
            "status": "unprocessed",
            "location": listing.get("location") or "N/A",
            "workModel": work_label,
            "salary": "N/A",
            "raw_text": listing.get("raw_text") or "",
            "category": cat,
            "categoryLabel": (listing.get("metadata") or {}).get("category_label") or label_for(cat),
            "fromDb": True,
        }

    def get_summary(self, job_id: str, user_id: str | None = None) -> dict | None:
        job = self.get_job(job_id, user_id=user_id)
        if not job:
            return None
        s3 = dict(job.get("stage3Result") or {})
        # Optional live rescore against the signed-in user's resume inventory
        if user_id:
            try:
                from app.modules.job_discovery.job_index import resume_text_for_user
                from app.modules.job_discovery.scorer import score_job_detailed

                listing = db.get_job_listing(job_id) or {}
                cat = listing.get("category") or job.get("category") or "data_analysis"
                detail = score_job_detailed(
                    {
                        "title": job.get("title") or "",
                        "raw_text": listing.get("raw_text") or job.get("raw_text") or "",
                    },
                    _scoring_query("", cat),
                    resume_text=resume_text_for_user(user_id),
                )
                s3 = {
                    "atsScore": float(detail.get("ats_score") or 0),
                    "semanticScore": float(detail.get("skill_score") or 0),
                    "hardConditionsPassed": True,
                    "finalScore": float(detail["match_score"]) / 100.0,
                    "coveredKeywords": detail.get("matched_skills") or detail.get("jd_skills") or [],
                    "missingKeywords": detail.get("missing_skills") or [],
                    "scoreBreakdown": detail.get("score_breakdown") or {},
                }
            except Exception:
                pass
        return {
            "id": job["id"],
            "title": job["title"],
            "company": job["company"],
            "source": job["source"],
            "originalUrl": job.get("originalUrl", ""),
            "location": job.get("location", "N/A"),
            "workModel": job.get("workModel", "Remote"),
            "salary": job.get("salary", "N/A"),
            "scrapedAt": job.get("scrapedAt", ""),
            "atsScore": s3.get("atsScore", 0),
            "semanticScore": s3.get("semanticScore", 0),
            "finalScore": s3.get("finalScore", 0),
            "coveredKeywords": s3.get("coveredKeywords", []),
            "missingKeywords": s3.get("missingKeywords", []),
            "scoreBreakdown": s3.get("scoreBreakdown") or {},
            "hasHardConditionIssues": not s3.get("hardConditionsPassed", True),
            "status": job["status"],
            "scoredForUser": bool(user_id),
        }

    def trigger_scoring(self, job_id: str) -> dict | None:
        for job in MOCK_JOBS:
            if job["id"] == job_id:
                s3 = job.get("stage3Result") or {}
                return {"stage3Result": s3}
        job = self.get_job(job_id)
        if not job:
            return None
        return {"stage3Result": job.get("stage3Result") or {}}

    def to_resume_workspace(self, job_id: str, user_id: str) -> dict | None:
        from app.modules.job_discovery.quality import jd_plaintext

        for job in MOCK_JOBS:
            if job["id"] == job_id:
                jd_text = (
                    f"{job['title']} at {job['company']}\n\n"
                    f"Source: {job['source']}\n"
                    f"URL: {job.get('originalUrl', '')}\n\n"
                    f"Requirements:\n"
                    f"- Experience aligned with {job['title']}\n"
                    f"- Strong analytical and communication skills\n\n"
                    f"Preferred:\n"
                    f"- Tools and domain keywords matching this role\n\n"
                    f"(Demo listing — paste a real JD for best tailoring.)"
                )
                session = db.create_jd_session(
                    user_id=user_id,
                    job_id=job_id,
                    jd_text=jd_text,
                )
                return {
                    "sessionId": session["id"],
                    "jobId": job_id,
                    "session_id": session["id"],
                    "job_id": job_id,
                    "jd_text": jd_text,
                    "title": job.get("title"),
                    "company": job.get("company"),
                }
        real = db.get_job(job_id)
        if real:
            jd_text = jd_plaintext((real.get("raw_text") or "").strip())
            if not jd_text:
                jd_text = (
                    f"{real.get('title')} at {real.get('company')}\n"
                    f"Location: {real.get('location') or 'N/A'}\n\n"
                    f"Requirements:\n- See original posting for full details.\n"
                )
            session = db.create_jd_session(
                user_id=user_id,
                job_id=job_id,
                jd_text=jd_text,
            )
            return {
                "sessionId": session["id"],
                "jobId": job_id,
                "session_id": session["id"],
                "job_id": job_id,
                "jd_text": jd_text,
                "title": real.get("title"),
                "company": real.get("company"),
                "from_db": True,
            }
        listing = db.get_job_listing(job_id)
        if not listing:
            return None
        jd_text = jd_plaintext((listing.get("raw_text") or "").strip())
        title = listing.get("title") or "Untitled"
        company = listing.get("company") or "Unknown"
        location = listing.get("location") or ""
        url = listing.get("source_url") or ""
        if not jd_text:
            jd_text = (
                f"{title} at {company}\n"
                f"Location: {location or 'N/A'}\n"
                f"Source: {listing.get('source_platform') or ''}\n"
                f"URL: {url}\n\n"
                f"About the role:\n"
                f"This listing was ingested without a full description body. "
                f"Open the original posting or paste the full JD for accurate tailoring.\n\n"
                f"Requirements:\n"
                f"- Skills and experience matching {title}\n"
            )
        elif title.lower() not in jd_text[:200].lower():
            jd_text = f"{title} at {company}\nLocation: {location}\nURL: {url}\n\n{jd_text}"
        session = db.create_jd_session(
            user_id=user_id,
            job_id=job_id,
            jd_text=jd_text,
        )
        meta = listing.get("metadata") if isinstance(listing.get("metadata"), dict) else {}
        jobright_url = (
            str(meta.get("jobright_url") or meta.get("page_url") or "").strip()
            or (url if "jobright.ai" in (url or "").lower() else "")
            or None
        )
        return {
            "sessionId": session["id"],
            "jobId": job_id,
            "session_id": session["id"],
            "job_id": job_id,
            "jd_text": jd_text,
            "title": title,
            "company": company,
            "from_db": True,
            "from_listing": True,
            "source_url": url or None,
            "jobright_url": jobright_url,
            "source_platform": listing.get("source_platform"),
        }

    def get_available_sources(self) -> list[str]:
        sources = set()
        for job in MOCK_JOBS:
            sources.add(job["source"])
        for row in db.search_job_listings(status="active", limit=200):
            if row.get("source_platform"):
                sources.add(row["source_platform"])
        return sorted(sources)


job_list_service = JobListService()
