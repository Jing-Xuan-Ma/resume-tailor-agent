"""Jobright-style listing quality gate: real JDs in, ad teasers out."""

from __future__ import annotations

import re
from typing import Any

from app.modules.job_discovery.scorer import extract_skills

# Typical aggregator teasers end with an ellipsis and almost no requirements.
_ELLIPSIS_RE = re.compile(r"(?:\u2026|\.\.\.)\s*$")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

_AD_TITLE_RE = re.compile(
    r"("
    r"make\s*\$\d|"
    r"guaranteed\s+interview|"
    r"no\s+experience\s+needed|"
    r"work\s+from\s+home\s+\$|"
    r"click\s+here\s+to\s+apply|"
    r"hiring\s+immediately!!!|"
    r"earn\s+extra\s+cash|"
    r"crypto\s+day\s+trader"
    r")",
    re.I,
)

_STRUCTURE_RE = re.compile(
    r"("
    r"responsibilities|requirements|qualifications|what\s+you.?ll\s+do|"
    r"about\s+the\s+role|job\s+description|minimum\s+qualifications|"
    r"preferred\s+qualifications|years\s+of\s+experience|must\s+have"
    r")",
    re.I,
)

# Platforms that often return truncated marketing blurbs, not full JDs.
_TEASER_PLATFORMS = {"adzuna"}


def jd_body(raw_text: str | None) -> str:
    """Strip header lines (Title/Company/Location/Source/URL) and HTML."""
    text = _HTML_TAG_RE.sub(" ", raw_text or "")
    lines: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            if lines:
                lines.append("")
            continue
        low = s.lower()
        if low.startswith(("company:", "location:", "source:", "url:", "http://", "https://")):
            continue
        lines.append(s)
    # Drop first line if it is only the job title repeated.
    body = "\n".join(lines).strip()
    return _WS_RE.sub(" ", body).strip()


_CSS_NOISE_RE = re.compile(
    r"^(?:tw-|sm:|md:|lg:|xl:|hover:|focus:|ring-|border-|shadow-|bg-|text-|flex|grid|rounded|px-|py-|mt-|mb-|ml-|mr-|w-|h-|min-|max-|font-|leading-|tracking-|opacity-|transition|absolute|relative|inset-|z-|overflow-|items-|justify-|gap-|col-|row-|prose)",
    re.I,
)


def jd_plaintext(raw_text: str | None) -> str:
    """Human-readable JD for UI/workspace: strip tags, keep lines, drop CSS class dumps."""
    text = raw_text or ""
    # Break tags into line boundaries so list items survive
    text = re.sub(r"<(br|/p|/li|/div|/h\d)[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<li[^>]*>", "\n- ", text, flags=re.I)
    text = _HTML_TAG_RE.sub(" ", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = re.sub(r"[ \t]+", " ", text)
    out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            if out and out[-1] != "":
                out.append("")
            continue
        # Drop lines that are mostly Tailwind / utility-class noise
        tokens = s.split()
        if tokens and sum(1 for t in tokens if _CSS_NOISE_RE.match(t) or t.startswith("tw-")) >= max(2, len(tokens) // 2):
            continue
        if s.count("-") > 8 and " " not in s[:20]:
            continue
        out.append(s)
    return "\n".join(out).strip()


def assess_listing_quality(lead: dict[str, Any], *, min_chars: int = 500) -> dict[str, Any]:
    """Return {ok, reason, body_len, skills, structured}."""
    title = str(lead.get("title") or "").strip()
    company = str(lead.get("company") or "").strip()
    platform = str(lead.get("source_platform") or "").strip().lower()
    url = str(lead.get("source_url") or "").strip()
    raw = lead.get("raw_text") or lead.get("description") or ""
    body = jd_body(str(raw))
    body_len = len(body)
    skills = sorted(extract_skills(body))
    structured = bool(_STRUCTURE_RE.search(body))
    base_platform = platform.split(":", 1)[0]

    if not title or title.lower() in {"untitled", "untitled job"}:
        return _fail("empty_title", body_len, skills, structured)
    if not company or company.lower() in {"nan", "none", "n/a", "unknown"}:
        return _fail("empty_company", body_len, skills, structured)
    if not url or not url.startswith("http"):
        return _fail("missing_url", body_len, skills, structured)
    if _AD_TITLE_RE.search(title):
        return _fail("ad_title", body_len, skills, structured)

    # Aggregator ad board — never treat as a real full JD source.
    if base_platform in _TEASER_PLATFORMS:
        return _fail("adzuna_ad_board", body_len, skills, structured)

    if body_len < min_chars:
        return _fail("jd_too_short", body_len, skills, structured)

    if _ELLIPSIS_RE.search(body) and body_len < 700 and not skills:
        return _fail("truncated_teaser", body_len, skills, structured)

    # Prefer listings that look like real JDs: skills or requirement sections.
    if not skills and not structured and body_len < 1500:
        return _fail("no_skills_or_structure", body_len, skills, structured)

    return {
        "ok": True,
        "reason": "pass",
        "body_len": body_len,
        "skills": skills,
        "structured": structured,
    }


def _fail(reason: str, body_len: int, skills: list[str], structured: bool) -> dict[str, Any]:
    return {
        "ok": False,
        "reason": reason,
        "body_len": body_len,
        "skills": skills,
        "structured": structured,
    }


def filter_quality_leads(
    leads: list[dict[str, Any]],
    *,
    min_chars: int = 500,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split into (accepted, rejected_with_reason)."""
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for lead in leads:
        verdict = assess_listing_quality(lead, min_chars=min_chars)
        meta = dict(lead.get("metadata") or {})
        meta["quality"] = {
            "ok": verdict["ok"],
            "reason": verdict["reason"],
            "body_len": verdict["body_len"],
            "skill_count": len(verdict["skills"]),
            "skills_sample": verdict["skills"][:8],
            "structured": verdict["structured"],
        }
        enriched = {**lead, "metadata": meta}
        if verdict["ok"]:
            accepted.append(enriched)
        else:
            rejected.append({**enriched, "reject_reason": verdict["reason"]})
    return accepted, rejected
