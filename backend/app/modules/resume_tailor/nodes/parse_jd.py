"""
JD Parsing Node — Extract structured fields from raw job description text.
Uses GPT-4o with Structured Output (JSON mode).
"""

from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import PydanticOutputParser

from app.config import settings
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
            kwargs = {
                "model": settings.DEFAULT_PARSER_MODEL,
                "temperature": 0.1,
                "api_key": settings.OPENAI_API_KEY,
            }
            if settings.OPENAI_BASE_URL:
                kwargs["base_url"] = settings.OPENAI_BASE_URL
            self._llm = ChatOpenAI(**kwargs)
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
            return parsed
        except Exception:
            # Fallback: return basic structure (also used when no API key)
            return ParsedJobDescription(
                title="Unknown Title",
                raw_text=jd_text,
                required_skills=[],
                preferred_skills=[],
                key_responsibilities=[],
                company_values=[],
                ats_keywords=[],
            )
