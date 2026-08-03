"""Resume quality gate aligned with RESUME_CONSTITUTION.md."""

from __future__ import annotations

import re
from typing import Any

SECTION_ORDER = [
    "education",
    "experiences",
    "projects",
    "competitions",
    "skills_certifications",
]

ACTION_VERBS = (
    "built", "designed", "engineered", "led", "delivered", "applied", "conducted",
    "optimized", "prepared", "used", "faced", "given", "to ", "analyzed", "extended",
    "collected", "created", "developed", "implemented", "reduced",
)


def _bullets(entry: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for b in entry.get("bullets") or []:
        if isinstance(b, dict):
            out.append(b)
        else:
            out.append({"text": str(b)})
    return out


def project_for_jd(master: dict[str, Any], jd_text: str) -> dict[str, Any]:
    """Show/hide experiences & projects by JD keyword overlap; reorder skills."""
    jd = (jd_text or "").lower()
    projected = {
        "candidate_name": master.get("candidate_name"),
        "contact_line": master.get("contact_line"),
        "summary": master.get("summary"),
        "education": list(master.get("education") or []),
        "experiences": [],
        "projects": [],
        "competitions": list(master.get("competitions") or []),
        "skills_certifications": master.get("skills_certifications"),
        "hidden_entries": [],
    }

    def score_entry(entry: dict[str, Any]) -> float:
        blob = " ".join(
            [
                str(entry.get("title") or ""),
                str(entry.get("company") or ""),
                str(entry.get("name") or ""),
                " ".join(str(t) for t in (entry.get("tools") or [])),
                " ".join(str(b.get("text") or "") for b in _bullets(entry)),
            ]
        ).lower()
        tokens = set(re.findall(r"[a-zA-Z+]{3,}", jd))
        if not tokens:
            return 0.0
        hits = sum(1 for t in tokens if t in blob)
        return hits / max(len(tokens), 1)

    scored_exp = sorted(
        ((score_entry(e), e) for e in (master.get("experiences") or [])),
        key=lambda x: x[0],
        reverse=True,
    )
    scored_proj = sorted(
        ((score_entry(e), e) for e in (master.get("projects") or [])),
        key=lambda x: x[0],
        reverse=True,
    )

    # Budget: up to 2 experiences + 2 projects
    for sc, e in scored_exp[:2]:
        projected["experiences"].append(e)
    for sc, e in scored_exp[2:]:
        projected["hidden_entries"].append(
            {"kind": "experience", "key": f"{e.get('company')}|{e.get('title')}", "score": sc}
        )

    for sc, e in scored_proj[:2]:
        projected["projects"].append(e)
    for sc, e in scored_proj[2:]:
        projected["hidden_entries"].append(
            {"kind": "project", "key": str(e.get("name")), "score": sc}
        )

    # Hide competitions when JD is analytics-heavy and space tight
    if projected["competitions"] and ("analyst" in jd or "sql" in jd or "tableau" in jd):
        for c in projected["competitions"]:
            projected["hidden_entries"].append(
                {"kind": "competition", "key": str(c.get("name") or c), "score": 0.0}
            )
        projected["competitions"] = []

    skills_raw = str(master.get("skills_certifications") or "")
    parts = [p.strip() for p in skills_raw.replace(";", ",").split(",") if p.strip()]
    hit, rest = [], []
    for p in parts:
        if p.lower() in jd:
            hit.append(p)
        else:
            rest.append(p)
    ordered = hit + rest
    projected["skills_certifications"] = ", ".join(ordered[:15] + ([] if len(ordered) <= 15 else rest[:0]))
    # Keep at most 15 skills in projection string for one-page
    projected["skills_certifications"] = ", ".join((hit + rest)[:15])

    # Summary boost using hit skills
    if hit:
        base = str(master.get("summary") or "")
        projected["summary"] = f"Data Analyst targeting roles emphasizing {', '.join(hit[:4])}. {base}"
        if len(projected["summary"]) > 420:
            projected["summary"] = projected["summary"][:417].rstrip() + "..."

    return projected


def run_quality_gate(resume: dict[str, Any], jd_text: str = "") -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if not resume.get("candidate_name"):
        errors.append("missing candidate_name")
    if not resume.get("contact_line") or "|" not in str(resume.get("contact_line")):
        errors.append("contact_line must use | separators")
    summary = str(resume.get("summary") or "")
    if not summary:
        errors.append("missing summary")
    if summary.count("\n") > 3:
        warnings.append("summary may exceed 3 visual lines")
    if len(summary) > 500:
        errors.append("summary too long for one-page budget")

    # Section presence / no unknown top-level fabrication markers
    if not resume.get("education"):
        errors.append("education required")
    if not resume.get("experiences") and not resume.get("projects"):
        errors.append("need at least one experience or project")

    # Bullet checks
    bullet_count = 0
    for section in ("experiences", "projects"):
        for entry in resume.get(section) or []:
            if not isinstance(entry, dict):
                continue
            bullets = _bullets(entry)
            if section in ("experiences", "projects") and bullets and not (2 <= len(bullets) <= 3):
                warnings.append(f"{section} entry should have 2-3 bullets, got {len(bullets)}")
            for b in bullets:
                bullet_count += 1
                text = str(b.get("text") or "").strip()
                if not text:
                    errors.append("empty bullet")
                    continue
                low = text.lower()
                if not any(low.startswith(v) for v in ACTION_VERBS):
                    warnings.append(f"bullet may lack strong opening: {text[:48]}...")
                if not b.get("evidence_from"):
                    errors.append("bullet missing evidence_from")
                # Fabrication heuristic: percentages not in original_text
                original = str(b.get("original_text") or "")
                for pct in re.findall(r"\d+(?:\.\d+)?%", text):
                    if pct not in original and original:
                        errors.append(f"fabricated metric {pct}")
                for num in re.findall(r"\b\d{2,}(?:,\d{3})*\b", text):
                    if original and num not in original and num not in original.replace(",", ""):
                        # allow if original has same digits without commas
                        digits = num.replace(",", "")
                        if digits not in original.replace(",", ""):
                            warnings.append(f"number {num} not in original_text")

    skills = str(resume.get("skills_certifications") or "")
    if not skills:
        errors.append("skills_certifications required")
    if "\n•" in skills or skills.strip().startswith("•"):
        errors.append("skills must be a single keyword line, not bullets")

    # One-page heuristic: rough char budget
    markdown_len = len(summary) + len(skills) + bullet_count * 180 + 400
    if markdown_len > 6500:
        errors.append("content likely exceeds one page")

    # JD keyword coverage among inventory skills (informational)
    jd = (jd_text or "").lower()
    covered = 0
    missing_requested = []
    for kw in ("sql", "python", "tableau", "airflow", "etl", "excel"):
        if kw in jd:
            if kw in skills.lower() or kw in summary.lower():
                covered += 1
            else:
                missing_requested.append(kw)

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "bullet_count": bullet_count,
            "approx_chars": markdown_len,
            "jd_core_covered": covered,
            "jd_core_missing_in_projection": missing_requested,
            "hidden_entries": len(resume.get("hidden_entries") or []),
        },
    }
