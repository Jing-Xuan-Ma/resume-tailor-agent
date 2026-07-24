"""
Text Export Node — render tailored resumes in the fixed reference format.
"""


class TextExportNode:
    """Formats a TailoredResume dict into the user's standard resume layout."""

    def render(self, tailored_resume: dict) -> str:
        tr = tailored_resume or {}
        lines: list[str] = []

        name = tr.get("candidate_name")
        contact = tr.get("contact_line")
        if name:
            lines.append(str(name).upper())
        if contact:
            lines.append(str(contact))

        summary = tr.get("summary")
        if summary:
            lines.append(str(summary))
            lines.append("")

        education = tr.get("education", [])
        if education:
            lines.append("EDUCATION")
            for edu in education:
                institution = edu.get("institution", "")
                date_range = edu.get("date_range", "")
                if institution or date_range:
                    lines.append(" ".join(p for p in [institution, date_range] if p))
                degree_line = " ".join(
                    p for p in [edu.get("degree", ""), edu.get("field", ""), edu.get("location", "")] if p
                )
                if degree_line:
                    lines.append(degree_line)
                coursework = edu.get("coursework") or []
                if coursework:
                    lines.append(f"• Coursework: {' | '.join(str(c) for c in coursework)}")
            lines.append("")

        experiences = tr.get("experiences", [])
        if experiences:
            lines.append("PROFESSIONAL EXPERIENCE")
            for exp in experiences:
                lines.append(self._entry_heading(exp.get("title"), exp.get("company"), exp.get("location"), exp.get("date_range")))
                for bullet in exp.get("bullets", [])[:3]:
                    lines.append(f"• {self._bullet_text(bullet)}")
            lines.append("")

        projects = tr.get("projects", [])
        if projects:
            lines.append("PROJECTS")
            for proj in projects:
                tools = proj.get("tools") or proj.get("skills") or []
                company = ", ".join(str(t) for t in tools)
                context = proj.get("context", "Independent Project")
                lines.append(self._entry_heading(proj.get("name"), company, context, proj.get("date_range")))
                bullets = proj.get("bullets") or []
                if bullets:
                    for bullet in bullets[:3]:
                        lines.append(f"• {self._bullet_text(bullet)}")
                elif proj.get("description"):
                    lines.append(f"• {proj.get('description')}")
            lines.append("")

        competitions = tr.get("competitions", [])
        if competitions:
            lines.append("COMPETITIONS")
            for comp in competitions:
                lines.append(self._entry_heading(comp.get("name"), comp.get("role"), comp.get("location"), comp.get("date_range")))
                for bullet in comp.get("bullets", []):
                    lines.append(f"• {self._bullet_text(bullet)}")
            lines.append("")

        skills_text = tr.get("skills_certifications")
        if not skills_text:
            skills = tr.get("skills", [])
            certifications = tr.get("certifications", [])
            skills_text = ", ".join(str(s) for s in [*skills, *certifications])
        if skills_text:
            lines.append("SKILLS & CERTIFICATIONS")
            lines.append(str(skills_text))

        result = "\n".join(line for line in lines if line is not None).strip()
        return result if result else "[No tailored resume content available.]"

    def _entry_heading(self, left: object, middle: object, location: object, date_range: object) -> str:
        left_text = str(left or "").strip()
        middle_text = str(middle or "").strip()
        location_text = str(location or "").strip()
        date_text = str(date_range or "").strip()
        first = " | ".join(p for p in [left_text, middle_text] if p)
        second = " - ".join(p for p in [location_text, date_text] if p)
        return " ".join(p for p in [first, second] if p)

    def _bullet_text(self, bullet: object) -> str:
        if isinstance(bullet, dict):
            return str(bullet.get("text", ""))
        return str(bullet)
