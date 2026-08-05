"""Rule-based outreach candidate scoring from LinkedIn-public signals.

Weights (design plan §3.1):
  title keywords 35% | team affinity 25% | activity 15% | seniority 15% | company-size 10%

No external APIs — only fields the user pastes (name, title, snippet, recent activity notes).
"""

from __future__ import annotations

import re
from typing import Any

TITLE_HIRING = re.compile(
    r"\b(hiring\s+manager|talent\s+acquisition|recruiter|people\s+ops|"
    r"head\s+of\s+(?:data|analytics|people)|director\s+of\s+(?:data|analytics)|"
    r"analytics\s+manager|data\s+(?:manager|lead|director)|team\s+lead|"
    r"engineering\s+manager)\b",
    re.I,
)
TITLE_RECRUITER = re.compile(r"\b(recruiter|talent\s+acquisition|sourcer|staffing)\b", re.I)
TITLE_HM = re.compile(
    r"\b(hiring\s+manager|head\s+of|director|manager|team\s+lead|lead)\b",
    re.I,
)
TITLE_GENERIC_TA = re.compile(r"\b(talent\s+acquisition\s+(?:specialist|coordinator|associate))\b", re.I)
TITLE_DOMAIN = re.compile(r"\b(data|analytics|analyst|bi|business\s+intelligence|ml|ai)\b", re.I)
HIRING_ACTIVITY = re.compile(
    r"\b(hiring|we'?re\s+hiring|open\s+role|looking\s+for|join\s+(?:our|my)\s+team|"
    r"now\s+hiring|job\s+opening)\b",
    re.I,
)
DEPT_HINTS = re.compile(
    r"\b((?:data|analytics|product|engineering|growth|risk|finance|ops|operations|"
    r"marketing|platform|infrastructure)\s+(?:team|org|organization|group|department|"
    r"division)?|(?:team|dept|department|org)\s+[A-Z][a-zA-Z0-9 &\-]{2,40})\b",
    re.I,
)


def extract_jd_signals(jd_text: str = "", position: str = "") -> dict[str, Any]:
    """Lightweight NLP: department clues + role keywords from JD / position title."""
    blob = f"{position or ''}\n{jd_text or ''}".strip()
    depts = sorted({m.group(0).strip() for m in DEPT_HINTS.finditer(blob)})[:8]
    domain_terms = sorted({m.group(0).lower() for m in TITLE_DOMAIN.finditer(blob)})
    return {
        "departments": depts,
        "domain_terms": domain_terms,
        "position": (position or "").strip(),
        "jd_chars": len(jd_text or ""),
    }


def _clamp(n: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, n))


def _title_score(title: str, jd: dict[str, Any]) -> tuple[float, list[str]]:
    reasons: list[str] = []
    t = (title or "").strip()
    if not t:
        return 20.0, ["No title provided — score is a weak estimate"]

    score = 30.0
    if TITLE_HM.search(t) and not TITLE_RECRUITER.search(t):
        score = 92.0
        reasons.append('Title matches Hiring Manager / team lead pattern')
    elif TITLE_RECRUITER.search(t):
        score = 78.0
        reasons.append("Title matches Recruiter / Talent Acquisition")
        if TITLE_GENERIC_TA.search(t):
            score = 58.0
            reasons.append("Generic TA title often has lower reply rates")
    elif TITLE_HIRING.search(t):
        score = 70.0
        reasons.append("Title related to hiring / people ops")

    domain_hit = False
    for term in jd.get("domain_terms") or []:
        if term and re.search(rf"\b{re.escape(term)}\b", t, re.I):
            domain_hit = True
            break
    if not domain_hit and TITLE_DOMAIN.search(t):
        domain_hit = True
    if domain_hit:
        score = _clamp(score + 8)
        reasons.append("Title includes Data / Analytics domain words")

    pos = (jd.get("position") or "").lower()
    if pos:
        first = pos.split()[0]
        if len(first) > 3 and first in t.lower():
            score = _clamp(score + 5)
            reasons.append(f'Title overlaps position keyword "{first}"')

    if not reasons:
        reasons.append("Title does not clearly match hiring roles for this JD")
        score = min(score, 45.0)
    return _clamp(score), reasons


def _team_score(title: str, snippet: str, jd: dict[str, Any]) -> tuple[float, list[str]]:
    reasons: list[str] = []
    blob = f"{title or ''}\n{snippet or ''}".lower()
    depts = [d.lower() for d in (jd.get("departments") or [])]
    hits = [d for d in depts if d and d.lower() in blob]
    if hits:
        return 85.0, [f"Team/dept clue matches JD: {hits[0]}"]
    domain = jd.get("domain_terms") or []
    if any(t in blob for t in domain):
        return 65.0, ["Profile mentions domain terms from the JD"]
    if TITLE_DOMAIN.search(blob):
        return 55.0, ["Profile mentions data/analytics broadly"]
    if not (jd.get("jd_chars") or 0):
        return 50.0, ["No JD text yet — team affinity is neutral"]
    return 35.0, ["No clear team/department overlap with JD"]


