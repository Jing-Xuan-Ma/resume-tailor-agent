"""Parse Jobright dataSource into browse-friendly JD sections."""

from __future__ import annotations

from typing import Any


def _as_str_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
            elif isinstance(item, dict):
                text = item.get("skill") or item.get("text") or item.get("displayName")
                if text and str(text).strip():
                    out.append(str(text).strip())
        return out
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def parse_jd_sections(data_source: dict[str, Any]) -> dict[str, Any]:
    """Extract Responsibilities / Qualification / Required / Preferred."""
    job = data_source.get("jobResult") or {}
    company = data_source.get("companyResult") or {}
    quals = job.get("qualifications") or {}
    if not isinstance(quals, dict):
        quals = {}

    responsibilities = _as_str_list(job.get("coreResponsibilities"))
    # Qualification tags shown on Jobright "Qualification" row
    qualification = _as_str_list(job.get("jdCoreSkills"))
    if not qualification:
        qualification = _as_str_list(job.get("skillMatchingScores"))
    required = _as_str_list(quals.get("mustHave"))
    preferred = _as_str_list(quals.get("preferredHave"))
    # fallbacks if structured quals missing
    if not required and not preferred:
        skills = _as_str_list(job.get("skillSummaries"))
        if skills:
            required = skills

    company_name = (
        str(company.get("companyName") or "").strip()
        or str((company.get("company") or {}).get("name") or "").strip()
        or str(job.get("companyName") or "").strip()
        or None
    )

    return {
        "title": str(job.get("jobTitle") or "").strip() or None,
        "company": company_name,
        "location": str(job.get("jobLocation") or "").strip() or None,
        "work_model": str(job.get("workModel") or "").strip() or None,
        "employment_type": str(job.get("employmentType") or "").strip() or None,
        "summary": str(job.get("jobSummary") or "").strip() or None,
        "responsibilities": responsibilities,
        "qualification": qualification,
        "required": required,
        "preferred": preferred,
    }
