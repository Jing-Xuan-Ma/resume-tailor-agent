"""Minimal one-page PDF from markdown/text for application artifacts."""

from __future__ import annotations

from textwrap import wrap

from app.modules.resume_core.text_export import TextExportNode
from app.modules.resume_workspace.template_editor import ResumeTemplateEditor


def resume_dict_to_markdown(resume: dict | None) -> str:
    return TextExportNode().render(resume or {})


def markdown_to_pdf(markdown: str) -> bytes:
    """Render plain resume markdown to a single-page PDF (artifact upload path)."""
    raw_lines = [line.strip() for line in (markdown or "").splitlines() if line.strip()]
    if not raw_lines:
        raw_lines = ["No resume content available."]
    configs = [
        {"font_size": 7.8, "leading": 9.1, "wrap_width": 132},
        {"font_size": 7.2, "leading": 8.3, "wrap_width": 146},
        {"font_size": 6.7, "leading": 7.7, "wrap_width": 158},
    ]
    section_names = {
        "EDUCATION",
        "PROFESSIONAL EXPERIENCE",
        "PROJECTS",
        "COMPETITIONS",
        "SKILLS & CERTIFICATIONS",
    }

    def wrap_lines(raw: list[str], width: int) -> list[str]:
        lines: list[str] = []
        for line0 in raw:
            line = line0.replace("* ", "• ")
            if line in section_names:
                lines.append(line)
                continue
            is_bullet = line.startswith("•")
            wrapped = wrap(line, width=width, subsequent_indent="  " if is_bullet else "") or [line]
            lines.extend(wrapped)
        return lines

    top, bottom = 752, 34
    selected_lines: list[str] = []
    selected = configs[-1]
    for config in configs:
        lines = wrap_lines(raw_lines, config["wrap_width"])
        max_lines = int((top - bottom) / config["leading"])
        selected_lines = lines
        selected = config
        if len(lines) <= max_lines:
            break

    return ResumeTemplateEditor._render_pdf(
        selected_lines,
        font_size=selected["font_size"],
        leading=selected["leading"],
        top=top,
        page_height=792,
    )


def resume_dict_to_pdf(resume: dict | None) -> bytes:
    return markdown_to_pdf(resume_dict_to_markdown(resume))
