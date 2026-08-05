"""ATS type detection from URL (+ optional DOM signatures)."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from app.modules.form_fill_engine.schemas import ATSDetectionResult, ATSType, DOMSnapshot

# Fastest path: domain / host patterns (Phase 1–2: Workday / Greenhouse / Lever).
DOMAIN_PATTERNS: list[tuple[re.Pattern[str], ATSType]] = [
    (re.compile(r"(?:^|\.)myworkdayjobs\.com$", re.I), ATSType.WORKDAY),
    (re.compile(r"(?:^|\.)workdayjobs\.com$", re.I), ATSType.WORKDAY),
    (re.compile(r"(?:^|\.)greenhouse\.io$", re.I), ATSType.GREENHOUSE),
    (re.compile(r"^jobs\.lever\.co$", re.I), ATSType.LEVER),
    (re.compile(r"(?:^|\.)lever\.co$", re.I), ATSType.LEVER),
    (re.compile(r"(?:^|\.)ashbyhq\.com$", re.I), ATSType.ASHBY),
    (re.compile(r"(?:^|\.)icims\.com$", re.I), ATSType.ICIMS),
]

# Path / full-URL fallbacks used in fixtures and embedded widgets.
URL_SUBSTRINGS: list[tuple[str, ATSType]] = [
    ("myworkdayjobs.com", ATSType.WORKDAY),
    ("workdayjobs.com", ATSType.WORKDAY),
    ("fixture_workday", ATSType.WORKDAY),
    ("greenhouse.io", ATSType.GREENHOUSE),
    ("boards.greenhouse", ATSType.GREENHOUSE),
    ("fixture_greenhouse", ATSType.GREENHOUSE),
    ("jobs.lever.co", ATSType.LEVER),
    ("fixture_lever", ATSType.LEVER),
    ("ashbyhq.com", ATSType.ASHBY),
    ("icims.com", ATSType.ICIMS),
]

# Lightweight DOM signatures when domain misses (Phase 2+).
DOM_SIGNATURES: list[tuple[ATSType, list[str]]] = [
    (ATSType.WORKDAY, ["data-automation-id", "wd-CommandButton", "workday"]),
    (ATSType.GREENHOUSE, ["greenhouse", "application_form", "grnhse"]),
    (ATSType.LEVER, ["lever-apply", "posting-application", "lever-"]),
]


def _host(url: str) -> str:
    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        return (parsed.hostname or "").lower().rstrip(".")
    except Exception:
        return ""


def detect_ats(url: str, dom_snapshot: DOMSnapshot | None = None) -> ATSDetectionResult:
    host = _host(url or "")
    for pattern, ats_type in DOMAIN_PATTERNS:
        if host and pattern.search(host):
            return ATSDetectionResult(
                ats_type=ats_type,
                confidence=0.95,
                detection_method="domain_pattern",
            )

    lower = (url or "").lower()
    for needle, ats_type in URL_SUBSTRINGS:
        if needle in lower:
            return ATSDetectionResult(
                ats_type=ats_type,
                confidence=0.9,
                detection_method="domain_pattern",
            )

    if dom_snapshot is not None:
        blob_parts = [dom_snapshot.page_title or "", dom_snapshot.url or ""]
        for el in dom_snapshot.elements[:80]:
            blob_parts.append(el.label or "")
            blob_parts.append(el.selector or "")
            blob_parts.append(el.tag or "")
        blob = " ".join(blob_parts).lower()
        for ats_type, needles in DOM_SIGNATURES:
            if any(n.lower() in blob for n in needles):
                return ATSDetectionResult(
                    ats_type=ats_type,
                    confidence=0.7,
                    detection_method="dom_signature",
                )

    return ATSDetectionResult(
        ats_type=ATSType.UNKNOWN,
        confidence=0.0,
        detection_method="fallback",
    )
