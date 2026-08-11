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
    "built",
    "designed",
    "engineered",
    "led",
    "delivered",
    "applied",
    "conducted",
    "optimized",
    "prepared",
    "used",
    "faced",
    "given",
    "to ",
    "analyzed",
    "extended",
    "collected",
    "created",
    "developed",
    "implemented",
    "reduced",
)


def _bullets(entry: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for b in entry.get("bullets") or []:
        if isinstance(b, dict):
            out.append(b)
        else:
            out.append({"text": str(b)})
    return out


def _entry_blob(entry: dict[str, Any]) -> str:
    return " ".join(
        [
            str(entry.get("title") or ""),
            str(entry.get("company") or ""),
            str(entry.get("name") or ""),
            " ".join(str(t) for t in (entry.get("tools") or [])),
            " ".join(str(t) for t in (entry.get("tags") or [])),
            " ".join(str(b.get("text") or "") for b in _bullets(entry)),
        ]
    )


def _entry_id(kind: str, index: int, entry: dict[str, Any]) -> str:
    label = entry.get("company") or entry.get("name") or entry.get("title") or str(index)
    return f"{kind}:{index}:{label}"


def _heuristic_scores(jd_text: str, entries: list[dict[str, Any]]) -> dict[str, float]:
    """Fallback relevance scoring with no LLM call — token-overlap only, no per-entry
    special-casing. Used only if the LLM decision engine call fails outright, so a
    missing/rate-limited model never blocks generation entirely.
    """
    jd = (jd_text or "").lower()
    tokens = set(re.findall(r"[a-zA-Z+]{3,}", jd))
    scores: dict[str, float] = {}
    for e in entries:
        blob = _entry_blob(e).lower()
        hits = sum(1 for t in tokens if t in blob) if tokens else 0
        scores[id(e).__repr__()] = hits / max(len(tokens), 1)
    return scores


def _project_from_scored(
    master: dict[str, Any],
    jd_text: str,
    *,
    all_entries: list[tuple[str, str, int, dict[str, Any]]],
    by_id: dict[str, Any],
) -> dict[str, Any]:
    projected = {
        "candidate_name": master.get("candidate_name"),
        "contact_line": master.get("contact_line"),
        "summary": master.get("summary"),
        "education": list(master.get("education") or []),
        "experiences": [],
        "projects": [],
        "competitions": [],
        "skills_certifications": master.get("skills_certifications"),
        "hidden_entries": [],
    }

    heuristic = _heuristic_scores(jd_text, [e for _, _, _, e in all_entries])
    scored: list[tuple[str, str, int, dict[str, Any], float, bool, str]] = []
    for item_id, kind, idx, entry in all_entries:
        d = by_id.get(item_id)
        if d is not None:
            score = d.relevance_score
            keep = d.decision == "keep"
            reason = d.reason
        else:
            score = heuristic.get(id(entry).__repr__(), 0.0)
            keep = True
            reason = "decision engine unavailable; kept by default (heuristic score only)"
        scored.append((item_id, kind, idx, entry, score, keep, reason))

    def emit(kind: str, section: str) -> None:
        rows = [r for r in scored if r[1] == kind]
        rows.sort(key=lambda r: r[4], reverse=True)
        for item_id, _k, _idx, entry, score, keep, reason in rows:
            if keep:
                out = dict(entry)
                out["_relevance_score"] = score
                projected[section].append(out)
            else:
                projected["hidden_entries"].append(
                    {"kind": kind, "key": item_id, "score": score, "reason": reason}
                )

    emit("experience", "experiences")
    emit("project", "projects")
    emit("competition", "competitions")

    jd = (jd_text or "").lower()
    skills_raw = str(master.get("skills_certifications") or "")
    parts = [p.strip() for p in skills_raw.replace(";", ",").split(",") if p.strip()]
    hit, rest = [], []
    for p in parts:
        if p.lower() in jd:
            hit.append(p)
        else:
            rest.append(p)
    projected["skills_certifications"] = ", ".join(hit + rest) if (hit or rest) else skills_raw
    projected["summary"] = master.get("summary")
    return projected


def _collect_entries(
    master: dict[str, Any],
) -> tuple[dict[str, Any], list[tuple[str, str, int, dict[str, Any]]]]:
    experiences = list(master.get("experiences") or [])
    projects = list(master.get("projects") or [])
    competitions = list(master.get("competitions") or [])

    empty = {
        "candidate_name": master.get("candidate_name"),
        "contact_line": master.get("contact_line"),
        "summary": master.get("summary"),
        "education": list(master.get("education") or []),
        "experiences": [],
        "projects": [],
        "competitions": [],
        "skills_certifications": master.get("skills_certifications"),
        "hidden_entries": [],
    }

    all_entries: list[tuple[str, str, int, dict[str, Any]]] = []
    for i, e in enumerate(experiences):
        all_entries.append((_entry_id("experience", i, e), "experience", i, e))
    for i, e in enumerate(projects):
        all_entries.append((_entry_id("project", i, e), "project", i, e))
    for i, e in enumerate(competitions):
        all_entries.append((_entry_id("competition", i, e), "competition", i, e))
    return empty, all_entries


def project_for_jd(
    master: dict[str, Any],
    jd_text: str,
    *,
    jd_title: str = "",
    jd_required_skills: list[str] | None = None,
    jd_keywords: list[str] | None = None,
) -> dict[str, Any]:
    """Show/hide experiences & projects by real JD relevance — sync LLM path."""
    from app.modules.resume_workspace.decision_engine import ExperienceItem, score_experience_items

    empty, all_entries = _collect_entries(master)
    if not all_entries:
        return empty

    items = [
        ExperienceItem(id=item_id, text=_entry_blob(entry), source=kind)
        for item_id, kind, _idx, entry in all_entries
    ]
    try:
        decisions = score_experience_items(
            jd_title=jd_title,
            jd_required_skills=jd_required_skills or [],
            jd_keywords=jd_keywords or [],
            items=items,
        )
        by_id = {d.item_id: d for d in decisions}
    except Exception:
        by_id = {}

    return _project_from_scored(master, jd_text, all_entries=all_entries, by_id=by_id)


async def project_for_jd_async(
    master: dict[str, Any],
    jd_text: str,
    *,
    jd_title: str = "",
    jd_required_skills: list[str] | None = None,
    jd_keywords: list[str] | None = None,
) -> dict[str, Any]:
    """Async Phase 2a — safe to run concurrently across shopping-cart jobs."""
    from app.modules.resume_workspace.decision_engine import ExperienceItem, ascore_experience_items

    empty, all_entries = _collect_entries(master)
    if not all_entries:
        return empty

    items = [
        ExperienceItem(id=item_id, text=_entry_blob(entry), source=kind)
        for item_id, kind, _idx, entry in all_entries
    ]
    try:
        decisions = await ascore_experience_items(
            jd_title=jd_title,
            jd_required_skills=jd_required_skills or [],
            jd_keywords=jd_keywords or [],
            items=items,
        )
        by_id = {d.item_id: d for d in decisions}
    except Exception:
        by_id = {}

    return _project_from_scored(master, jd_text, all_entries=all_entries, by_id=by_id)


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
