"""Create local files that browser automation can upload."""

import re
from pathlib import Path

from app.modules.resume_core.draft_pdf import markdown_to_pdf, resume_dict_to_pdf

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_ARTIFACT_ROOT = _PROJECT_ROOT / "data" / "application_artifacts"


def _safe(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-.")
    return cleaned or "artifact"


def create_application_artifacts(
    *,
    user_id: str,
    application_run_id: str,
    draft: dict | None,
    cover_letter: dict | None,
    company: str | None = None,
    position: str | None = None,
) -> dict:
    folder_name = (
        _safe(f"{company or 'Company'}_{position or 'Position'}")
        if (company or position)
        else _safe(application_run_id)
    )
    output_dir = _ARTIFACT_ROOT / _safe(user_id) / folder_name
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, str] = {}

    if draft:
        try:
            markdown = str(draft.get("markdown") or "")
            full_resume = draft.get("full_resume") if isinstance(draft.get("full_resume"), dict) else None
            if markdown.strip():
                pdf_bytes = markdown_to_pdf(markdown)
            elif full_resume:
                pdf_bytes = resume_dict_to_pdf(full_resume)
            else:
                pdf_bytes = b""
            if pdf_bytes:
                resume_path = output_dir / "resume.pdf"
                resume_path.write_bytes(pdf_bytes)
                artifacts["resume"] = str(resume_path)
            elif markdown:
                resume_path = output_dir / "resume.txt"
                resume_path.write_text(markdown, encoding="utf-8")
                artifacts["resume"] = str(resume_path)
        except Exception:
            markdown = (draft or {}).get("markdown") or ""
            if markdown:
                resume_path = output_dir / "resume.txt"
                resume_path.write_text(str(markdown), encoding="utf-8")
                artifacts["resume"] = str(resume_path)

    if cover_letter and cover_letter.get("text"):
        cover_path = output_dir / "cover_letter.txt"
        cover_path.write_text(str(cover_letter["text"]), encoding="utf-8")
        artifacts["cover_letter"] = str(cover_path)

    return artifacts
