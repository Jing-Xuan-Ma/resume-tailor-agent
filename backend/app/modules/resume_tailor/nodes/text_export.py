"""
Text Export Node — Format tailored resume as plain text for easy editing.
Replaces PDF rendering in MVP; users can copy-paste into Word/Google Docs.
"""

from typing import Optional


class TextExportNode:
    """
    Formats a TailoredResume dict into a clean, standard resume text.
    """

    def render(self, tailored_resume: dict) -> str:
        """
        Convert tailored resume dict to plain text.
        """
        lines: list[str] = []
        tr = tailored_resume or {}

        # Summary
        summary = tr.get("summary")
        if summary:
            lines.append(summary)
            lines.append("")

        # Skills
        skills = tr.get("skills", [])
        if skills:
            lines.append("SKILLS")
            lines.append(", ".join(str(s) for s in skills))
            lines.append("")

        # Experience
        experiences = tr.get("experiences", [])
        if experiences:
            lines.append("PROFESSIONAL EXPERIENCE")
            lines.append("")
            for exp in experiences:
                title = exp.get("title", "")
                company = exp.get("company", "")
                date_range = exp.get("date_range", "")
                header_parts = [p for p in [title, company, date_range] if p]
                lines.append(" | ".join(header_parts))

                for bullet in exp.get("bullets", []):
                    if isinstance(bullet, dict):
                        text = bullet.get("text", "")
                    else:
                        text = str(bullet)
                    lines.append(f"  • {text}")
                lines.append("")

        # Projects
        projects = tr.get("projects", [])
        if projects:
            lines.append("PROJECTS")
            lines.append("")
            for proj in projects:
                name = proj.get("name", "") if isinstance(proj, dict) else str(proj)
                desc = proj.get("description", "") if isinstance(proj, dict) else ""
                lines.append(f"{name}")
                if desc:
                    lines.append(f"  {desc}")
                lines.append("")

        # Education
        education = tr.get("education", [])
        if education:
            lines.append("EDUCATION")
            lines.append("")
            for edu in education:
                if isinstance(edu, dict):
                    institution = edu.get("institution", "")
                    degree = edu.get("degree", "")
                    field = edu.get("field", "")
                    date_range = edu.get("date_range", "")
                    parts = [p for p in [degree, field, institution, date_range] if p]
                    lines.append(" | ".join(parts))
                else:
                    lines.append(str(edu))
            lines.append("")

        # Certifications
        certifications = tr.get("certifications", [])
        if certifications:
            lines.append("CERTIFICATIONS")
            for cert in certifications:
                lines.append(f"  • {cert}")
            lines.append("")

        result = "\n".join(lines).strip()
        return result if result else "[No tailored resume content available.]"
