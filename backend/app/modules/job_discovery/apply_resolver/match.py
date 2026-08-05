"""Title/location/req-id confidence scoring for ATS search hits."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from app.modules.job_discovery.apply_resolver.models import ApplyCandidate

_REQ_RE = re.compile(
    r"\b(?:JR[-_]?|R[-_]?)?\d{4,}[-_]?\d*\b|\bR-\d{5,}\b|\bJR-?\d+\b",
    re.I,
)


def normalize_title(text: str | None) -> str:
    s = re.sub(r"[^a-z0-9]+", " ", (text or "").lower())
    return re.sub(r"\s+", " ", s).strip()


def extract_req_ids(*texts: str | None) -> set[str]:
    found: set[str] = set()
    for t in texts:
        if not t:
            continue
        for m in _REQ_RE.finditer(t):
            found.add(re.sub(r"[^a-z0-9]", "", m.group(0).lower()))
    return found


def score_candidate(
    cand: ApplyCandidate,
    *,
    title: str,
    location: str | None = None,
    raw_text: str | None = None,
) -> float:
    """Return 0..1 confidence that cand matches the target job."""
    score = 0.0
    nt = normalize_title(title)
    ct = normalize_title(cand.title)
    if not nt or not ct:
        return 0.0

    if nt == ct:
        score += 0.55
    elif nt in ct or ct in nt:
        score += 0.4
    else:
        ratio = SequenceMatcher(None, nt, ct).ratio()
        score += 0.35 * ratio

    target_reqs = extract_req_ids(title, raw_text)
    cand_reqs = extract_req_ids(cand.req_id, cand.title, cand.url)
    if target_reqs and cand_reqs and target_reqs & cand_reqs:
        score += 0.35  # strongest signal

    if location and cand.location:
        loc_l = location.lower()
        cl = cand.location.lower()
        if loc_l in cl or cl in loc_l:
            score += 0.08
        else:
            # city token overlap
            loc_tokens = set(re.findall(r"[a-z]{3,}", loc_l))
            cl_tokens = set(re.findall(r"[a-z]{3,}", cl))
            if loc_tokens & cl_tokens:
                score += 0.05

    posted = (cand.posted_on or "").lower()
    if "30+" in posted or "60+" in posted or "90+" in posted:
        score -= 0.08

    return max(0.0, min(1.0, score))


def pick_best(
    candidates: list[ApplyCandidate],
    *,
    title: str,
    location: str | None = None,
    raw_text: str | None = None,
    min_confidence: float = 0.45,
) -> ApplyCandidate | None:
    if not candidates:
        return None
    best: ApplyCandidate | None = None
    for c in candidates:
        c.confidence = score_candidate(c, title=title, location=location, raw_text=raw_text)
        if best is None or c.confidence > best.confidence:
            best = c
    if best and best.confidence >= min_confidence:
        return best
    return None
