"""Job matching score utilities (JR-3: JD body + skill hit + breakdown)."""

from __future__ import annotations

import re
from typing import Any


# Domain skills we care about for Data Analyst track (extend later).
SKILL_LEXICON = {
    "sql",
    "python",
    "r",
    "tableau",
    "powerbi",
    "power-bi",
    "looker",
    "excel",
    "spark",
    "hadoop",
    "snowflake",
    "redshift",
    "bigquery",
    "dbt",
    "airflow",
    "pandas",
    "numpy",
    "statistics",
    "etl",
    "dashboard",
    "dashboards",
    "visualization",
    "a/b",
    "experimentation",
    "machine",
    "learning",
    "sklearn",
    "tensorflow",
    "pytorch",
    "java",
    "scala",
    "sas",
    "spss",
    "alteryx",
    "qlik",
    "mongodb",
    "postgresql",
    "mysql",
    "kafka",
    "aws",
    "azure",
    "gcp",
    "databricks",
}


def tokenize(text: str) -> set[str]:
    stop = {
        "and", "the", "for", "with", "you", "our", "job", "role", "team", "this", "that",
        "are", "not", "have", "from", "your", "will", "all", "can", "has", "its", "also",
        "been", "than", "what", "who", "about", "their", "they", "was", "were", "one",
        "being", "very", "just", "some", "each", "which", "requirements", "responsibilities",
        "company", "location", "source", "http", "https", "www",
    }
    return {
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9+#./-]{1,}", text.lower())
        if token not in stop and len(token) >= 2
    }


def _jd_blob(parsed: dict) -> str:
    parts: list[str] = [
        str(parsed.get("title") or ""),
        str(parsed.get("raw_text") or ""),
        str(parsed.get("description") or ""),
        " ".join(str(x) for x in (parsed.get("required_skills") or [])),
        " ".join(str(x) for x in (parsed.get("preferred_skills") or [])),
        " ".join(str(x) for x in (parsed.get("ats_keywords") or [])),
        " ".join(str(x) for x in (parsed.get("key_responsibilities") or [])),
    ]
    return " ".join(parts)


def extract_skills(text: str) -> set[str]:
    tokens = tokenize(text)
    # normalize power bi variants
    if "power" in tokens and "bi" in tokens:
        tokens.add("powerbi")
    found = {s for s in SKILL_LEXICON if s in tokens}
    # multiword-ish: power-bi already in lexicon via token pattern
    return found


