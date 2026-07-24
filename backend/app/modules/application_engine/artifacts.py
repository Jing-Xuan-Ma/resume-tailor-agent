"""Create local files that browser automation can upload."""

from pathlib import Path
import re

from app.modules.resume_tailor.service import ResumeTailorService


_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_ARTIFACT_ROOT = _PROJECT_ROOT / "data" / "application_artifacts"


def _safe(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-.")
    return cleaned or "artifact"


def create_application_artifacts(*, user_id: str, application_run_id: str, draft: dict | None, cover_letter: dict | None) -> dict:
    output_dir = _ARTIFACT_ROOT / _safe(user_id) / _safe(application_run_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, str] = {}

    if draft:
        try:
            pdf_bytes = ResumeTailorService().export_draft_pdf(draft)
            resume_path = output_dir / "resume.pdf"
            resume_path.write_bytes(pdf_bytes)
            artifacts["resume"] = str(resume_path)
        except Exception:
            markdown = draft.get("markdown") or ""
            if markdown:
                resume_path = output_dir / "resume.txt"
                resume_path.write_text(markdown, encoding="utf-8")
                artifacts["resume"] = str(resume_path)

    if cover_letter and cover_letter.get("text"):
        cover_path = output_dir / "cover_letter.txt"
        cover_path.write_text(str(cover_letter["text"]), encoding="utf-8")
        artifacts["cover_letter"] = str(cover_path)

    return artifacts
