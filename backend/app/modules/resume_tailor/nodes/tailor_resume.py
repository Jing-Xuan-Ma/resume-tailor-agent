"""
Tailor Resume Node — Core LLM-driven resume customization.
Uses the unified LLM client for provider-agnostic model access.
"""

import json
import re
from pathlib import Path

from app.config import settings
from app.core.llm_client import get_chat_openai


class TailorResumeNode:
    """
    Generates a tailored resume based on user experiences and JD.
    Parses LLM's structured JSON output into a usable dict.
    """

    def __init__(self):
        self._llm = None
        system_prompt_path = Path(__file__).parent.parent / "prompts" / "tailor_system.txt"
        template_path = Path(__file__).parent.parent / "prompts" / "standard_resume_template.md"
        self.system_prompt = system_prompt_path.read_text(encoding="utf-8")
        self.standard_template = template_path.read_text(encoding="utf-8")

    def _get_llm(self):
        if self._llm is None:
            self._llm = get_chat_openai(
                model=settings.DEFAULT_TAILOR_MODEL,
                temperature=0.3,
                max_tokens=4096,
            )
        return self._llm

    def _parse_json_from_llm(self, content: object) -> dict | None:
        """Extract the first valid JSON object from messy LLM output."""
        if not isinstance(content, str):
            content = str(content)

        candidates: list[str] = []
        for match in re.finditer(r"```(?:json)?\s*(.*?)```", content, re.DOTALL | re.IGNORECASE):
            candidates.append(match.group(1).strip())
        candidates.append(content.strip())

        decoder = json.JSONDecoder()
        for candidate in candidates:
            stripped = candidate.strip()
            if stripped.startswith("json"):
                stripped = stripped[4:].strip()
            for idx, char in enumerate(stripped):
                if char != "{":
                    continue
                try:
                    parsed, _ = decoder.raw_decode(stripped[idx:])
                    if isinstance(parsed, dict):
                        if isinstance(parsed.get("tailored_resume"), dict):
                            return parsed["tailored_resume"]
                        return parsed
                except json.JSONDecodeError:
                    continue

        return None

    async def run(
        self,
        resume_data: dict,
        jd_parsed: dict,
        matched_experiences: list,
        memory_context: dict,
    ) -> dict:
        """
        Generate tailored resume.
        Returns a dict representing TailoredResume (serialized) with
        parsed structured data from the LLM.
        """
        if not resume_data or not resume_data.get("experiences"):
            return {
                "summary": None,
                "skills": [],
                "experiences": [],
                "tailoring_summary": (
                    "I could not tailor the resume because no original resume content was provided. "
                    "To comply with the no-fabrication requirement, I cannot add any skills, "
                    "experience bullets, projects, or achievements that were not present in the source resume. "
                    "Please upload your resume first, then I can tailor it for this role."
                ),
                "ats_score_estimate": None,
            }

        user_prompt = self._build_user_prompt(
            resume_data=resume_data,
            jd_parsed=jd_parsed,
            matched_experiences=matched_experiences,
            memory_context=memory_context,
        )

        messages = [
            ("system", self.system_prompt),
            ("human", user_prompt),
        ]

        try:
            llm = self._get_llm()
            response = await llm.ainvoke(messages)
            content = response.content

            parsed = self._parse_json_from_llm(content)

            if parsed:
                return self._build_tailored_resume(parsed, resume_data, jd_parsed)
            else:
                return {
                    "summary": resume_data.get("summary"),
                    "skills": [],
                    "experiences": [],
                    "tailoring_summary": content[:2000] if len(content) > 2000 else content,
                    "ats_score_estimate": None,
                }
        except Exception:
            tailoring_summary = (
                "[LLM unavailable] Tailoring could not be completed. "
                "Please check your API key configuration."
            )
            return {
                "summary": resume_data.get("summary"),
                "skills": [],
                "experiences": [],
                "tailoring_summary": tailoring_summary,
                "ats_score_estimate": None,
            }

    async def revise(
        self,
        *,
        current_resume: dict,
        instruction: str,
        jd_parsed: dict,
        key_map: list[dict],
        original_resume: dict,
    ) -> dict:
        """Revise the current draft in-place while preserving evidence constraints."""
        user_prompt = f"""Revise the current tailored resume according to the user's instruction.

## USER INSTRUCTION
{instruction}

## CURRENT TAILORED RESUME JSON
{current_resume}

## ORIGINAL RESUME EVIDENCE
{original_resume}

## JOB DESCRIPTION PARSED
{jd_parsed}

## CURRENT JD KEY MAP
{key_map}

Rules:
1. Preserve truthful, evidence-backed content only.
2. Do not add unsupported claims, skills, companies, dates, projects, or metrics.
3. Keep the same JSON structure as the original tailoring output.
4. Update tailoring_summary to explain the revision.
"""
        messages = [
            ("system", self.system_prompt),
            ("human", user_prompt),
        ]
        try:
            llm = self._get_llm()
            response = await llm.ainvoke(messages)
            parsed = self._parse_json_from_llm(response.content)
            if parsed:
                return self._build_tailored_resume(parsed, original_resume, jd_parsed)
        except Exception:
            pass

        unchanged = dict(current_resume or {})
        note = unchanged.get("tailoring_summary") or "Current draft preserved."
        unchanged["tailoring_summary"] = (
            f"{note}\n\nRevision request could not be applied because the LLM was unavailable."
        )
        return unchanged

    def _build_tailored_resume(
        self, parsed: dict, resume_data: dict, jd_parsed: dict
    ) -> dict:
        summary = parsed.get("summary") or resume_data.get("summary")
        skills = parsed.get("skills", []) or resume_data.get("skills", [])
        skills_certifications = (
            parsed.get("skills_certifications")
            or resume_data.get("skills_certifications")
            or ", ".join(str(s) for s in skills)
        )
        ats_score = parsed.get("ats_score_estimate")
        tailoring_summary = parsed.get("tailoring_summary", "")

        raw_experiences = parsed.get("experiences", []) or resume_data.get("experiences", [])
        experiences = []
        for exp in raw_experiences:
            if not isinstance(exp, dict):
                continue
            raw_bullets = exp.get("bullets", [])
            bullets = []
            for b in raw_bullets:
                if isinstance(b, str):
                    bullets.append({"text": b, "evidence_from": None, "original_text": None})
                elif isinstance(b, dict):
                    bullets.append({
                        "text": b.get("text", ""),
                        "evidence_from": b.get("evidence_from") or exp.get("original_id"),
                        "original_text": b.get("original_text"),
                    })
            experiences.append({
                "original_id": str(exp.get("original_id", "")),
                "company": exp.get("company", ""),
                "title": exp.get("title", ""),
                "location": exp.get("location", ""),
                "date_range": exp.get("date_range", ""),
                "bullets": bullets[:3],
                "skills_highlighted": exp.get("skills_highlighted", []),
            })

        projects = []
        for proj in parsed.get("projects", []) or resume_data.get("projects", []):
            if isinstance(proj, dict):
                projects.append({
                    "name": proj.get("name", ""),
                    "tools": proj.get("tools", []),
                    "context": proj.get("context", "Independent Project"),
                    "date_range": proj.get("date_range", ""),
                    "description": proj.get("description", ""),
                    "url": proj.get("url"),
                    "bullets": proj.get("bullets", [])[:3],
                    "skills": proj.get("skills", []),
                })

        education = []
        for edu in parsed.get("education", []) or resume_data.get("education", []):
            if isinstance(edu, dict):
                education.append({
                    "institution": edu.get("institution", ""),
                    "degree": edu.get("degree", ""),
                    "field": edu.get("field", ""),
                    "location": edu.get("location", ""),
                    "date_range": edu.get("date_range", ""),
                    "coursework": edu.get("coursework", []),
                    "gpa": edu.get("gpa"),
                })

        competitions = []
        for comp in parsed.get("competitions", []) or resume_data.get("competitions", []):
            if isinstance(comp, dict):
                competitions.append({
                    "name": comp.get("name", ""),
                    "role": comp.get("role", ""),
                    "location": comp.get("location", ""),
                    "date_range": comp.get("date_range", ""),
                    "bullets": comp.get("bullets", []),
                })

        certifications = parsed.get("certifications", []) or resume_data.get("certifications", []) or []

        return {
            "candidate_name": parsed.get("candidate_name") or resume_data.get("candidate_name", ""),
            "contact_line": parsed.get("contact_line") or resume_data.get("contact_line", ""),
            "summary": summary,
            "skills": skills,
            "skills_certifications": skills_certifications,
            "experiences": experiences,
            "projects": projects,
            "education": education,
            "competitions": competitions,
            "certifications": certifications,
            "tailoring_summary": tailoring_summary,
            "ats_score_estimate": ats_score,
        }

    def _build_user_prompt(
        self,
        resume_data: dict,
        jd_parsed: dict,
        matched_experiences: list,
        memory_context: dict,
    ) -> str:
        return f"""Please tailor the following resume for the job description provided.

## USER'S ORIGINAL RESUME
{resume_data}

## JOB DESCRIPTION (PARSED)
{jd_parsed}

## MOST RELEVANT EXPERIENCES (PRE-MATCHED)
{matched_experiences}

## USER PREFERENCES FROM HISTORY
{memory_context.get('preferences', {})}

## STANDARD RESUME TEMPLATE AND FORMAT RULES
{self.standard_template}

Instructions:
1. Rewrite bullet points to align with JD keywords.
2. Quantify achievements where possible.
3. Ensure every claim maps to an original experience with an `evidence_from` field.
4. Preserve the exact template section order and one-page concise style.
5. Output the tailored resume in the required JSON structure.
"""
