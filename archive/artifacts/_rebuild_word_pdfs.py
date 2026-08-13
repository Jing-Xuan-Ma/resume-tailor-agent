"""Rebuild version PDFs from stored master-injected DOCX via Word."""
from __future__ import annotations

from pathlib import Path

from app.modules.resume_workspace.service import ResumeWorkspaceService
from app.modules.resume_workspace.template_editor import ResumeTemplateEditor

ROOT = Path(r"d:\resume-agent\data\templates")
svc = ResumeWorkspaceService()
fixed = 0
errors = 0
for docx_path in sorted(ROOT.glob("*/resume.docx")):
    version_id = docx_path.parent.name
    try:
        pdf = ResumeTemplateEditor.convert_docx_to_pdf_via_word(
            docx_path.read_bytes(), label=version_id[:8]
        )
        svc._store_version_file(version_id, "pdf", pdf)
        fixed += 1
        print("ok", version_id, "pdf_kb", round(len(pdf) / 1024, 1))
    except Exception as exc:
        errors += 1
        print("fail", version_id, str(exc)[:120])
    if fixed >= 5:
        break  # enough for UI test; full rebuild is slow

print("done fixed=", fixed, "errors=", errors)
