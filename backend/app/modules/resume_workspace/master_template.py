"""Load and cache the read-only master DOCX into the workspace template store."""

from __future__ import annotations

import hashlib
from pathlib import Path

from app import db
from app.modules.resume_workspace.template_editor import ResumeTemplateEditor

MASTER_SRC = Path(r"d:\Jingxuan's Resumes\Jingxuan_Resume_Data Analyst.docx")
MASTER_COPY = (
    Path(__file__).resolve().parents[4]
    / "data"
    / "templates"
    / "master"
    / "Jingxuan_Resume_Data_Analyst.docx"
)


def ensure_master_template_bytes() -> bytes | None:
    if MASTER_COPY.exists():
        return MASTER_COPY.read_bytes()
    if not MASTER_SRC.exists():
        return None
    MASTER_COPY.parent.mkdir(parents=True, exist_ok=True)
    data = MASTER_SRC.read_bytes()
    MASTER_COPY.write_bytes(data)
    return data


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ensure_user_has_master_template(user_id: str) -> dict | None:
    """Seed or refresh the user's active template from the locked disk master.

    If a cached DB copy exists but no longer matches the on-disk master bytes,
    replace it so layout fixes (e.g. EDUCATION degree-line tabs) propagate.
    """
    data = ensure_master_template_bytes()
    if not data:
        return None

    existing = db.get_active_template(user_id)
    if existing and existing.get("docx_bytes"):
        if _sha256(existing["docx_bytes"]) == _sha256(data):
            return existing

    editor = ResumeTemplateEditor()
    blocks = editor.load_template(data)
    template_id = db.save_template(
        user_id=user_id,
        filename="Jingxuan_Resume_Data_Analyst.docx",
        docx_bytes=data,
        parsed_blocks=blocks["blocks"],
    )
    return db.get_template(template_id)
