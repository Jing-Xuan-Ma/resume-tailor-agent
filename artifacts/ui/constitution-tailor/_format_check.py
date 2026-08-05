"""Render master + tailored Word PDFs to PNG and run format checklist."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import fitz  # pymupdf

OUT = Path(r"d:\resume-agent\artifacts\ui\constitution-tailor")
OUT.mkdir(parents=True, exist_ok=True)

CHECKS: list[tuple[str, bool, str]] = []


def render_pdf(pdf_path: Path, png_path: Path, zoom: float = 1.6) -> dict:
    doc = fitz.open(pdf_path)
    page = doc[0]
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    png_path.write_bytes(pix.tobytes("png"))
    text = page.get_text("text")
    return {
        "pages": doc.page_count,
        "width": page.rect.width,
        "height": page.rect.height,
        "text": text,
        "png": str(png_path),
    }


# 1) Master reference
master_pdf = OUT / "master_ref.pdf"
if not master_pdf.exists():
    from app.modules.resume_workspace.master_template import ensure_master_template_bytes
    from app.modules.resume_workspace.template_editor import ResumeTemplateEditor

    master_pdf.write_bytes(
        ResumeTemplateEditor.convert_docx_to_pdf_via_word(
            ensure_master_template_bytes(), label="master_ref"
        )
    )

m = render_pdf(master_pdf, OUT / "09-master-template.png")
CHECKS.append(("master_one_page", m["pages"] == 1, f"pages={m['pages']}"))
CHECKS.append(("master_no_md_##", "##" not in m["text"], ""))
CHECKS.append(("master_no_md_**", "**" not in m["text"], ""))
CHECKS.append(("master_has_EDUCATION", "EDUCATION" in m["text"].upper(), ""))
CHECKS.append(("master_has_EXPERIENCE", "EXPERIENCE" in m["text"].upper(), ""))
CHECKS.append(("master_has_SKILLS", "SKILL" in m["text"].upper(), ""))

# 2) Latest Word-quality tailored PDF from templates
root = Path(r"d:\resume-agent\data\templates")
candidates = []
for p in root.glob("*/resume.pdf"):
    if p.stat().st_size > 50000:
        candidates.append(p)
candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
assert candidates, "no Word-quality tailored PDFs"
tpdf = candidates[0]
t = render_pdf(tpdf, OUT / "10-tailored-master-pdf.png")
CHECKS.append(("tailored_one_page", t["pages"] == 1, f"pages={t['pages']} size={tpdf.stat().st_size}"))
CHECKS.append(("tailored_no_md_##", "##" not in t["text"], ""))
CHECKS.append(("tailored_no_md_**", "**" not in t["text"], ""))
CHECKS.append(("tailored_has_EDUCATION", "EDUCATION" in t["text"].upper(), ""))
CHECKS.append(("tailored_has_EXPERIENCE", "EXPERIENCE" in t["text"].upper(), ""))
CHECKS.append(("tailored_pdf_word_size", tpdf.stat().st_size > 50000, f"size={tpdf.stat().st_size}"))

# section order roughly
def section_order_ok(text: str) -> bool:
    u = text.upper()
    i_edu = u.find("EDUCATION")
    i_exp = u.find("PROFESSIONAL EXPERIENCE")
    i_proj = u.find("\nPROJECTS")
    if i_proj < 0:
        i_proj = u.find("PROJECTS")
    i_skills = u.find("SKILLS & CERTIFICATIONS")
    if i_skills < 0:
        i_skills = u.find("SKILLS &")
    if min(i_edu, i_exp, i_skills) < 0:
        return False
    # COMPETITIONS optional; PROJECTS optional but if present must be after experience
    if i_proj >= 0:
        return i_edu < i_exp < i_proj < i_skills
    return i_edu < i_exp < i_skills

CHECKS.append(("master_section_order", section_order_ok(m["text"]), ""))
CHECKS.append(("tailored_section_order", section_order_ok(t["text"]), ""))

# contact line style (pipe separators)
CHECKS.append(("tailored_pipe_contact", "|" in t["text"].split("\n")[1] if len(t["text"].split("\n")) > 1 else "|" in t["text"], ""))

passed = all(ok for _, ok, _ in CHECKS)
print(json.dumps({"passed": passed, "checks": CHECKS, "master_png": m["png"], "tailored_png": t["png"], "tailored_pdf": str(tpdf)}, indent=2))
