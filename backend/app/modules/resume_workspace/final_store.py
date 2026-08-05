"""Persist confirmed resumes under data/final_resumes/{Company}_{Position}/."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# .../backend/app/modules/resume_workspace/final_store.py -> repo root is parents[4]
FINAL_ROOT = Path(__file__).resolve().parents[4] / "data" / "final_resumes"


def slugify(value: str, max_len: int = 60) -> str:
    text = (value or "Unknown").strip()
    text = re.sub(r"[\\/:*?\"<>|]+", "", text)
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"_+", "_", text).strip("._")
    if not text:
        text = "Unknown"
    return text[:max_len]


def folder_name(company: str, position: str) -> str:
    return f"{slugify(company)}_{slugify(position)}"


def resolve_job_company_position(job_id: str | None) -> tuple[str, str]:
    """Look up company/title from jobs or job_listings when session has job_id."""
    if not job_id:
        return "", ""
    try:
        from app import db

        listing = db.get_job_listing(job_id)
        if listing:
            return str(listing.get("company") or ""), str(listing.get("title") or "")
        job = db.get_job(job_id)
        if job:
            return str(job.get("company") or ""), str(job.get("title") or "")
    except Exception:
        pass
    return "", ""


def extract_company_position(resume: dict[str, Any], session: dict[str, Any] | None = None) -> tuple[str, str]:
    session = session or {}
    company = ""
    position = ""

    # Prefer job-linked fields when present on session
    company = str(session.get("company") or "")
    position = str(session.get("position") or session.get("title") or "")

    if not company or not position:
        job_company, job_title = resolve_job_company_position(
            session.get("job_id") or session.get("listing_id")
        )
        if not company:
            company = job_company
        if not position:
            position = job_title

    if not company or not position:
        jd = str(session.get("jd_text") or "")
        lines = [ln.strip() for ln in jd.splitlines() if ln.strip()]
        if lines and not position:
            # "Title at Company" or first line as position
            first = lines[0][:120]
            if " at " in first.lower() and not company:
                left, _, right = first.partition(" at ")
                if not position:
                    position = left.strip()
                company = company or right.strip()
            else:
                position = first
        for ln in lines[:8]:
            low = ln.lower()
            if low.startswith("company:"):
                company = company or ln.split(":", 1)[1].strip()
            if low.startswith("title:") or low.startswith("position:"):
                position = position or ln.split(":", 1)[1].strip()

    if not company:
        exps = resume.get("experiences") or []
        if exps and isinstance(exps[0], dict):
            company = str(exps[0].get("company") or "Target_Company")
        else:
            company = "Target_Company"

    if not position:
        position = str(resume.get("target_role") or "Target_Role")

    return company, position


def save_final_resume(
    *,
    company: str,
    position: str,
    version_id: str,
    markdown: str,
    full_resume: dict[str, Any],
    docx_bytes: bytes | None = None,
    pdf_bytes: bytes | None = None,
    extra_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from datetime import datetime, timezone

    FINAL_ROOT.mkdir(parents=True, exist_ok=True)
    folder = FINAL_ROOT / folder_name(company, position)
    folder.mkdir(parents=True, exist_ok=True)

    base = slugify(f"{company}_{position}", max_len=80)
    meta: dict[str, Any] = {
        "company": company,
        "position": position,
        "version_id": version_id,
        "folder": str(folder),
        "job_id": None,
        "confirmed_at": datetime.now(timezone.utc).isoformat(),
        "apply_status": "not_started",
        "outreach_status": "not_started",
    }
    if extra_meta:
        meta.update({k: v for k, v in extra_meta.items() if v is not None and v != ""})
    # Constitution funnel contract: these keys always present
    meta.setdefault("job_id", None)
    meta.setdefault("apply_status", "not_started")
    meta.setdefault("outreach_status", "not_started")
    meta.setdefault("confirmed_at", datetime.now(timezone.utc).isoformat())

    (folder / f"{base}.txt").write_text(markdown or "", encoding="utf-8")
    (folder / f"{base}.json").write_text(
        json.dumps(full_resume, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    files = {
        "txt": str(folder / f"{base}.txt"),
        "json": str(folder / f"{base}.json"),
        "meta": str(folder / "meta.json"),
    }
    if not docx_bytes:
        raise ValueError("Confirm requires master-template DOCX bytes")
    path = folder / f"{base}.docx"
    path.write_bytes(docx_bytes)
    files["docx"] = str(path)
    # Stable aliases for upload / humans browsing the folder
    (folder / "resume.docx").write_bytes(docx_bytes)
    files["resume_docx"] = str(folder / "resume.docx")

    if not pdf_bytes:
        raise ValueError("Confirm requires Word-exported PDF bytes")
    path = folder / f"{base}.pdf"
    path.write_bytes(pdf_bytes)
    files["pdf"] = str(path)
    (folder / "resume.pdf").write_bytes(pdf_bytes)
    files["resume_pdf"] = str(folder / "resume.pdf")

    return {"folder": str(folder), "files": files, "company": company, "position": position, "meta": meta}
