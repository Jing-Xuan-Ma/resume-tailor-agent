"""Three-stage job scoring pipeline.

Stage 1: Rule-based filtering (zero LLM cost)
Stage 2: Cheap LLM preliminary scoring
Stage 3: Deep scoring with full ATS + semantic + hard conditions
"""

import logging
import re
from typing import Any

from app import db
from app.config import settings
from app.core.llm_client import get_chat_openai

logger = logging.getLogger(__name__)

TITLE_BLACKLIST_PATTERNS = [
    r"(?i)^(senior|staff|principal|lead|sr\.?).+",
    r"(?i)^(director|vp|vice president|head of|chief|manager)\b.+",
    r"(?i)^(intern|internship)$",
    r"(?i).+\bintern(ship)?$",
]

STOP_WORDS = {
    "and", "the", "for", "with", "you", "our", "job", "role", "team", "this",
    "that", "are", "not", "have", "from", "your", "will", "all", "can", "has",
    "its", "also", "been", "than", "what", "who", "about", "their", "they",
    "was", "were", "one", "being", "very", "just", "some", "each", "which",
}


def stage1_filter(job: dict) -> bool:
    title = (job.get("title") or "").strip()
    if not title:
        return False
    for pattern in TITLE_BLACKLIST_PATTERNS:
        if re.match(pattern, title):
            return False
    return True


def _stage2_prompt(job: dict, resume_text: str) -> str:
    return (
        f"Job Title: {job.get('title', '')}\n"
        f"Company: {job.get('company', '')}\n"
        f"JD excerpt: {(job.get('raw_text') or '')[:1500]}\n\n"
        f"Candidate resume (excerpt):\n{resume_text[:1000]}\n\n"
        "Rate relevance 0-100. Return ONLY a number."
    )


def stage2_score(job: dict, resume_text: str) -> int | None:
    prompt = _stage2_prompt(job, resume_text)
    try:
        llm = get_chat_openai(
            model=settings.DEFAULT_PARSER_MODEL,
            temperature=0.1,
            max_tokens=10,
        )
        from langchain_core.messages import HumanMessage
        response = llm.invoke([HumanMessage(content=prompt)])
        m = re.search(r"\d+", response.content.strip())
        if m:
            return max(0, min(100, int(m.group(0))))
    except Exception as e:
        logger.warning("stage2 LLM failed for job %s: %s", job.get("id"), e)
    return None


def stage3_score(
    job: dict,
    resume_text: str,
    resume_parsed: dict | None = None,
) -> dict:
    parsed = job.get("parsed") or {}
    rl = resume_text.lower()

    req = [s.lower() for s in parsed.get("required_skills") or []]
    pref = [s.lower() for s in parsed.get("preferred_skills") or []]
    ats_kw = [s.lower() for s in parsed.get("ats_keywords") or []]

    req_hits = sum(1 for s in req if s in rl)
    pref_hits = sum(1 for s in pref if s in rl)
    kw_hits = sum(1 for s in ats_kw if s in rl)

    req_t = len(req) or 1
    pref_t = len(pref) or 1
    kw_t = len(ats_kw) or 1

    ats_score = 0.5 * (req_hits / req_t) + 0.25 * (pref_hits / pref_t) + 0.25 * (kw_hits / kw_t)
    ats_score = min(1.0, ats_score)

    rw = set(re.findall(r"[a-zA-Z][a-zA-Z0-9+#.\-]{2,}", rl)) - STOP_WORDS
    jw = set(re.findall(r"[a-zA-Z][a-zA-Z0-9+#.\-]{2,}", (job.get("raw_text") or "").lower())) - STOP_WORDS
    overlap = len(rw & jw)
    semantic_score = overlap / max(1, min(len(rw), max(len(jw), 1)))
    semantic_score = min(1.0, semantic_score)

    hard_passed = True
    issues: list[str] = []
    jd_years = parsed.get("years_experience")
    if jd_years and resume_parsed:
        # Check if resume has a total_years_experience or estimate from experiences
        ry = (resume_parsed.get("total_years_experience") or
              _estimate_years(resume_parsed))
        if ry is not None and ry < jd_years:
            hard_passed = False
            issues.append(f"Requires {jd_years}+ years, resume ~{ry}")

    alpha, beta, gamma = 0.5, 0.3, 0.2
    hc = 0.0 if not hard_passed else 1.0
    final = alpha * ats_score + beta * semantic_score + gamma * hc
    if not hard_passed:
        final *= 0.5

    all_skills = parsed.get("required_skills", []) + parsed.get("preferred_skills", []) + parsed.get("ats_keywords", [])
    covered = [s for s in all_skills if s.lower() in rl]
    missing = [s for s in all_skills if s.lower() not in rl]

    return {
        "atsScore": round(ats_score, 4),
        "semanticScore": round(semantic_score, 4),
        "hardConditionsPassed": hard_passed,
        "hardConditionIssues": issues,
        "finalScore": round(final, 4),
        "coveredKeywords": covered[:20],
        "missingKeywords": missing[:20],
    }


def _estimate_years(resume_parsed: dict) -> int | None:
    exps = resume_parsed.get("experiences") or []
    if not exps:
        return None
    total = 0
    for e in exps:
        d = e.get("duration_months") or 0
        if d:
            total += d
    return max(1, round(total / 12.0)) if total else None


def score_all_jobs(
    jobs: list[dict],
    resume_text: str,
    resume_parsed: dict | None = None,
    skip_stage2: bool = False,
) -> list[dict]:
    """Run all three stages on a list of jobs. Returns enriched job dicts."""
    results = []
    for job in jobs:
        job = dict(job)
        job["_passed_stage1"] = stage1_filter(job)
        job["_stage2_score"] = None
        job["_stage3_result"] = None

        if not job["_passed_stage1"]:
            results.append(job)
            continue

        if not skip_stage2:
            s2 = stage2_score(job, resume_text)
            job["_stage2_score"] = s2
            if s2 is not None and s2 < 30:
                results.append(job)
                continue

        s3 = stage3_score(job, resume_text, resume_parsed)
        job["_stage3_result"] = s3
        results.append(job)

    return results
