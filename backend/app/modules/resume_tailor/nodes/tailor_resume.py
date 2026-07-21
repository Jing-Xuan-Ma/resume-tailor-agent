"""
Tailor Resume Node — Core LLM-driven resume customization.
Uses Claude 3.5 Sonnet for high-quality, context-aware rewriting.
"""

from pathlib import Path

from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate

from app.config import settings


class TailorResumeNode:
    """
    Generates a tailored resume based on user experiences and JD.
    """

    def __init__(self):
        self.llm = ChatAnthropic(
            model=settings.DEFAULT_TAILOR_MODEL,
            temperature=0.3,
            api_key=settings.ANTHROPIC_API_KEY,
            max_tokens=4096,
        )
        # Load system prompt from file
        system_prompt_path = Path(__file__).parent.parent / "prompts" / "tailor_system.txt"
        self.system_prompt = system_prompt_path.read_text(encoding="utf-8")

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

        response = await self.llm.ainvoke(messages)

        # TODO: Parse structured output from response
        # For MVP, return a structured dict
        return {
            "summary": "Tailored summary based on JD requirements.",
            "skills": jd_parsed.get("required_skills", []),
            "experiences": [],
            "tailoring_summary": response.content[:500],
            "ats_score_estimate": 85.0,
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
