"""Phase 2b: rewrite kept bullets to align with JD terminology.

Zero-fabrication contract: rewriting may only change wording/phrasing to
match JD synonyms. It must never escalate the claimed scope of involvement
("participated in" -> "led") or add anything not already true of the
original bullet. A mechanical intensity check runs on every rewrite; any
escalation is rejected and the original text is kept unchanged rather than
silently applied.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from app.core.llm_client import get_chat_openai
from app.modules.job_discovery.scorer import tokenize

log = logging.getLogger(__name__)

# Ownership-intensity ladder, low -> high. A rewrite may move sideways within
# a tier or remain silent about intensity, but must never jump to a higher
# tier than the original bullet already claimed.
_INTENSITY_TIERS: list[set[str]] = [
    {
        "participated", "assisted", "helped", "contributed", "supported",
        "involved", "参与", "协助", "支持", "参加", "配合",
    },
    {
        "built", "developed", "implemented", "created", "designed", "wrote",
        "maintained", "integrated", "improved", "构建", "开发", "实现",
        "设计", "编写", "维护", "优化", "改进",
    },
    {
        "led", "drove", "owned", "architected", "spearheaded", "directed",
        "managed", "initiated", "established", "founded", "主导", "负责",
        "领导", "驱动", "建立", "发起", "统筹",
    },
]

_SYSTEM_PROMPT = """You rewrite a resume bullet's WORDING to better match a job description's \
terminology, without changing what actually happened.

