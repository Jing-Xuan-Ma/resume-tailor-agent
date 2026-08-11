"""Phase 2a: decide which experience items to keep/drop for a given JD.

Zero-fabrication contract: the LLM never introduces new experience content —
it only scores and annotates items it was actually handed. Every returned
decision is mechanically checked against the real input id set; anything
that doesn't match a real item is dropped, not trusted.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.core.llm_client import get_chat_openai

_MAX_ITEMS = 60

_SYSTEM_PROMPT = """You are scoring which pieces of a candidate's experience should be kept \
or dropped for a specific job description.

STRICT RULES:
1. You may ONLY judge the items given to you by their exact "id". Never invent a new
   experience, never merge two items into a new claim, never add a technology or
   accomplishment that isn't already in the item's text.
2. For each input id, output exactly one decision: "keep" or "drop".
3. relevance_score is a float from 0.0 (irrelevant) to 1.0 (directly required by the JD).
4. reason must be one plain-language sentence a human can read and agree/disagree with —
   not a restatement of the score, an actual reason ("JD asks for React; this item is
   backend-only Python/FastAPI work").
5. Do not judge quality ("well done", "impressive") — only relevance to THIS job description.
6. Output ONLY a JSON array, one object per input id, nothing else:
   [{"id": str, "decision": "keep"|"drop", "relevance_score": float, "reason": str}, ...]
"""


@dataclass
class ExperienceItem:
    id: str
    text: str
    source: str = "unknown"


@dataclass
class Decision:
    item_id: str
    decision: str
    relevance_score: float
    reason: str


def _parse_json_array(text: str) -> list[dict]:
    text = text.strip()
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


def _build_score_prompt(
    *,
    jd_title: str,
    jd_required_skills: list[str],
    jd_keywords: list[str],
    items: list[ExperienceItem],
) -> str:
    items_block = "\n".join(f"- id={item.id}: {item.text}" for item in items)
    return f"""Job title: {jd_title}
Required skills: {', '.join(jd_required_skills) or '(none listed)'}
Keywords: {', '.join(jd_keywords) or '(none listed)'}

Candidate experience items (judge ONLY these, by their exact id):
{items_block}

Output a JSON array with exactly one decision object per id listed above."""


def _decisions_from_raw(raw: list[dict], items: list[ExperienceItem]) -> list[Decision]:
    valid_ids = {item.id for item in items}
    seen: set[str] = set()
    decisions: list[Decision] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        item_id = str(entry.get("id", "")).strip()
        decision = str(entry.get("decision", "")).strip().lower()
        if item_id not in valid_ids:
            continue  # hallucinated id — not something we handed the model, drop it
        if decision not in {"keep", "drop"}:
            continue
        reason = str(entry.get("reason", "")).strip()
        if decision == "drop" and not reason:
            continue  # spec requires a human-readable reason for every drop
        try:
            score = float(entry.get("relevance_score", 0.0))
        except (TypeError, ValueError):
            score = 0.0
        score = max(0.0, min(1.0, score))
        decisions.append(
            Decision(item_id=item_id, decision=decision, relevance_score=score, reason=reason)
        )
        seen.add(item_id)

    # Any item the model silently skipped: fail closed as "keep" (never silently
    # discard real experience content the model forgot to rule on) with a note.
    for item in items:
        if item.id not in seen:
            decisions.append(Decision(
                item_id=item.id, decision="keep", relevance_score=0.0,
                reason="模型未对该条给出判断,按“找不到证据不删”原则默认保留,建议人工复核。",
            ))
    return decisions


def score_experience_items(
    *,
    jd_title: str,
    jd_required_skills: list[str],
    jd_keywords: list[str],
    items: list[ExperienceItem],
) -> list[Decision]:
    if not items:
        return []
    if len(items) > _MAX_ITEMS:
        items = items[:_MAX_ITEMS]

    user_prompt = _build_score_prompt(
        jd_title=jd_title,
        jd_required_skills=jd_required_skills,
        jd_keywords=jd_keywords,
        items=items,
    )
    llm = get_chat_openai(temperature=0.0, max_tokens=8000)
    response = llm.invoke([
        ("system", _SYSTEM_PROMPT),
        ("human", user_prompt),
    ])
    return _decisions_from_raw(_parse_json_array(response.content), items)


async def ascore_experience_items(
    *,
    jd_title: str,
    jd_required_skills: list[str],
    jd_keywords: list[str],
    items: list[ExperienceItem],
) -> list[Decision]:
    """Async variant — does not block the event loop (needed for true batch concurrency)."""
    if not items:
        return []
    if len(items) > _MAX_ITEMS:
        items = items[:_MAX_ITEMS]

    user_prompt = _build_score_prompt(
        jd_title=jd_title,
        jd_required_skills=jd_required_skills,
        jd_keywords=jd_keywords,
        items=items,
    )
    llm = get_chat_openai(temperature=0.0, max_tokens=8000)
    response = await llm.ainvoke([
        ("system", _SYSTEM_PROMPT),
        ("human", user_prompt),
    ])
    return _decisions_from_raw(_parse_json_array(response.content), items)