def score_job_detailed(parsed: dict, query: str, resume_text: str = "") -> dict[str, Any]:
    jd_text = _jd_blob(parsed)
    jd_tokens = tokenize(jd_text)
    query_tokens = tokenize(query)
    resume_tokens = tokenize(resume_text)

    jd_skills = extract_skills(jd_text)
    resume_skills = extract_skills(resume_text) if resume_text else set()
    query_skills = extract_skills(query)

    # Explicit ATS-style keywords from structured JD fields (not title noise).
    ats_terms = {
        t
        for t in tokenize(
            " ".join(
                [
                    " ".join(str(x) for x in (parsed.get("required_skills") or [])),
                    " ".join(str(x) for x in (parsed.get("preferred_skills") or [])),
                    " ".join(str(x) for x in (parsed.get("ats_keywords") or [])),
                ]
            )
        )
    }
    # If JD has no structured skills, fall back to lexicon hits in body.
    if not ats_terms:
        ats_terms = jd_skills
    profile_terms = resume_skills | (extract_skills(resume_text) if resume_text else set()) | query_skills
    if resume_tokens:
        # Prefer resume lexicon + frequent DA stack tokens present in resume
        profile_terms = resume_skills | {t for t in resume_tokens if t in SKILL_LEXICON}
    ats_coverage = (
        len(ats_terms & profile_terms) / max(1, len(ats_terms)) if ats_terms else 0.0
    )

    # Guard: using the job title as query against a blob that includes that title
    # always yields query_overlap=1.0 → flat 35% when resume/skills are empty.
    title_tokens = tokenize(str(parsed.get("title") or ""))
    if query_tokens and title_tokens and query_tokens <= title_tokens:
        query_overlap = 0.0
    else:
        query_overlap = len(query_tokens & jd_tokens) / max(1, len(query_tokens))
    if resume_tokens:
        overlap_count = len(resume_tokens & jd_tokens)
        resume_overlap = overlap_count / max(1, min(len(resume_tokens), max(len(jd_tokens), 1)))
    else:
        resume_overlap = 0.0

    # Skill hit must be grounded in the JD — never score query∩resume when JD has no skills
    # (that previously inflated thin/labeling posts to skill_hit_rate=1.0).
    if jd_skills and resume_skills:
        skill_hit_rate = len(resume_skills & jd_skills) / max(1, len(jd_skills))
    elif jd_skills and not resume_skills:
        skill_hit_rate = len(query_skills & jd_skills) / max(1, len(jd_skills))
    else:
        skill_hit_rate = 0.0

    # Cap ATS coverage when the "keyword list" is just a tiny lexicon fallback on a thin body
    body_len = len(str(parsed.get("raw_text") or parsed.get("description") or ""))
    structured_ats = bool(
        (parsed.get("required_skills") or [])
        or (parsed.get("preferred_skills") or [])
        or (parsed.get("ats_keywords") or [])
    )
    if not structured_ats and body_len < 500 and len(ats_terms) <= 2:
        ats_coverage *= 0.4
    if not structured_ats and body_len < 300:
        ats_coverage = 0.0

    # v2 weights: query 25 + resume token 20 + skill hit 35 + ATS keyword 20
    raw = 100 * (
        0.25 * query_overlap
        + 0.20 * resume_overlap
        + 0.35 * skill_hit_rate
        + 0.20 * ats_coverage
    )
    # Soft penalty: title looks unrelated to analytics/data when query is DA-oriented
    q_l = query.lower()
    title_l = str(parsed.get("title") or "").lower()
    if any(k in q_l for k in ("data", "analyst", "analytics", "bi")):
        if not any(k in title_l for k in ("data", "analyst", "analytics", "bi", "sql", "intel")):
            raw *= 0.85

    # Anti-inflation: thin / labeling / microtask JDs should not score like senior DA roles
    if body_len and body_len < 400:
        raw *= 0.7
    if any(
        k in title_l
        for k in ("labeling", "labelling", "data entry", "clickworker", "survey", "microtask")
    ):
        raw *= 0.55
    if len(jd_skills) <= 1 and body_len < 800:
        raw *= 0.8
    if len(jd_skills) == 0 and body_len < 600:
        raw *= 0.75

    # Soft stale penalty when caller passes age_hours (posted age)
    age_hours = parsed.get("age_hours")
    try:
        age_h = float(age_hours) if age_hours is not None else None
    except (TypeError, ValueError):
        age_h = None
    if age_h is not None:
        if age_h > 24 * 14:
            raw *= 0.85
        elif age_h > 24 * 7:
            raw *= 0.92

    score = round(min(100.0, max(raw, 0.0)), 1)

    matched_skills = sorted(resume_skills & jd_skills) if resume_skills else sorted(query_skills & jd_skills)
    missing_skills = sorted(jd_skills - (resume_skills or query_skills))

    return {
        "match_score": score,
        "score_breakdown": {
            "query_overlap": round(query_overlap, 3),
            "resume_overlap": round(resume_overlap, 3),
            "skill_hit_rate": round(skill_hit_rate, 3),
            "ats_coverage": round(ats_coverage, 3),
            "weights": {"query": 0.25, "resume": 0.20, "skills": 0.35, "ats": 0.20},
        },
        "matched_skills": matched_skills,
        "missing_skills": missing_skills[:20],
        "jd_skills": sorted(jd_skills),
        # Honest component scores for UI (0–1)
        "ats_score": round(ats_coverage, 4),
        "skill_score": round(skill_hit_rate, 4),
    }


def score_job(parsed: dict, query: str, resume_text: str = "") -> float:
    return float(score_job_detailed(parsed, query, resume_text=resume_text)["match_score"])