STRICT RULES:
1. You may swap generic phrasing to match JD terminology (e.g. "web framework" -> "backend
   framework" if the JD says "backend").
2. NEVER remove, rename, or replace a specific named technology, tool, or component that's
   already in the original (e.g. if the original says "FastAPI" or "Evidence Guard module",
   the rewrite must keep saying "FastAPI" / "Evidence Guard module" — do not swap a named,
   specific thing for a generic JD keyword just because the JD keyword sounds relevant).
3. NEVER escalate the level of ownership or scope. If the original says the person
   "participated in" or "helped with" something, the rewrite must not say "led" or "owned" it.
4. NEVER add numbers, percentages, team sizes, or outcomes that are not already in the
   original text.
5. Keep it to one sentence, same rough length as the original.
6. Output ONLY the rewritten sentence, nothing else — no quotes, no preamble.
"""

_BATCH_SYSTEM_PROMPT = """You rewrite multiple resume bullets' WORDING to better match a job \
description's terminology, without changing what actually happened.

STRICT RULES (apply to EVERY bullet):
1. You may swap generic phrasing to match JD terminology.
2. NEVER remove, rename, or replace a specific named technology/tool/component already in
   the original.
3. NEVER escalate ownership/scope ("participated" must not become "led").
4. NEVER add numbers, percentages, team sizes, or outcomes not already in the original.
5. Keep each rewrite to one sentence, same rough length as the original.
6. Output ONLY a JSON array, one object per input id, nothing else:
   [{"id": str, "rewritten": str}, ...]
"""


@dataclass
class RewriteResult:
    original: str
    rewritten: str
    applied: bool          # False if rejected (intensity escalation) — original text stands
    reject_reason: str | None
    keyword_score_before: int
    keyword_score_after: int


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_PROPER_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#./-]*")


def _named_terms(text: str) -> set[str]:
    """Distinctive named technologies/components: capitalized tokens that are NOT the
    first word of their sentence, merged into runs (so "Evidence Guard" survives as one
    unit, not two). This is what stops a rewrite from silently swapping a real, specific
    thing (FastAPI, Evidence Guard module) for a generic JD buzzword.
    """
    terms: set[str] = set()
    for sentence in _SENTENCE_SPLIT_RE.split(text):
        tokens = _PROPER_TOKEN_RE.findall(sentence)
        run: list[str] = []
        for i, tok in enumerate(tokens):
            title_case = tok[:1].isupper() and not tok.isupper()
            multi_char_acronym = tok.isupper() and len(tok) > 1
            is_capitalized = title_case or multi_char_acronym
            if i == 0:
                continue  # sentence-initial capitalization is just grammar, not a proper noun
            if is_capitalized:
                run.append(tok)
            else:
                if run:
                    terms.add(" ".join(run))
                run = []
        if run:
            terms.add(" ".join(run))
    # Drop single common words that happen to get capitalized (e.g. after a colon)
    return {t for t in terms if len(t) > 2}


def _max_tier(text: str) -> int | None:
    """Highest ownership-intensity tier detected in `text`, or None if no marker word found."""
    words = set(re.findall(r"[a-zA-Z一-鿿]+", text.lower()))
    highest = None
    for tier_index, tier_words in enumerate(_INTENSITY_TIERS):
        if words & tier_words:
            highest = tier_index
    return highest


def _keyword_match_score(text: str, jd_keywords: set[str]) -> int:
    return len(tokenize(text) & jd_keywords)


def _jd_kw_tokens(jd_required_skills: list[str], jd_keywords: list[str]) -> set[str]:
    jd_terms = set(jd_required_skills) | set(jd_keywords)
    tokens: set[str] = set()
    for term in jd_terms:
        tokens |= tokenize(term)
    return tokens


def finalize_rewrite(
    *,
    bullet_text: str,
    rewritten: str,
    jd_required_skills: list[str],
    jd_keywords: list[str],
) -> RewriteResult:
    """Mechanical post-checks shared by single and batch rewrite paths."""
    rewritten = str(rewritten or "").strip().strip('"')
    jd_kw_tokens = _jd_kw_tokens(jd_required_skills, jd_keywords)
    before_score = _keyword_match_score(bullet_text, jd_kw_tokens)
    after_score = _keyword_match_score(rewritten, jd_kw_tokens)

    original_tier = _max_tier(bullet_text)
    rewritten_tier = _max_tier(rewritten)
    escalated = (
        original_tier is not None
        and rewritten_tier is not None
        and rewritten_tier > original_tier
    )

    original_named_terms = _named_terms(bullet_text)
    rewritten_named_terms = _named_terms(rewritten)
    dropped_terms = {t for t in original_named_terms if t not in rewritten_named_terms}

    if escalated or dropped_terms or not rewritten:
        if escalated:
            reason = (
                "改写后的措辞把参与程度从低往高拔高了(比如“参与”被改成了“主导”),"
                "按零编造规则拒绝,保留原文"
            )
        elif dropped_terms:
            dropped_str = ", ".join(sorted(dropped_terms))
            reason = (
                f"改写后丢失/替换掉了原文里具体的专有名词或技术名称({dropped_str}),"
                "疑似被替换成了泛化的JD关键词,按零编造规则拒绝,保留原文"
            )
        else:
            reason = "模型未返回有效改写,保留原文"
        return RewriteResult(
            original=bullet_text,
            rewritten=bullet_text,
            applied=False,
            reject_reason=reason,
            keyword_score_before=before_score,
            keyword_score_after=before_score,
        )

    return RewriteResult(
        original=bullet_text,
        rewritten=rewritten,
        applied=True,
        reject_reason=None,
        keyword_score_before=before_score,
        keyword_score_after=after_score,
    )


def rewrite_bullet(
    *, bullet_text: str, jd_required_skills: list[str], jd_keywords: list[str]
) -> RewriteResult:
    jd_terms = set(jd_required_skills) | set(jd_keywords)
    jd_terms_str = ", ".join(sorted(jd_terms)) or "(none)"
    user_prompt = f"""JD terminology to align with (skills + keywords): {jd_terms_str}

Original bullet:
{bullet_text}

Rewrite it per the system rules. Output only the rewritten sentence."""

    llm = get_chat_openai(temperature=0.0, max_tokens=2000)
    response = llm.invoke([
        ("system", _SYSTEM_PROMPT),
        ("human", user_prompt),
    ])
    rewritten = str(response.content).strip().strip('"')
    return finalize_rewrite(
        bullet_text=bullet_text,
        rewritten=rewritten,
        jd_required_skills=jd_required_skills,
        jd_keywords=jd_keywords,
    )


def _parse_json_array(text: str) -> list[dict]:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if not match:
            return []
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []
    return data if isinstance(data, list) else []


_SECTION_LABELS = {
    "experiences": "Professional Experience",
    "projects": "Projects",
    "competitions": "Competitions / Awards",
    "skills": "Skills",
    "summary": "Professional Summary",
}


async def rewrite_bullets_batch(
    *,
    bullets: list[tuple[str, str]],
    jd_required_skills: list[str],
    jd_keywords: list[str],
    model: str | None = None,
    provider: str | None = None,
    section: str | None = None,
) -> dict[str, RewriteResult]:
    """Rewrite many bullets in one async LLM call (one module batch).

    `bullets` is a list of (bullet_id, original_text). Returns id -> RewriteResult.
    Missing/invalid model rows fall back to keeping the original.
    """
    if not bullets:
        return {}

    jd_terms = set(jd_required_skills) | set(jd_keywords)
    jd_terms_str = ", ".join(sorted(jd_terms)) or "(none)"
    items_block = "\n".join(
        f'- id={bid}: {text}' for bid, text in bullets if str(text or "").strip()
    )
    if not items_block:
        return {
            bid: finalize_rewrite(
                bullet_text=text,
                rewritten=text,
                jd_required_skills=jd_required_skills,
                jd_keywords=jd_keywords,
            )
            for bid, text in bullets
        }

    module = _SECTION_LABELS.get(section or "", section or "Resume bullets")
    user_prompt = f"""Resume module: {module}
JD terminology to align with (skills + keywords): {jd_terms_str}

Bullets to rewrite in this module only (judge ONLY these, by their exact id):
{items_block}

Output a JSON array with exactly one object per id listed above."""

    by_id: dict[str, RewriteResult] = {}
    try:
        llm_kwargs: dict = {"temperature": 0.0, "max_tokens": 8000}
        if model:
            llm_kwargs["model"] = model
        if provider:
            llm_kwargs["provider"] = provider
        llm = get_chat_openai(**llm_kwargs)
        response = await llm.ainvoke([
            ("system", _BATCH_SYSTEM_PROMPT),
            ("human", user_prompt),
        ])
        raw = _parse_json_array(str(response.content))
        mapped = {
            str(entry.get("id", "")).strip(): str(entry.get("rewritten", "")).strip()
            for entry in raw
            if isinstance(entry, dict)
        }
        for bid, original in bullets:
            rewritten = mapped.get(bid, "")
            by_id[bid] = finalize_rewrite(
                bullet_text=original,
                rewritten=rewritten,
                jd_required_skills=jd_required_skills,
                jd_keywords=jd_keywords,
            )
    except Exception as exc:
        log.warning(
            "batch bullet rewrite failed section=%s (%s); keeping originals",
            section or "?",
            exc,
        )
        for bid, original in bullets:
            jd_kw = _jd_kw_tokens(jd_required_skills, jd_keywords)
            before = _keyword_match_score(original, jd_kw)
            by_id[bid] = RewriteResult(
                original=original,
                rewritten=original,
                applied=False,
                reject_reason=f"batch rewrite failed: {exc}",
                keyword_score_before=before,
                keyword_score_after=before,
            )
    # Any id the model skipped: keep original (fail closed on wording, not content loss)
    for bid, original in bullets:
        if bid not in by_id:
            by_id[bid] = finalize_rewrite(
                bullet_text=original,
                rewritten=original,
                jd_required_skills=jd_required_skills,
                jd_keywords=jd_keywords,
            )
    return by_id