def _activity_score(recent_activity: str) -> tuple[float, list[str]]:
    text = (recent_activity or "").strip()
    if not text:
        return 45.0, ["No recent activity note — activity score is neutral"]
    if HIRING_ACTIVITY.search(text):
        return 90.0, ["Recent activity mentions hiring / open roles"]
    if len(text) > 20:
        return 60.0, ["Has recent public activity (not clearly hiring-related)"]
    return 50.0, ["Sparse activity note"]


def _seniority_score(title: str) -> tuple[float, list[str]]:
    t = (title or "").strip()
    if re.search(r"\bhiring\s+manager\b", t, re.I):
        return 95.0, ["Seniority: Hiring Manager (best reply path)"]
    if re.search(r"\b(head\s+of|director|vp|chief)\b", t, re.I):
        return 88.0, ["Seniority: Head/Director-level decision maker"]
    if re.search(r"\b(manager|team\s+lead|lead)\b", t, re.I) and not TITLE_RECRUITER.search(t):
        return 80.0, ["Seniority: Manager / Team Lead"]
    if TITLE_RECRUITER.search(t) and not TITLE_GENERIC_TA.search(t):
        return 70.0, ["Seniority: Recruiter (good for process, less for team fit)"]
    if TITLE_GENERIC_TA.search(t):
        return 40.0, ["Seniority: generic TA — often lowest reply rate"]
    return 50.0, ["Seniority unclear from title"]


def _company_size_adjust(
    title: str,
    company_size: str | None,
    title_component: float,
    seniority_component: float,
) -> tuple[float, list[str]]:
    """10% weight: small cos boost recruiters; large cos boost HMs."""
    size = (company_size or "unknown").lower().strip()
    is_recruiter = bool(TITLE_RECRUITER.search(title or ""))
    is_hm = bool(TITLE_HM.search(title or "")) and not is_recruiter

    if size in ("small", "startup", "<200", "lt200"):
        if is_recruiter:
            return 85.0, ["Small company: Recruiter/HR often is the decision maker"]
        if is_hm:
            return 75.0, ["Small company: HM still strong"]
        return 60.0, ["Small company size noted"]
    if size in ("large", "enterprise", ">1000", "gt1000"):
        if is_hm:
            return 90.0, ["Large company: prefer Hiring Manager over generic TA"]
        if is_recruiter:
            return 55.0, ["Large company: Recruiter may not own this team"]
        return 50.0, ["Large company size noted"]
    # unknown / medium — blend of title & seniority already captured
    blended = 0.5 * title_component + 0.5 * seniority_component
    return blended, ["Company size unknown — neutral size adjustment"]


def score_candidate(
    *,
    name: str = "",
    title: str = "",
    snippet: str = "",
    recent_activity: str = "",
    company_size: str | None = None,
    jd_text: str = "",
    position: str = "",
    status: str = "not_contacted",
) -> dict[str, Any]:
    jd = extract_jd_signals(jd_text, position)
    title_s, title_r = _title_score(title, jd)
    team_s, team_r = _team_score(title, snippet, jd)
    act_s, act_r = _activity_score(recent_activity)
    sen_s, sen_r = _seniority_score(title)
    size_s, size_r = _company_size_adjust(title, company_size, title_s, sen_s)

    total = (
        0.35 * title_s
        + 0.25 * team_s
        + 0.15 * act_s
        + 0.15 * sen_s
        + 0.10 * size_s
    )
    score = int(round(_clamp(total)))
    stars = max(1, min(5, round(score / 20)))

    reasons = title_r[:1] + team_r[:1] + act_r[:1] + sen_r[:1]
    # Prefer the highest-signal reasons first
    primary = reasons[0] if reasons else "Limited public signals"
    if len(reasons) > 1:
        primary = f"{reasons[0]}; {reasons[1]}"

    return {
        "name": (name or "").strip(),
        "title": (title or "").strip(),
        "snippet": (snippet or "").strip(),
        "recent_activity": (recent_activity or "").strip(),
        "score": score,
        "stars": stars,
        "match_reason": primary,
        "reason_details": reasons + size_r[:1],
        "components": {
            "title": round(title_s, 1),
            "team": round(team_s, 1),
            "activity": round(act_s, 1),
            "seniority": round(sen_s, 1),
            "company_size": round(size_s, 1),
        },
        "status": status or "not_contacted",
        "jd_signals": jd,
    }


def rank_candidates(
    candidates: list[dict[str, Any]],
    *,
    jd_text: str = "",
    position: str = "",
    company_size: str | None = None,
) -> list[dict[str, Any]]:
    scored = [
        score_candidate(
            name=str(c.get("name") or ""),
            title=str(c.get("title") or c.get("role") or ""),
            snippet=str(c.get("snippet") or c.get("headline") or ""),
            recent_activity=str(c.get("recent_activity") or ""),
            company_size=str(c.get("company_size") or company_size or "") or None,
            jd_text=jd_text,
            position=position,
            status=str(c.get("status") or "not_contacted"),
        )
        | {
            "linkedin_url": str(c.get("linkedin_url") or ""),
            "id": str(c.get("id") or ""),
        }
        for c in candidates
    ]
    scored.sort(key=lambda x: (-int(x["score"]), (x.get("name") or "").lower()))
    return scored
