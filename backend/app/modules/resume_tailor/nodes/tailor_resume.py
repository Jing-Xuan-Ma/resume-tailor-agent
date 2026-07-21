"""
Tailor Resume Node — Core LLM-driven resume customization.
Uses Claude 3.5 Sonnet for high-quality, context-aware rewriting.
"""

from pathlib import Path

from langchain_openai import ChatOpenAI

from app.config import settings


class TailorResumeNode:
    """
    Generates a tailored resume based on user experiences and JD.
    """

    def __init__(self):
        self._llm = None
        # Load system prompt from file
        system_prompt_path = Path(__file__).parent.parent / "prompts" / "tailor_system.txt"
        self.system_prompt = system_prompt_path.read_text(encoding="utf-8")

    def _get_llm(self):
        if self._llm is None:
            kwargs = {
                "model": settings.DEFAULT_TAILOR_MODEL,
                "temperature": 0.3,
                "api_key": settings.OPENAI_API_KEY,
                "max_tokens": 4096,
            }
            if settings.OPENAI_BASE_URL:
                kwargs["base_url"] = settings.OPENAI_BASE_URL
            self._llm = ChatOpenAI(**kwargs)
        return self._llm

    async def run(
        self,
        resume_data: dict,
        jd_parsed: dict,
        matched_experiences: list,
        memory_context: dict,
    ) -> dict:
        """
        Generate tailored resume.
        Returns a dict representing TailoredResume (serialized).
        """
        # Guard: no resume data provided
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

        # Build user prompt
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
            # TODO: Parse JSON structured output from response
            # For MVP, we treat the entire response as the tailoring summary
            tailoring_summary = content[:2000] if len(content) > 2000 else content
        except Exception:
            tailoring_summary = (
                "[LLM unavailable] Tailoring could not be completed. "
                "Please check your API key configuration."
            )

        # Extract user skills from resume (intersection with JD skills)
        user_skills = resume_data.get("skills", [])
        jd_skills = set(jd_parsed.get("required_skills", []) + jd_parsed.get("preferred_skills", []))
        highlighted_skills = [s for s in user_skills if s.lower() in {j.lower() for j in jd_skills}]

        return {
            "summary": resume_data.get("summary"),
            "skills": highlighted_skills,
            "experiences": [],
            "tailoring_summary": tailoring_summary,
            "ats_score_estimate": None,  # TODO: implement real ATS scoring
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

Instructions:
1. Rewrite bullet points to align with JD keywords.
2. Quantify achievements where possible.
3. Ensure every claim maps to an original experience with an `evidence_from` field.
4. Output the tailored resume in the required JSON structure.
"""
