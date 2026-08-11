"""Canonical apply profile keys for ATS fill mapping."""

from __future__ import annotations

from pathlib import Path
from typing import Any

CANONICAL_KEYS = (
    "first_name",
    "last_name",
    "full_name",
    "preferred_name",
    "email",
    "phone",
    "location",
    "linkedin",
    "github",
    "portfolio",
    "twitter",
    "source",
    "work_authorized",
    "needs_sponsorship",
    "visa_status",
    "earliest_start",
    "salary_expectation",
    "gender",
    "race_ethnicity",
    "veteran_status",
    "disability_status",
    "resume_path",
    "cover_letter_path",
)

# Voluntary EEO self-identification keys — always require human review before
# submit, even at high match confidence (RESUME_CONSTITUTION: no silent
# submission of protected-class answers).
EEO_KEYS = frozenset({"gender", "race_ethnicity", "veteran_status", "disability_status"})


def _split_name(full: str) -> tuple[str, str]:
    parts = [p for p in str(full or "").strip().split() if p]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def resolve_resume_path(final_path: str | None, version_id: str | None = None) -> str | None:
    """Prefer real resume.docx / resume.pdf under a final_resumes folder."""
    if final_path:
        base = Path(final_path)
        if base.is_file() and base.suffix.lower() in {".docx", ".pdf"} and base.exists():
            return str(base.resolve())
        if base.is_dir():
            for name in ("resume.pdf", "resume.docx"):
                cand = base / name
                if cand.exists():
                    return str(cand.resolve())
            # any pdf/docx
            for pat in ("*.pdf", "*.docx"):
                hits = sorted(base.glob(pat))
                if hits:
                    return str(hits[0].resolve())
    return None


def canonical_apply_profile(
    user_id: str,
    *,
    final_path: str | None = None,
    version_id: str | None = None,
    resume_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Stable key→value map used by LLM/rules mapping. Never invents experience bullets."""
    from app.modules.profile.library_service import get_apply_profile

    raw = dict(get_apply_profile(user_id) or {})
    overrides = resume_overrides or {}
    full = str(
        raw.get("full_name")
        or overrides.get("candidate_name")
        or overrides.get("full_name")
        or "Jingxuan Ma"
    ).strip()
    first, last = _split_name(full)
    email = str(raw.get("email") or overrides.get("email") or "jma107@jh.edu").strip()
    phone = str(raw.get("phone") or overrides.get("phone") or "+1 (410) 240-4366").strip()
    resume_path = resolve_resume_path(final_path, version_id)

    profile = {
        "first_name": first,
        "last_name": last,
        "full_name": full,
        "preferred_name": str(raw.get("preferred_name") or "").strip(),
        "email": email,
        "phone": phone,
        "location": str(raw.get("location") or "").strip(),
        "linkedin": str(raw.get("linkedin_url") or raw.get("linkedin") or "").strip(),
        "github": str(
            raw.get("github_url") or raw.get("resume_tailor_github") or raw.get("github") or ""
        ).strip(),
        "portfolio": str(raw.get("portfolio_url") or raw.get("portfolio") or "").strip(),
        "twitter": str(raw.get("twitter_url") or raw.get("twitter") or "").strip(),
        "source": str(raw.get("source") or raw.get("how_heard") or "").strip(),
        "work_authorized": "Yes" if raw.get("work_authorized", True) else "No",
        "needs_sponsorship": "Yes" if raw.get("needs_sponsorship", True) else "No",
        "visa_status": str(raw.get("visa_status") or "").strip(),
        "earliest_start": str(raw.get("earliest_start") or "").strip(),
        "salary_expectation": str(raw.get("salary_expectation") or "").strip(),
        "gender": str(raw.get("gender") or "").strip(),
        "race_ethnicity": str(raw.get("race_ethnicity") or "").strip(),
        "veteran_status": str(raw.get("veteran_status") or "").strip(),
        "disability_status": str(raw.get("disability_status") or "").strip(),
        "resume_path": resume_path or "",
        "cover_letter_path": "",
    }
    result = {k: profile.get(k, "") for k in CANONICAL_KEYS}
    # Non-canonical extras carried through for the field mapper's custom-answer
    # fallback (job-specific essay questions, ad-hoc ATS questions saved via chat).
    custom_fields = raw.get("custom_fields")
    answers = raw.get("answers")
    result["_custom_fields"] = dict(custom_fields) if isinstance(custom_fields, dict) else {}
    result["_answers"] = dict(answers) if isinstance(answers, dict) else {}
    return result
