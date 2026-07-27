"""Cover letter generation for a saved job and tailored resume."""

from app.config import settings
from app.core.llm_client import get_chat_openai


class CoverLetterNode:
    def __init__(self) -> None:
        self._llm = None

    def _get_llm(self):
        if self._llm is None:
            self._llm = get_chat_openai(
                model=settings.DEFAULT_TAILOR_MODEL,
                temperature=0.35,
                max_tokens=1200,
            )
        return self._llm

    async def run(self, *, job: dict, tailored_resume: dict, original_resume: dict) -> dict:
        prompt = f"""Write a concise, evidence-backed cover letter for this job.

Rules:
1. Do not invent experience, employers, projects, credentials, dates, or metrics.
2. Ground the letter only in the original resume and tailored resume below.
3. Keep it under 260 words.
4. Use a professional tone.
5. Return plain text only.

JOB:
{job.get('raw_text', '')}

TAILORED RESUME:
{tailored_resume}

ORIGINAL RESUME EVIDENCE:
{original_resume}
"""
        try:
            response = await self._get_llm().ainvoke([
                ("system", "You are an expert career writing assistant who never fabricates candidate facts."),
                ("human", prompt),
            ])
            text = str(response.content).strip()
            if text:
                return {"text": text, "model": settings.DEFAULT_TAILOR_MODEL, "source": "llm"}
        except Exception:
            pass

        return {"text": self._fallback(job, tailored_resume), "model": "fallback", "source": "template"}

    def _fallback(self, job: dict, tailored_resume: dict) -> str:
        company = job.get("company") or "your team"
        title = job.get("title") or "this role"
        summary = tailored_resume.get("summary") or "my background aligns with the role's requirements"
        skills = tailored_resume.get("skills") or []
        skill_text = ", ".join(str(skill) for skill in skills[:6])
        return (
            f"Dear Hiring Team,\n\n"
            f"I am excited to apply for {title} at {company}. {summary}\n\n"
            f"My experience is most relevant in {skill_text or 'the responsibilities described in the role'}, "
            "and I would welcome the opportunity to contribute with evidence-backed, practical execution. "
            "I have attached a tailored resume that highlights the most relevant parts of my background for this position.\n\n"
            "Thank you for your time and consideration.\n\n"
            "Sincerely"
        )
