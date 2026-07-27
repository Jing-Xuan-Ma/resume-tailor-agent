from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app import db
from app.modules.growth_advisor.schemas import GrowthAnalyzeRequest, GrowthPlanListResponse, GrowthPlanResponse


router = APIRouter()


def _tokens(value: object) -> set[str]:
    if isinstance(value, list):
        text = " ".join(str(item) for item in value)
    else:
        text = str(value or "")
    cleaned = "".join(ch.lower() if ch.isalnum() or ch in {"+", "#"} else " " for ch in text)
    return {part for part in cleaned.split() if len(part) > 1}


def _resume_skills(resume: dict | None) -> set[str]:
    if not resume:
        return set()
    parsed = resume.get("parsed") or {}
    skills = set()
    skills |= _tokens(parsed.get("skills"))
    skills |= _tokens(parsed.get("skills_certifications"))
    skills |= _tokens(resume.get("raw_text"))
    return skills


def _job_requirements(job: dict | None, target_role: str) -> list[str]:
    if job:
        parsed = job.get("parsed") or {}
        candidates = []
        for key in ("required_skills", "preferred_skills", "keywords", "responsibilities"):
            value = parsed.get(key)
            if isinstance(value, list):
                candidates.extend(str(item) for item in value)
            elif value:
                candidates.append(str(value))
        if candidates:
            return candidates[:12]
    defaults = {
        "software engineer": ["python", "system design", "api development", "testing", "cloud", "databases"],
        "data analyst": ["sql", "python", "dashboards", "statistics", "stakeholder communication", "data cleaning"],
        "product manager": ["roadmaps", "user research", "metrics", "prioritization", "cross-functional leadership"],
    }
    key = target_role.lower()
    for role, requirements in defaults.items():
        if role in key:
            return requirements
    return [target_role, "communication", "project execution", "domain knowledge", "portfolio evidence"]


@router.post("/analyze", response_model=GrowthPlanResponse)
async def analyze_growth(request: GrowthAnalyzeRequest):
    job = None
    if request.job_id:
        job = db.get_job(str(request.job_id), user_id=str(request.user_id))
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
    target_role = request.target_role or (job or {}).get("title") or "target role"
    resume = db.get_latest_resume(str(request.user_id))
    known = _resume_skills(resume)
    requirements = _job_requirements(job, target_role)

    gaps = []
    for requirement in requirements:
        req_tokens = _tokens(requirement)
        overlap = known & req_tokens
        if not overlap:
            gaps.append({"skill": requirement, "severity": "high", "evidence": "not found in latest resume"})
        elif len(overlap) < max(1, len(req_tokens) // 2):
            gaps.append({"skill": requirement, "severity": "medium", "evidence": f"partial overlap: {', '.join(sorted(overlap))}"})

    if not gaps:
        gaps.append({"skill": "role-specific proof", "severity": "low", "evidence": "resume matches core keywords; add stronger project evidence"})

    recommendations = [
        {
            "title": f"Build evidence for {gap['skill']}",
            "action": "Create a small project, work sample, or resume bullet that demonstrates this requirement with measurable output.",
            "priority": gap["severity"],
        }
        for gap in gaps[:6]
    ]
    roadmap = [
        {"week": 1, "focus": "Close highest-severity skill gap", "deliverable": recommendations[0]["title"]},
        {"week": 2, "focus": "Package evidence", "deliverable": "Add quantified resume bullet and portfolio note"},
        {"week": 3, "focus": "Market test", "deliverable": "Apply to 5 aligned roles and track callbacks"},
        {"week": 4, "focus": "Iterate", "deliverable": "Refine resume and outreach based on response data"},
    ]
    plan_id = db.save_growth_plan(
        user_id=str(request.user_id),
        job_id=str(request.job_id) if request.job_id else None,
        target_role=target_role,
        gaps=gaps,
        recommendations=recommendations,
        roadmap=roadmap,
    )
    return db.list_growth_plans(str(request.user_id), limit=1)[0] | {"id": plan_id}


@router.get("", response_model=GrowthPlanListResponse)
async def list_growth_plans(user_id: UUID = Query(...), limit: int = Query(20, ge=1, le=100)):
    return GrowthPlanListResponse(plans=db.list_growth_plans(str(user_id), limit=limit))
