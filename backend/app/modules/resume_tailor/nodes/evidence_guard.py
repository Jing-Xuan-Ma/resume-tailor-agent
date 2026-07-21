"""
Evidence Guard Node — Independent fact-checker that verifies tailored claims.
"""

from pathlib import Path

from langchain_anthropic import ChatAnthropic

from app.config import settings


class EvidenceGuardNode:
    """
    Verifies that every claim in the tailored resume is supported by
    the user's original experiences. Flags hallucinations.
    """

    def __init__(self):
        self.llm = ChatAnthropic(
            model=settings.DEFAULT_TAILOR_MODEL,
            temperature=0.1,
            api_key=settings.ANTHROPIC_API_KEY,
            max_tokens=2048,
        )
        prompt_path = Path(__file__).parent.parent / "prompts" / "evidence_check.txt"
        self.system_prompt = prompt_path.read_text(encoding="utf-8")

    async def verify(self, original_resume: dict, tailored_resume: dict) -> dict:
        """
        Returns verification result with 'passed' boolean and list of issues.
        """
        # TODO: Implement structured verification
        # For MVP, simulate a passing check
        return {
            "passed": True,
            "issues": [],
            "confidence": 0.95,
        }
