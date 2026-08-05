"""Screener question answering with dual-LLM anti-fabrication guard."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from app.modules.form_fill_engine.schemas import InteractiveElement, ScreenerAnswer

log = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def _collect_facts_text(resume_facts: dict[str, Any]) -> str:
    parts: list[str] = []

    def walk(item: object, depth: int = 0) -> None:
        if depth > 8:
            return
        if isinstance(item, str):
            if item.strip():
                parts.append(item.strip())
        elif isinstance(item, dict):
            for v in item.values():
                walk(v, depth + 1)
        elif isinstance(item, list):
            for v in item:
                walk(v, depth + 1)

    walk(resume_facts)
    return "\n".join(parts[:200])


def _heuristic_draft(question: str, resume_facts: dict[str, Any]) -> tuple[str, list[str]]:
    """Offline draft when LLM unavailable — only reuse explicit profile/resume strings."""
    q = question.lower()
    sources: list[str] = []
    facts = resume_facts or {}

    def pick(*keys: str) -> str:
        for k in keys:
            v = facts.get(k)
            if v not in (None, ""):
                sources.append(f"{k}: {v}")
                return str(v)
        return ""

    if any(w in q for w in ("years of experience", "how many years", "years experience")):
        for key in ("years_experience", "experience_years", "yoe"):
            if facts.get(key) not in (None, ""):
                return str(facts[key]), [f"{key}: {facts[key]}"]
        return "", []

    if "authorize" in q or "work authorization" in q:
        v = pick("work_authorized", "work_authorization")
        if v:
            return v if v in {"Yes", "No"} else ("Yes" if str(v).lower() in {"true", "1", "yes"} else "No"), sources

    if "sponsor" in q:
        v = pick("needs_sponsorship")
        if v:
            return v if v in {"Yes", "No"} else ("Yes" if str(v).lower() in {"true", "1", "yes"} else "No"), sources

    # Prefer leaving empty rather than fabricating prose
    return "", sources


async def generate_draft_answer(
    question: str,
    resume_facts: dict[str, Any],
    *,
    tone: str = "professional",
) -> tuple[str, list[str]]:
    facts_text = _collect_facts_text(resume_facts)
    if not facts_text.strip():
        draft, sources = _heuristic_draft(question, resume_facts)
        return draft, sources

    try:
        from app.core.llm_client import get_chat_openai
        from langchain_core.messages import HumanMessage, SystemMessage

        system = (
            "You answer job application screener questions using ONLY the provided resume facts. "
            "Never invent employers, metrics, skills, degrees, or dates. "
            "If facts are insufficient, return an empty answer string. "
            f"Tone: {tone}. "
            'Respond with JSON: {"answer": "...", "cited_facts": ["exact quote", ...]}'
        )
        llm = get_chat_openai(temperature=0.2, max_tokens=512)
        resp = await llm.ainvoke(
            [
                SystemMessage(content=system),
                HumanMessage(
                    content=json.dumps(
                        {"question": question, "resume_facts": facts_text[:8000]},
                        ensure_ascii=False,
                    )
                ),
            ]
        )
        raw = str(getattr(resp, "content", "") or "").strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        answer = str(data.get("answer") or "").strip()
        cited = [str(x) for x in (data.get("cited_facts") or []) if str(x).strip()]
        return answer, cited
    except Exception as exc:
        log.debug("screener draft LLM unavailable: %s", exc)
        return _heuristic_draft(question, resume_facts)


async def verify_evidence(
    draft: str,
    resume_facts: dict[str, Any],
    *,
    question: str = "",
) -> dict[str, Any]:
    """Independent evidence check (LLM call 2) + deterministic number/token overlap."""
    if not draft.strip():
        return {"passed": False, "cited_facts": [], "issues": ["empty answer"]}

    source = _collect_facts_text(resume_facts)
    cited: list[str] = []
    issues: list[str] = []

    # Deterministic: numbers in draft must appear in source
    draft_nums = set(re.findall(r"(?:\$\s*)?\b\d+(?:\.\d+)?\s*(?:%|k|m|b|x)?\b", draft.lower()))
    source_nums = set(re.findall(r"(?:\$\s*)?\b\d+(?:\.\d+)?\s*(?:%|k|m|b|x)?\b", source.lower()))
    unsupported = sorted(draft_nums - source_nums)
    if unsupported:
        issues.append(f"unsupported metrics: {', '.join(unsupported)}")

    # Token overlap heuristic
    stop = {"and", "the", "for", "with", "that", "this", "from", "you", "your", "have", "will"}
    d_tok = {t for t in re.findall(r"[a-z][a-z0-9+#.-]{2,}", draft.lower()) if t not in stop}
    s_tok = {t for t in re.findall(r"[a-z][a-z0-9+#.-]{2,}", source.lower()) if t not in stop}
    if d_tok and s_tok:
        overlap = len(d_tok & s_tok) / max(1, min(len(d_tok), len(s_tok)))
        if overlap < 0.12 and len(draft.split()) > 8:
            issues.append("weak textual support vs resume facts")

    # Optional LLM verify (reuse evidence_check spirit)
    try:
        from app.core.llm_client import get_chat_openai
        from langchain_core.messages import HumanMessage, SystemMessage

        prompt_path = _PROMPTS_DIR / "screener_evidence_check.txt"
        if prompt_path.exists():
            system = prompt_path.read_text(encoding="utf-8")
        else:
            system = (
                "Verify the screener answer is fully supported by resume facts. "
                'Return JSON: {"passed": bool, "cited_facts": [str], "issues": [str]}. '
                "Any fabricated claim → passed=false."
            )
        llm = get_chat_openai(temperature=0.1, max_tokens=512)
        resp = await llm.ainvoke(
            [
                SystemMessage(content=system),
                HumanMessage(
                    content=json.dumps(
                        {
                            "question": question,
                            "answer": draft,
                            "resume_facts": source[:8000],
                        },
                        ensure_ascii=False,
                    )
                ),
            ]
        )
        raw = str(getattr(resp, "content", "") or "").strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        if data.get("passed") is False:
            issues.extend([str(x) for x in (data.get("issues") or [])])
        cited = [str(x) for x in (data.get("cited_facts") or []) if str(x).strip()]
        if data.get("passed") is True and not issues:
            return {"passed": True, "cited_facts": cited, "issues": []}
    except Exception as exc:
        log.debug("screener evidence LLM skip: %s", exc)

    passed = not issues
    if passed and not cited:
        # Use overlapping sentences as weak citations
        for line in source.splitlines():
            line = line.strip()
            if len(line) > 20 and any(t in line.lower() for t in list(d_tok)[:5]):
                cited.append(line[:200])
                if len(cited) >= 3:
                    break
    return {"passed": passed, "cited_facts": cited, "issues": issues}


async def answer_screener_question(
    question: str,
    resume_facts: dict[str, Any],
    *,
    element_index: int = -1,
    tone: str = "professional",
) -> ScreenerAnswer:
    draft, draft_sources = await generate_draft_answer(question, resume_facts, tone=tone)
    if not draft.strip():
        return ScreenerAnswer(
            element_index=element_index,
            question_text=question,
            generated_answer="",
            evidence_check_passed=False,
            evidence_sources=draft_sources,
            needs_human_review=True,
        )
    check = await verify_evidence(draft, resume_facts, question=question)
    sources = list(check.get("cited_facts") or []) or draft_sources
    passed = bool(check.get("passed"))
    return ScreenerAnswer(
        element_index=element_index,
        question_text=question,
        generated_answer=draft,
        evidence_check_passed=passed,
        evidence_sources=sources,
        needs_human_review=not passed,
    )


def is_likely_screener(element: InteractiveElement, mapped_key: str | None = None) -> bool:
    """Heuristic: unmatched text/textarea/radio questions look like screeners."""
    if mapped_key:
        return False
    tag = (element.tag or "").lower()
    etype = (element.element_type or "").lower()
    if tag == "button":
        return False
    if etype in {"file", "hidden", "submit", "password"}:
        return False
    label = (element.label or "").strip()
    if len(label) < 12:
        return False
    # Profile-like short fields already handled by mapper
    if tag in {"textarea"} or etype in {"text", "textarea"} or tag == "select":
        q_markers = (
            "?",
            "describe",
            "why",
            "tell us",
            "experience",
            "how many",
            "are you",
            "do you",
            "have you",
            "explain",
            "additional",
        )
        low = label.lower()
        if any(m in low for m in q_markers) or len(label) > 40:
            return True
    return False
