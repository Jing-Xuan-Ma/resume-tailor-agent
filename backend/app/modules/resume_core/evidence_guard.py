"""
Evidence Guard Node — Independent fact-checker that verifies tailored claims.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.config import settings
from app.core.llm_client import get_chat_openai


class EvidenceGuardNode:
    """
    Verifies that every claim in the tailored resume is supported by
    the user's original experiences. Flags hallucinations.
    """

    def __init__(self):
        self._llm = None
        prompt_path = Path(__file__).parent / "prompts" / "evidence_check.txt"
        self.system_prompt = prompt_path.read_text(encoding="utf-8")

    def _get_llm(self):
        if self._llm is None:
            self._llm = get_chat_openai(
                model=settings.DEFAULT_TAILOR_MODEL,
                temperature=0.1,
                # Reasoning models can burn the whole budget on internal reasoning
                # before writing output (bit us in Phase 2-pre); a multi-claim batch
                # with a quoted original_support per finding needs real headroom too.
                max_tokens=8000,
            )
        return self._llm

    async def verify(self, original_resume: dict, tailored_resume: dict) -> dict:
        """
        Returns verification result with 'passed' boolean and list of issues.

        Two independent passes, either one failing fails the whole check:
        1. Fast heuristics (number/token overlap) — catches obvious cases cheaply.
        2. An actual independent LLM call against evidence_check.txt — catches
           claims that reuse enough real vocabulary to slip past heuristics
           (e.g. "negotiated executive buy-in for company-wide rollout" built
           entirely out of words lifted from a real, unrelated bullet).
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
        claims: list[tuple[str, str]] = []

        for section_name, bullet in self._iter_tailored_bullets(tailored_resume):
            claim = str(bullet.get("text", "")).strip()
            if not claim:
                continue
            claims.append((section_name, claim))

            evidence_from = str(bullet.get("evidence_from") or "").strip()
            original_text = str(bullet.get("original_text") or "").strip()
            if not evidence_from and not original_text:
                issues.append(
                    f"{section_name}: missing evidence_from/original_text for claim: {claim[:140]}"
                )

            missing_numbers = sorted(self._numbers(claim) - source_numbers)
            if missing_numbers:
                numbers_str = ", ".join(missing_numbers)
                issues.append(
                    f"{section_name}: claim adds unsupported metric(s) {numbers_str}: {claim[:140]}"
                )

            evidence_text = original_text or source_text
            evidence_tokens = self._tokens(evidence_text) or source_tokens
            claim_tokens = self._tokens(claim)
            if claim_tokens:
                shorter_len = min(len(claim_tokens), len(evidence_tokens))
                overlap = len(claim_tokens & evidence_tokens) / max(1, shorter_len)
                if overlap < 0.15:
                    issues.append(f"{section_name}: weak textual support for claim: {claim[:140]}")

        llm_result = await self._llm_fact_check(source_text, claims)
        if llm_result is not None:
            issues.extend(llm_result["issues"])

        passed = not issues
        return {
            "passed": passed,
            "issues": issues,
            "confidence": 0.9 if passed else 0.55,
        }

    async def _llm_fact_check(
        self, source_text: str, claims: list[tuple[str, str]]
    ) -> dict | None:
        """Independent LLM pass per evidence_check.txt. Returns None (skip, not pass)
        if the model call itself fails — a broken LLM call must never silently count
        as "verified"; the heuristic pass above still applies regardless.

        Every claim gets a stable id and MUST get exactly one finding back. A claim
        the model silently drops from its findings list is NOT treated as reviewed —
        it fails closed as unverifiable, the same fail-closed rule used in the Phase
        2a decision engine for ids the model forgets to rule on. Without this, a
        multi-claim batch can let one fabricated claim slip through un-reviewed
        while the model dutifully classifies the others (observed in dogfooding).
        """
        if not claims:
            return {"issues": []}
        indexed = list(enumerate(claims))
        claims_block = "\n".join(
            f'- id={i}: [{section}] {claim}' for i, (section, claim) in indexed
        )
        user_prompt = f"""ORIGINAL resume (source of truth):
{source_text}

TAILORED resume claims to review, each with a stable id:
{claims_block}

Review EVERY claim above and return the JSON object per your instructions, with one
addition: each object in "findings" MUST include an "id" field copied verbatim from
the id shown above for that claim. You must return exactly one finding per id listed —
do not skip any, do not merge two ids into one finding."""

        # Transient provider/formatting hiccups happen; retry once before failing
        # closed so a flaky response doesn't spuriously block every other run.
        findings_by_id: dict[str, dict] = {}
        for _attempt in range(2):
            try:
                llm = self._get_llm()
                response = await llm.ainvoke([
                    ("system", self.system_prompt),
                    ("human", user_prompt),
                ])
                data = self._parse_json_object(str(response.content))
            except Exception:
                data = None
            if data is not None:
                for finding in data.get("findings") or []:
                    if not isinstance(finding, dict):
                        continue
                    finding_id = str(finding.get("id", "")).strip()
                    if finding_id:
                        findings_by_id[finding_id] = finding
            if all(str(i) in findings_by_id for i, _ in indexed):
                break  # every claim covered — no need for a second attempt

        issues: list[str] = []
        for i, (section, claim) in indexed:
            finding = findings_by_id.get(str(i))
            if finding is None:
                issues.append(
                    f"{section}: llm_fact_check did not return a verdict for this claim "
                    f"after retry (fails closed, not treated as verified): {claim[:140]}"
                )
                continue
            classification = str(finding.get("classification", "")).upper()
            if classification == "FABRICATED":
                issues.append(f"{section}: llm_fact_check FABRICATED claim: {claim[:140]}")
            elif classification not in {"SUPPORTED", "EXAGGERATED", "AMBIGUOUS"}:
                issues.append(
                    f"{section}: llm_fact_check returned an unrecognized classification "
                    f"'{finding.get('classification')}' (fails closed): {claim[:140]}"
                )
        return {"issues": issues}

    @staticmethod
    def _parse_json_object(text: str) -> dict | None:
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if not match:
                return None
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
        return data if isinstance(data, dict) else None

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
