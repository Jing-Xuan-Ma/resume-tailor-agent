"""
JD Parsing Node — Extract structured fields from raw job description text.
Uses LLM with Structured Output (JSON mode).
"""

from langchain_core.output_parsers import PydanticOutputParser

from app.config import settings
from app.core.llm_client import get_chat_openai
from app.core.models import ParsedJobDescription


class JDParsingNode:
    """
    Parses a raw job description into structured fields.
    """

    def __init__(self):
        self._llm = None
        self.parser = PydanticOutputParser(pydantic_object=ParsedJobDescription)

    def _get_llm(self):
        if self._llm is None:
            self._llm = get_chat_openai(
                model=settings.DEFAULT_PARSER_MODEL,
                temperature=0.1,
            )
        return self._llm

    async def parse(self, jd_text: str) -> ParsedJobDescription:
        """
        Parse raw JD text into ParsedJobDescription.
        """
        # Simple implementation using model-specific structured output
        # In production, you'd use with_structured_output or tool calling
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a job description parser. Extract structured information "
                    "from the provided job description. Return ONLY valid JSON matching "
                    "the expected schema. Do not add commentary."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Parse this job description and extract all relevant fields:\n\n{jd_text}\n\n"
                    f"{self.parser.get_format_instructions()}"
                ),
            },
        ]

        try:
            llm = self._get_llm()
            response = await llm.ainvoke(messages)
            # Attempt to parse the LLM output
            parsed = self.parser.parse(response.content)
            parsed.raw_text = jd_text
            if not parsed.title or parsed.title.strip().lower() in {"unknown title", "unknown", "n/a"}:
                heur = self._heuristic_parse(jd_text)
                if heur.title:
                    parsed.title = heur.title
                if not parsed.company and heur.company:
                    parsed.company = heur.company
            return parsed
        except Exception:
            # Fallback: heuristic structure (also used when no API key)
            return self._heuristic_parse(jd_text)

    def _heuristic_parse(self, jd_text: str) -> ParsedJobDescription:
        lines = [ln.strip() for ln in (jd_text or "").splitlines() if ln.strip()]
        title = lines[0] if lines else "Imported Job"
        company = None
        for ln in lines[:8]:
            low = ln.lower()
            if low.startswith("company:"):
                company = ln.split(":", 1)[1].strip() or None
                break
            if low.startswith("company "):
                company = ln[7:].strip(" :-") or None
                break
        # Prefer a short title-like first line (not a paragraph)
        if len(title) > 120 or title.count(" ") > 14:
            title = "Imported Job"
        return ParsedJobDescription(
            title=title or "Imported Job",
            company=company,
            raw_text=jd_text,
            required_skills=[],
            preferred_skills=[],
            key_responsibilities=[],
            company_values=[],
            ats_keywords=[],
        )
