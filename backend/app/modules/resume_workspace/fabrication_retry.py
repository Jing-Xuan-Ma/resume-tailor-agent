"""Phase 2d: when the evidence guard flags a claim, route it back through the
Phase 2a decision engine instead of silently deleting it from the resume.

A flagged claim isn't just dropped in place — it goes through the same
accountable, logged keep/drop decision process as any other candidate, so
there's always a traceable reason attached to why content left the resume.
"""

from __future__ import annotations

from app.modules.resume_workspace.decision_engine import (
    Decision,
    ExperienceItem,
    ascore_experience_items,
)


def extract_flagged_claim_texts(issues: list[str]) -> list[str]:
    """Pull the (possibly truncated) claim text back out of evidence-guard issue strings.

    Every issue string ends with ": <claim text>" (see evidence_guard.py) — the
    claim itself may contain no colons, but the section/reason prefix before it
    often does (e.g. "experiences: claim adds unsupported metric(s) 95% : ...
    text"), so this splits on the LAST colon, not the first.

    Deduplicated: the heuristic pass and the LLM pass can both flag the same
    claim independently, and re-running Phase 2a twice on an identical claim
    is wasted work, not extra safety.
    """
    claims: list[str] = []
    seen: set[str] = set()
    for issue in issues:
        if ":" not in issue:
            continue
        claim = issue.rsplit(":", 1)[-1].strip()
        if claim and claim not in seen:
            seen.add(claim)
            claims.append(claim)
    return claims


async def rerun_flagged_claims_through_phase_2a(
    *,
    flagged_claim_texts: list[str],
    jd_title: str,
    jd_required_skills: list[str],
    jd_keywords: list[str],
) -> list[Decision]:
    """Re-run Phase 2a's decision engine on exactly the flagged claims.

    This is deliberately synchronous with Phase 2a's own contract: every
    outcome is a logged Decision with a reason, not a silent list.remove().
    A flagged claim will almost always come back "drop" (it failed fact-check,
    so it should not appear on the resume) — but it comes back as a *decision*
    with a reason, traceable the same way every other keep/drop call is.
    """
    if not flagged_claim_texts:
        return []
    items = [
        ExperienceItem(id=f"flagged-{i}", text=text, source="evidence_guard_flag")
        for i, text in enumerate(flagged_claim_texts)
    ]
    decisions = await ascore_experience_items(
        jd_title=jd_title,
        jd_required_skills=jd_required_skills,
        jd_keywords=jd_keywords,
        items=items,
    )
    # Belt and suspenders: a flagged claim must never silently survive as "keep"
    # just because Phase 2a's own model call had a different opinion — the
    # evidence guard's rejection is final for this specific claim.
    forced: list[Decision] = []
    for d in decisions:
        if d.decision == "keep":
            forced.append(Decision(
                item_id=d.item_id, decision="drop", relevance_score=d.relevance_score,
                reason=(
                    "证据核查已标记为无法溯源/编造,即使二次评分认为相关也强制删除: "
                    + d.reason
                ),
            ))
        else:
            forced.append(d)
    return forced
