"""
Evidence Guard Node — Independent fact-checker that verifies tailored claims.
"""

from pathlib import Path
import re

from app.config import settings
from app.core.llm_client import get_chat_openai


class EvidenceGuardNode:
    """
    Verifies that every claim in the tailored resume is supported by
    the user's original experiences. Flags hallucinations.
    """

    def __init__(self):
        self._llm = None
        prompt_path = Path(__file__).parent.parent / "prompts" / "evidence_check.txt"
        self.system_prompt = prompt_path.read_text(encoding="utf-8")

    def _get_llm(self):
        if self._llm is None:
            self._llm = get_chat_openai(
                model=settings.DEFAULT_TAILOR_MODEL,
                temperature=0.1,
                max_tokens=2048,
            )
        return self._llm

    async def verify(self, original_resume: dict, tailored_resume: dict) -> dict:
        """
        Returns verification result with 'passed' boolean and list of issues.
        """
        source_text = self._collect_source_text(original_resume)
        if not source_text.strip():
            return {
                "passed": False,
                "issues": ["No original resume evidence is available for verification."],
                "confidence": 0.0,
            }

        issues: list[str] = []
        source_numbers = self._numbers(source_text)
        source_tokens = self._tokens(source_text)

        for section_name, bullet in self._iter_tailored_bullets(tailored_resume):
            claim = str(bullet.get("text", "")).strip()
            if not claim:
                continue

            evidence_from = str(bullet.get("evidence_from") or "").strip()
            original_text = str(bullet.get("original_text") or "").strip()
            if not evidence_from and not original_text:
                issues.append(f"{section_name}: missing evidence_from/original_text for claim: {claim[:140]}")

            missing_numbers = sorted(self._numbers(claim) - source_numbers)
            if missing_numbers:
                issues.append(
                    f"{section_name}: claim adds unsupported metric(s) {', '.join(missing_numbers)}: {claim[:140]}"
                )

            evidence_text = original_text or source_text
            evidence_tokens = self._tokens(evidence_text) or source_tokens
            claim_tokens = self._tokens(claim)
            if claim_tokens:
                overlap = len(claim_tokens & evidence_tokens) / max(1, min(len(claim_tokens), len(evidence_tokens)))
                if overlap < 0.15:
                    issues.append(f"{section_name}: weak textual support for claim: {claim[:140]}")

        passed = not issues
        return {
            "passed": passed,
            "issues": issues,
            "confidence": 0.9 if passed else 0.55,
        }

    def _collect_source_text(self, value: object) -> str:
        parts: list[str] = []

        def walk(item: object) -> None:
            if isinstance(item, str):
                if item.strip():
                    parts.append(item.strip())
            elif isinstance(item, dict):
                for child in item.values():
                    walk(child)
            elif isinstance(item, list):
                for child in item:
                    walk(child)

        walk(value)
        return "\n".join(parts)

    def _iter_tailored_bullets(self, tailored_resume: dict):
        for section_name in ["experiences", "projects", "competitions"]:
            for item in tailored_resume.get(section_name, []) or []:
                if not isinstance(item, dict):
                    continue
                for bullet in item.get("bullets", []) or []:
                    if isinstance(bullet, dict):
                        yield section_name, bullet
                    else:
                        yield section_name, {"text": str(bullet)}

    def _tokens(self, text: str) -> set[str]:
        stopwords = {
            "and", "for", "with", "the", "that", "this", "from", "into", "using",
            "through", "across", "within", "while", "were", "was", "are", "you",
            "your", "resume", "experience", "project", "team", "role",
        }
        return {
            token
            for token in re.findall(r"[a-zA-Z][a-zA-Z0-9+#.-]{2,}", text.lower())
            if token not in stopwords
        }

    def _numbers(self, text: str) -> set[str]:
        return set(re.findall(r"(?:\$\s*)?\b\d+(?:\.\d+)?\s*(?:%|k|m|b|x)?\b", text.lower()))
