from typing import Any
from uuid import uuid4
from datetime import UTC, datetime
from app import db


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


MOCK_JOBS: list[dict[str, Any]] = [
    {
        "id": "mock_job_001",
        "company": "Google",
        "title": "Senior Software Engineer, Infrastructure",
        "source": "linkedin",
        "originalUrl": "https://linkedin.com/jobs/view/1",
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
        "originalUrl": "https://linkedin.com/jobs/view/2",
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
        "originalUrl": "https://amazon.com/jobs/3",
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
        "originalUrl": "https://stripe.com/jobs/4",
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
        "originalUrl": "https://indeed.com/view/5",
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
        "originalUrl": "https://linkedin.com/jobs/view/6",
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
        "originalUrl": "https://linkedin.com/jobs/view/7",
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
        "originalUrl": "https://uber.com/jobs/8",
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
        "originalUrl": "https://apple.com/jobs/9",
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
        "originalUrl": "https://netflix.com/jobs/10",
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


class JobListService:

    def list_jobs(self, threshold: float = 0, sort_by: str = "score",
                  top_n: int = 0, source: str = "", search: str = "") -> dict:
        filtered = [_enrich(j) for j in MOCK_JOBS]

        # Source filter
        if source and source != "all":
            filtered = [j for j in filtered if j["source"] == source]

        # Search filter (company or title)
        if search:
            s = search.lower()
            filtered = [j for j in filtered if s in j["company"].lower() or s in j["title"].lower()]

        # Only show jobs that passed stage 1 and have a score
        scored = [j for j in filtered if j["passedStage1"] and j.get("stage3Result") and j["stage3Result"]["hardConditionsPassed"]]
        unscored = [j for j in filtered if j not in scored]

        # Apply threshold AFTER stage1/stage3 filter but BEFORE topN (spec Section 3)
        threshold_pct = threshold / 100.0
        scored_above = [j for j in scored if j["stage3Result"]["finalScore"] >= threshold_pct]

        # Apply Top10: take top N from the threshold-filtered result (spec: not global topN)
        if top_n > 0 and len(scored_above) > top_n:
            scored_above.sort(key=lambda j: j["stage3Result"]["finalScore"], reverse=True)
            scored_above = scored_above[:top_n]

        # Sort
        if sort_by == "score":
            scored_above.sort(key=lambda j: j["stage3Result"]["finalScore"], reverse=True)
        else:
            scored_above.sort(key=lambda j: j["scrapedAt"], reverse=True)

        # Include unscored (not matching threshold) at the bottom
        result = scored_above + unscored

        return {
            "jobs": result,
            "total": len(result),
            "filtered_total": len(scored_above),
        }

    def get_job(self, job_id: str) -> dict | None:
        for job in MOCK_JOBS:
            if job["id"] == job_id:
                return _enrich(job)
        return None

    def get_summary(self, job_id: str) -> dict | None:
        job = self.get_job(job_id)
        if not job:
            return None
        s3 = job.get("stage3Result") or {}
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
            "hasHardConditionIssues": not s3.get("hardConditionsPassed", True),
            "status": job["status"],
        }

    def trigger_scoring(self, job_id: str) -> dict | None:
        for job in MOCK_JOBS:
            if job["id"] == job_id:
                s3 = job.get("stage3Result") or {}
                return {"stage3Result": s3}
        return None

    def to_resume_workspace(self, job_id: str, user_id: str) -> dict | None:
        for job in MOCK_JOBS:
            if job["id"] == job_id:
                session = db.create_jd_session(
                    user_id=user_id,
                    job_id=job_id,
                    jd_text=f"{job['title']} at {job['company']}\n\n"
                            f"Source: {job['source']}\n"
                            f"URL: {job.get('originalUrl', '')}\n\n"
                            f"This is a mock job description for {job['title']} at {job['company']}."
                )
                return {"sessionId": session["id"], "jobId": job_id}
        return None

    def get_available_sources(self) -> list[str]:
        sources = set()
        for job in MOCK_JOBS:
            sources.add(job["source"])
        return sorted(sources)


job_list_service = JobListService()
