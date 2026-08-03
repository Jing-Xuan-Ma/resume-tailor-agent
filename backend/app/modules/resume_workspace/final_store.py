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


def extract_company_position(resume: dict[str, Any], session: dict[str, Any] | None = None) -> tuple[str, str]:
    session = session or {}
    company = ""
    position = ""

    # Prefer job-linked fields when present on session
    company = str(session.get("company") or "")
    position = str(session.get("position") or session.get("title") or "")

    if not company or not position:
        jd = str(session.get("jd_text") or "")
        lines = [ln.strip() for ln in jd.splitlines() if ln.strip()]
        if lines and not position:
            position = lines[0][:120]
        for ln in lines[:8]:
            if ln.lower().startswith("company:"):
                company = ln.split(":", 1)[1].strip()
                break

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
) -> dict[str, Any]:
    FINAL_ROOT.mkdir(parents=True, exist_ok=True)
    folder = FINAL_ROOT / folder_name(company, position)
    folder.mkdir(parents=True, exist_ok=True)

    base = slugify(f"{company}_{position}", max_len=80)
    meta = {
        "company": company,
        "position": position,
        "version_id": version_id,
        "folder": str(folder),
    }

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
    if docx_bytes:
        path = folder / f"{base}.docx"
        path.write_bytes(docx_bytes)
        files["docx"] = str(path)
    if pdf_bytes:
        path = folder / f"{base}.pdf"
        path.write_bytes(pdf_bytes)
        files["pdf"] = str(path)

    return {"folder": str(folder), "files": files, "company": company, "position": position}
